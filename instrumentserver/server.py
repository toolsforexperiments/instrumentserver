import os
import time
import logging
import random
from typing import Union

import zmq
from qcodes import Parameter, Station, Instrument

from . import resource
from . import QtCore, QtWidgets, QtGui, serialize
from .base import send, recv
from .log import LogLevels, LogWidget, log, setupLogging
from .serialize import toParamDict
from .helpers import getInstrumentMethods, getInstrumentParameters, toHtml


logger = logging.getLogger(__name__)


# TODO: parameter file location should be optionally configurable
# TODO: should be possible to look at all parameters in an instrument
# TODO: add an option to save one file per station component


class StationList(QtWidgets.QTreeWidget):
    """A widget that displays all objects in a qcodes station"""

    cols = ['Name', 'Info']

    #: Signal(str) --
    #: emitted when a parameter or Instrument is selected
    componentSelected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(len(self.cols))
        self.setHeaderLabels(self.cols)
        self.setSortingEnabled(True)
        self.clear()

        self.itemSelectionChanged.connect(self._processSelection)

    def clear(self):
        super().clear()
        self.instrumentsItem = QtWidgets.QTreeWidgetItem(['Instruments', ''])
        self.paramsItem = QtWidgets.QTreeWidgetItem(['Parameters', ''])
        self.addTopLevelItem(self.paramsItem)
        self.addTopLevelItem(self.instrumentsItem)

    def _addParameterTo(self, parent, obj):
        lst = [obj.name]
        info = toParamDict([obj], includeMeta=['vals', 'unit'])[obj.name]
        infoString = f"{str(obj.__class__.__name__)}"
        lst.append(infoString)
        paramItem = QtWidgets.QTreeWidgetItem(lst)
        parent.addChild(paramItem)

    def addObject(self, obj: Union[Instrument, Parameter]):
        lst = [obj.name, f"{str(obj.__class__.__name__)}"]
        if isinstance(obj, Instrument):
            insItem = QtWidgets.QTreeWidgetItem(lst)
            self.instrumentsItem.addChild(insItem)

        elif isinstance(obj, Parameter):
            paramItem = QtWidgets.QTreeWidgetItem(lst)
            self.paramsItem.addChild(paramItem)

    def removeObject(self, name: str):
        items = self.findItems(name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
        for i in items:
            if i not in [self.instrumentsItem, self.paramsItem]:
                parent = i.parent()
                parent.removeChild(i)
                del i

    def _processSelection(self):
        items = self.selectedItems()
        if len(items) == 0:
            return
        item = items[0]
        if item not in [self.instrumentsItem, self.paramsItem]:
            self.componentSelected.emit(item.text(0))


class StationObjectInfo(QtWidgets.QTextEdit):

    @staticmethod
    def htmlDoc(obj: Union[Parameter, Instrument]):
        pass

    @staticmethod
    def parameterHtml(param: Parameter):
        pass

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)

    @QtCore.Slot(object)
    def setObject(self, obj: Union[Instrument, Parameter]):
        self.setHtml(toHtml(obj))


