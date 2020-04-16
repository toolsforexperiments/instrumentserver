import time
import logging
import pickle
from enum import Enum, unique, auto

import zmq
from qcodes import Parameter, Station

from qtpy import QtCore, QtWidgets, QtGui
from .base import send, recv
from .log import LogLevels, LogWidget, log, setupLogging


logger = logging.getLogger(__name__)


class StationServer(QtCore.QObject):
    """Prototype for a server object.

    Encapsulated in a separate object so we can run it in a separate thread.
    """

    REP_PORT = 5555

    #: signal to emit log messages
    log = QtCore.Signal(str, LogLevels)

    def __init__(self, station=None, parent=None):
        super().__init__(parent)

        self.station = station
        self.server_running = False

    @QtCore.Slot()
    def startServer(self):
        addr = f"tcp://*:{self.REP_PORT}"
        self.log.emit(f"Starting server at {addr}", LogLevels.info)
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind(addr)

        self.server_running = True
        while self.server_running:
            message = recv(socket)
            self.log.emit(f"Message received: {message}", LogLevels.debug)

            if message == 'log_components':
                components = list(self.station.components.keys())
                self.log.emit(f"Station contains: {components}", LogLevels.info)
                send(socket, str(list(self.station.components.keys())))

            else:
                self.log.emit(f"Unknown request: {message}", LogLevels.info)
                send(socket, False)


class ServerGuiWidget(QtWidgets.QWidget):
    """Central widget for the ServerGui."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(LogWidget(self))

        self.setLayout(self.layout)


class ServerGui(QtWidgets.QMainWindow):
    """Simple MainWindow that contains a StationServer object"""

    def __init__(self, station):
        super().__init__()
        self.guiWidget = ServerGuiWidget()
        self.setCentralWidget(self.guiWidget)
        self.station = station

        self.stationServer = StationServer(station=self.station)
        self.stationServerThread = QtCore.QThread()
        self.stationServer.moveToThread(self.stationServerThread)
        self.stationServerThread.started.connect(
            self.stationServer.startServer
        )
        self.stationServer.log.connect(self.log)

    def startServer(self):
        self.stationServerThread.start()

    def log(self, message, level):
        log(logger, message, level)


def servergui(station: Station) -> "ServerGui":
    """Create a server gui window

    Can be used in an ipython kernel with Qt mainloop.
    """

    setupLogging(addStreamHandler=False)
    logging.getLogger('instrumentserver').setLevel(logging.DEBUG)
    window = ServerGui(station)
    window.show()
    return window



