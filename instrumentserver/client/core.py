import logging
import warnings
import zmq

from instrumentserver import DEFAULT_PORT, QtCore
from instrumentserver.base import send, recv
from instrumentserver.server.core import ServerResponse


logger = logging.getLogger(__name__)


# TODO: allow for the client to operate as context manager.


class BaseClient:
    """Simple client for the StationServer.

    :param host: The host address of the server, defaults to localhost.
    :param port: The port of the server, defaults to the value of DEFAULT_PORT.
    :param connect: If true, the server connects as it is being constructed, defaults to True.
    :param timeout: Amount of time that the client waits for an answer before declaring timeout in ms.
                    Defaults to 5000.
    """

    def __init__(self, host='localhost', port=DEFAULT_PORT, connect=True, timeout=5000):
        self.connected = False
        self.context = None
        self.socket = None
        self.host = host
        self.port = port
        self.addr = f"tcp://{host}:{port}"

        #: timeout for server replies.
        self.recv_timeout = timeout

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
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.recv_timeout)
        self.socket.connect(self.addr)
        self.connected = True

    def ask(self, message):
        if not self.connected:
            raise RuntimeError("No connection yet.")

        # try so that if timeout happens, the client remains usable
        try:
            send(self.socket, message)
            ret = recv(self.socket)
            logger.info(f"Response received.")
            logger.debug(f"Response: {str(ret)}")

            if isinstance(ret, ServerResponse):
                err = ret.error
                if err is not None:
                    if isinstance(err, str):
                        logger.error(err)
                    elif isinstance(err, Warning):
                        warnings.warn(err)
                    elif isinstance(err, Exception):
                        raise err
                    else:
                        raise TypeError(f'Unknown Error Type: {str(err)}')
            return ret.message

        except zmq.error.Again as e:
            # if there is a timeout, close the socket and connect again
            self.socket.close()
            self.connect()
            raise RuntimeError(f'Server did not reply before timeout.')


    def disconnect(self):
        self.socket.close()
        self.connected = False


def sendRequest(message, host='localhost', port=DEFAULT_PORT):
    with BaseClient(host, port) as cli:
        ret = cli.ask(message)
    return ret