class ServerStatus(QtWidgets.QWidget):
    """A widget that shows the status of the instrument server."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QtWidgets.QVBoxLayout(self)

        # At the top: a status label, and a button for emitting a test message
        self.addressLabel = QtWidgets.QLabel()
        self.testButton = QtWidgets.QPushButton('Send test message')
        self.statusLayout = QtWidgets.QHBoxLayout()
        self.statusLayout.addWidget(self.addressLabel, 1)
        self.statusLayout.addWidget(self.testButton, 0)
        self.testButton.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                  QtWidgets.QSizePolicy.Minimum)
        )

        self.layout.addLayout(self.statusLayout)

        # next row: a window for displaying the incoming messages.
        self.layout.addWidget(QtWidgets.QLabel('Messages:'))
        self.messages = QtWidgets.QTextEdit()
        self.messages.setReadOnly(True)
        self.layout.addWidget(self.messages)

    @QtCore.Slot(str)
    def setListeningAddress(self, addr: str):
        self.addressLabel.setText(f"Listening on: {addr}")

    @QtCore.Slot(str, str)
    def addMessageAndReply(self, message: str, reply: str):
        tstr = time.strftime("%Y-%m-%d %H:%M:%S")
        self.messages.setTextColor(QtGui.QColor('black'))
        self.messages.append(f"[{tstr}]")
        self.messages.setTextColor(QtGui.QColor('blue'))
        self.messages.append(f"Server received: {message}")
        self.messages.setTextColor(QtGui.QColor('green'))
        self.messages.append(f"Server replied: {reply}")


class ServerGui(QtWidgets.QMainWindow):
    """Main window of the qcodes station server."""

    serverPortSet = QtCore.Signal(int)

    def __init__(self, station, startServer=True):
        super().__init__()

        self._paramValuesFile = os.path.join('.', 'parameters.json')
        self._serverPort = None

        self.setWindowTitle('Instrument server')

        # central widget is simply a tab container
        self.tabs = QtWidgets.QTabWidget(self)
        self.setCentralWidget(self.tabs)

        self.stationList = StationList()
        self.stationObjInfo = StationObjectInfo()
        self.stationList.componentSelected.connect(self.displayComponentInfo)

        stationWidgets = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        stationWidgets.addWidget(self.stationList)
        stationWidgets.addWidget(self.stationObjInfo)
        stationWidgets.setSizes([300, 700])
        self.tabs.addTab(stationWidgets, 'Station')

        self.tabs.addTab(LogWidget(level=logging.INFO), 'Log')

        self.serverStatus = ServerStatus()
        self.tabs.addTab(self.serverStatus, 'Server')

        # toolbar
        self.toolBar = self.addToolBar('Tools')
        self.toolBar.setIconSize(QtCore.QSize(16, 16))

        # station tools
        self.toolBar.addWidget(QtWidgets.QLabel('Station:'))
        refreshStationAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/refresh.svg"), 'Refresh', self)
        refreshStationAction.triggered.connect(self.refreshStationComponents)
        self.toolBar.addAction(refreshStationAction)

        # parameter tools
        self.toolBar.addSeparator()
        self.toolBar.addWidget(QtWidgets.QLabel('Params:'))

        loadParamsAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/load.svg"), 'Load from file', self)
        loadParamsAction.triggered.connect(self.loadParamsFromFile)
        self.toolBar.addAction(loadParamsAction)

        saveParamsAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/save.svg"), 'Save to file', self)
        saveParamsAction.triggered.connect(self.saveParamsToFile)
        self.toolBar.addAction(saveParamsAction)

        self.station = station
        self.refreshStationComponents()

        # A test client, just a simple helper object
        self.testClient = TestClient()
        self.testClient.log.connect(self.log)
        self.serverPortSet.connect(self.testClient.setServerPort)
        self.serverStatus.testButton.clicked.connect(
            lambda x: self.testClient.sendMessage("Ping server.")
        )

        if startServer:
            self.startServer()

    def log(self, message, level=LogLevels.info):
        log(logger, message, level)

    def closeEvent(self, event):
        if hasattr(self, 'stationServerThread'):
            if self.stationServerThread.isRunning():
                self.testClient.sendMessage(self.stationServer.SAFEWORD)
        event.accept()

    def startServer(self):
        """Start the instrument server in a separate thread."""
        self.stationServer = StationServer(station=self.station)
        self.stationServerThread = QtCore.QThread()
        self.stationServer.moveToThread(self.stationServerThread)
        self.stationServerThread.started.connect(self.stationServer.startServer)
        self.stationServer.finished.connect(lambda: self.log('ZMQ server closed.'))
        self.stationServer.finished.connect(self.stationServerThread.quit)
        self.stationServer.finished.connect(self.stationServer.deleteLater)

        # connecting some additional things for messages
        self.stationServer.log.connect(self.log)
        self.stationServer.serverStarted.connect(self.serverStatus.setListeningAddress)
        self.stationServer.serverStarted.connect(self._setServerAddr)
        self.stationServer.finished.connect(
            lambda: self.log('Server thread finished.', LogLevels.info)
        )
        self.stationServer.messageReceived.connect(self._messageReceived)
        self.stationServerThread.start()

    @QtCore.Slot(str)
    def _setServerAddr(self, addr: str):
        port = int(addr.split(":")[-1])
        self._serverPort = port
        self.serverPortSet.emit(port)

    @QtCore.Slot(str, str)
    def _messageReceived(self, message: str, reply: str):
        maxLen = 80
        messageSummary = message[:maxLen]
        replySummary = reply[:maxLen]
        self.log(f"Server received: {message}", LogLevels.debug)
        self.log(f"Server replied: {reply}", LogLevels.debug)
        self.serverStatus.addMessageAndReply(messageSummary, replySummary)

    def addStationComponent(self, obj: Union[Parameter, Instrument]):
        """Add an object (instrument or unbound parameter) to the station.

        Will add the object also to the widget listing the station components.
        """
        self.station.add_component(obj)
        self.log(f"Added to station: {obj}", LogLevels.info)
        if isinstance(obj, Instrument) or isinstance(obj, Parameter):
            self.stationList.addObject(obj)
        else:
            self.log(f"Cannot add <{obj}> to list of objects (unknown type).",
                     LogLevels.warn)

    def removeStationComponent(self, name: str):
        """Remove an object from the station, and also from the widget showing
        the station contents.

        If the object is an instrument, we make sure to close it.
        """
        obj = self.station.components[name]
        if isinstance(obj, Instrument):
            self.station.close_and_remove_instrument(obj)
        else:
            self.station.remove_component(name)
        self.stationList.removeObject(name)
        self.log(f"Removed from station: {obj}", LogLevels.info)

    def refreshStationComponents(self):
        """clear and re-populate the widget holding the station components, using
        the objects that are currently registered in the station."""
        self.stationList.clear()
        for _, obj in self.station.components.items():
            self.stationList.addObject(obj)

        for i in range(self.stationList.topLevelItemCount()):
            item = self.stationList.topLevelItem(i)
            self.stationList.expandItem(item)

        for i, _ in enumerate(self.stationList.cols):
            self.stationList.resizeColumnToContents(i)

    def loadParamsFromFile(self):
        """load the values of all parameters present in the server's params json file
        to parameters registered in the station (incl those in instruments)."""

        self.log(f"Loading parameters from file: "
                 f"{os.path.abspath(self._paramValuesFile)}", LogLevels.info)
        serialize.loadParamsFromFile(self._paramValuesFile, self.station)

    def saveParamsToFile(self):
        """save the values of all parameters registered in the station (incl
         those in instruments) to the server's param json file."""

        self.log(f"Saving parameters to file: "
                 f"{os.path.abspath(self._paramValuesFile)}", LogLevels.info)
        serialize.saveParamsToFile(self.station, self._paramValuesFile)

    @QtCore.Slot(str)
    def displayComponentInfo(self, name: Union[str, None]):
        if name is not None:
            obj = self.station.components[name]
        else:
            obj = None
        self.stationObjInfo.setObject(obj)


