import logging
import uuid
import warnings
from types import TracebackType
from typing import Any, Optional, Type

import zmq

from instrumentserver import DEFAULT_PORT
from instrumentserver.base import recv, send
from instrumentserver.server.core import ServerResponse

logger = logging.getLogger(__name__)


class BaseClient:
    """Simple client for the StationServer.
    When a timeout happens, a RunTimeError is being raised. This error is there just to warn the user that a timeout
    has occurred. After that the client will restart the socket to continue the normal work.

    :param host: The host address of the server, defaults to localhost.
    :param port: The port of the server, defaults to the value of DEFAULT_PORT.
    :param connect: If true, the server connects as it is being constructed, defaults to True.
    :param timeout: Amount of time that the client waits for an answer before declaring timeout in seconds.
                    Defaults to 20s.
    :param raise_exceptions: If true the client will raise an exception when the server sends one to it, defaults to True.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = DEFAULT_PORT,
        connect: bool = True,
        timeout: float = 20,
        raise_exceptions: bool = True,
    ) -> None:
        self.connected = False
        self._closed = False
        self.context: Optional[zmq.Context] = None
        self.socket: Optional[zmq.Socket] = None
        self.host = host
        self.port = port
        self.addr = f"tcp://{host}:{port}"
        self.raise_exceptions = raise_exceptions
        self.recv_timeout_ms = int(timeout * 1e3)

        if connect:
            self.connect()

    def __enter__(self) -> "BaseClient":
        if not self.connected:
            self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.disconnect()

    def connect(self) -> None:
        if self._closed:
            raise RuntimeError("Client has been permanently disconnected.")
        # Clean up any existing context/socket so we don't leak them when
        # connect() is called more than once (e.g. EmbeddedClient.start()).
        if self.socket is not None:
            try:
                self.socket.close(linger=0)
            except Exception:
                pass
            self.socket = None
        if self.context is not None:
            try:
                self.context.destroy(linger=0)
            except Exception:
                pass
            self.context = None
        logger.info(f"Connecting to {self.addr}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.RCVTIMEO, self.recv_timeout_ms)
        self.socket.setsockopt(
            zmq.IDENTITY, uuid.uuid4().hex.encode()
        )  # todo: more meaningful id?
        self.socket.connect(self.addr)
        self.connected = True

    def ask(self, message: Any) -> Any:
        if self._closed or not self.connected:
            raise RuntimeError("No connection yet.")

        # try so that if timeout happens, the client remains usable
        try:
            send(self.socket, message)  # type: ignore[arg-type]
            ret = recv(self.socket)  # type: ignore[arg-type]
            logger.debug("Response received.")
            logger.debug(f"Response: {str(ret)}")
        except zmq.error.Again:
            self._reset_connection()
            if self.raise_exceptions:
                raise RuntimeError("Server did not reply before timeout.")
            else:
                logger.error("Server did not reply before timeout.")
                return None

        if isinstance(ret, ServerResponse):
            err = ret.error
            if err is not None:
                self._handle_server_error(err)
            return ret.message

        return ret

    def _reset_connection(self) -> None:
        try:
            if self.socket is not None:
                self.socket.close(linger=0)
        finally:
            self.connected = False
            if not self._closed:
                self.connect()

    def _handle_server_error(self, err: Any) -> None:
        if isinstance(err, str):
            logger.error(err)
            if self.raise_exceptions:
                raise RuntimeError(err)
        elif isinstance(err, Warning):
            warnings.warn(err)
        elif isinstance(err, Exception):
            if self.raise_exceptions:
                raise err
            logger.error(f"Server raised exception: {err}")
        else:
            msg = f"Unknown error type from server: {err!r}"
            if self.raise_exceptions:
                raise TypeError(msg)
            logger.error(msg)

    def disconnect(self) -> None:
        self._closed = True
        if self.socket is not None:
            try:
                self.socket.close(linger=0)
            except Exception:
                pass
            self.socket = None
        if self.context is not None:
            try:
                self.context.destroy(linger=0)
            except Exception:
                pass
            self.context = None
        self.connected = False


def sendRequest(message: Any, host: str = "localhost", port: int = DEFAULT_PORT) -> Any:
    with BaseClient(host, port) as cli:
        ret = cli.ask(message)
    return ret
