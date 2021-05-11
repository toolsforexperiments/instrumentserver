import zmq
import logging

logger = logging.getLogger(__name__)


class SubClient:
    """Test client to test PUB-SUB"""

    def __init__(self, host='localhost', port=5554):
        self.connected = False
        self.context = None
        self.socket = None
        self.host = host
        self.port = port
        self.addr = f"tcp://{host}:{port}"
        print("I am working")

    def connect(self):
        logger.info(f"Connecting to {self.addr}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.connect(self.addr)
        self.connected = True

        while self.connected:

            message = self.socket.recv_string()
            print(str(self.id)+" the message is: " + message)


        print("closing connection")
        self.disconnect()
        return True