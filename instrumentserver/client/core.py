import logging
import warnings
import zmq
import uuid

from instrumentserver import DEFAULT_PORT
from instrumentserver.base import send, recv
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

    def __init__(self, host='localhost', port=DEFAULT_PORT, connect=True, timeout=20, raise_exceptions=True):
        self.connected = False
        self.context = None
        self.socket = None
        self.host = host
        self.port = port
        self.addr = f"tcp://{host}:{port}"
        self.raise_exceptions = raise_exceptions
        self.recv_timeout_ms = int(timeout * 1e3)

        if connect:
            self.connect()

    def __enter__(self):
        if not self.connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        logger.info(f"Connecting to {self.addr}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.RCVTIMEO, self.recv_timeout_ms)
        self.socket.setsockopt(zmq.IDENTITY, uuid.uuid4().hex.encode()) #todo: more meaningful id?
        self.socket.connect(self.addr)
        self.connected = True

    def ask(self, message):
        if not self.connected:
            raise RuntimeError("No connection yet.")

        # try so that if timeout happens, the client remains usable
        try:
            send(self.socket, message)
            ret = recv(self.socket)
            logger.debug(f"Response received.")
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
    
    def _reset_connection(self):
        try:
            if self.socket is not None:
                self.socket.close(linger=0)
        finally:
            self.connected = False
            self.connect()
            
    def _handle_server_error(self, err):
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
    
    def disconnect(self):
        if self.socket is not None:
            try:
                self.socket.close(linger=0)
            except Exception:
                pass
            self.socket = None
        self.connected = False


def sendRequest(message, host='localhost', port=DEFAULT_PORT):
    with BaseClient(host, port) as cli:
        ret = cli.ask(message)
    return ret