def servergui(station: Station) -> "ServerGui":
    """Create a server gui window

    Can be used in an ipython kernel with Qt mainloop.
    """

    setupLogging(addStreamHandler=False,
                 logFile=os.path.abspath('instrumentserver.log'))
    logging.getLogger('instrumentserver').setLevel(logging.DEBUG)
    window = ServerGui(station, startServer=True)
    window.show()
    return window


# initial prototype for server functionality below.

class StationServer(QtCore.QObject):
    """Prototype for a server object.

    Encapsulated in a separate object so we can run it in a separate thread.
    """

    # we use this to quit the server.
    # if this string is sent as message to the server, it'll shut down and close
    # the socket. Should only be used from within this module.
    # it's randomized for a little bit of safety.
    SAFEWORD = ''.join(random.choices([chr(i) for i in range(65, 91)], k=16))

    #: signal to emit log messages
    log = QtCore.Signal(str, LogLevels)

    #: Signal(str, str) -- emit messages for display in the gui (or other stuff the gui
    #: wants to do with it.
    #: Arguments: the message received, and the reply sent.
    messageReceived = QtCore.Signal(str, str)

    #: Signal(int) -- emitted when the server is started.
    #: Arguments: the port.
    serverStarted = QtCore.Signal(str)

    #: Signal() -- emitted when we shut down
    finished = QtCore.Signal()

    def __init__(self, station=None, parent=None, port=None):
        super().__init__(parent)

        self.SAFEWORD = ''.join(random.choices([chr(i) for i in range(65, 91)], k=16))
        self.station = station
        self.serverRunning = False
        self.port = port
        if self.port is None:
            self.port = 5555

    @QtCore.Slot()
    def startServer(self):
        addr = f"tcp://*:{self.port}"
        self.log.emit(f"Starting server at {addr}", LogLevels.info)
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind(addr)

        self.serverRunning = True
        self.serverStarted.emit(addr)

        while self.serverRunning:
            message = recv(socket)

            if message == self.SAFEWORD:
                reply = 'As you command, server will now shut down.'
                self.serverRunning = False
            else:
                reply = 'Thank you for your message.'

            send(socket, str(reply))
            self.messageReceived.emit(message, reply)

        socket.close()
        self.finished.emit()
        return True


class TestClient(QtCore.QObject):
    """A simple client we can use to test if the server replies."""

    #: signal to emit log messages
    log = QtCore.Signal(str, LogLevels)
    serverAddressSet = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.serverAddr = None

    @QtCore.Slot(int)
    def setServerPort(self, port: int):
        self.serverAddr = f"tcp://localhost:{port}"
        self.serverAddressSet.emit()

    @QtCore.Slot(str)
    def sendMessage(self, msg: str):
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(self.serverAddr)
        self.log.emit(f"Test client sending request: {msg}", LogLevels.debug)
        send(socket, msg)
        reply = recv(socket)
        self.log.emit(f"Test client received reply: {reply}", LogLevels.debug)
        socket.close()
