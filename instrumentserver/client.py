import logging
import zmq

from .base import send, recv

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class StationClient:
    """Simple client for the StationServer"""

    def __init__(self):
        self.connected = False
        self.context = None
        self.socket = None

    def connect(self, host='localhost', port=5555):
        addr = f"tcp://{host}:{port}"
        log.info(f"Connecting to {addr}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(addr)
        self.connected = True

    def ask(self, message):
        if not self.connected:
            raise RuntimeError("No connection yet.")

        send(self.socket, message)
        reply = recv(self.socket)
        log.debug(f"Reply: {reply}")
        return reply

    def disconnect(self):
        self.socket.close()
        self.connected = False


def startClient(host='localhost', port=5555):
    cli = StationClient()
    cli.connect(host, port)
    return cli

