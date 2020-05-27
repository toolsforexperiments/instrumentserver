import logging
import zmq

from .base import send, recv


logger = logging.getLogger(__name__)


class StationClient:
    """Simple client for the StationServer"""

    def __init__(self):
        self.connected = False
        self.context = None
        self.socket = None

    def connect(self, host='localhost', port=5555):
        addr = f"tcp://{host}:{port}"
        logger.info(f"Connecting to {addr}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(addr)
        self.connected = True

    def ask(self, message):
        if not self.connected:
            raise RuntimeError("No connection yet.")

        send(self.socket, message)
        reply = recv(self.socket)
        logger.info(f"Response received.")
        logger.debug(f"Response: {str(reply)}")
        return reply

    def disconnect(self):
        self.socket.close()
        self.connected = False


def startClient(host='localhost', port=5555):
    cli = StationClient()
    cli.connect(host, port)
    return cli


def sendRequest(message, host='localhost', port=5555):
    cli = startClient(host, port)
    ret = cli.ask(message)
    cli.disconnect()
    return ret

