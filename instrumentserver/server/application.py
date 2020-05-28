import html
import os
import time
import logging
from typing import Union, Optional

from .. import QtCore, QtWidgets, QtGui, DEFAULT_PORT, serialize, resource
from instrumentserver.log import LogLevels, LogWidget, log, setupLogging
from instrumentserver.client import QtClient

from .core import (
    StationServer,
    InstrumentModuleBluePrint, ParameterBluePrint, MethodBluePrint
)

logger = logging.getLogger(__name__)


# TODO: parameter file location should be optionally configurable
# TODO: add an option to save one file per station component
# TODO: allow for user shutdown of the server.
# TODO: use the safeword approach to configure the server on the fly
#   allowing users to shut down, etc, set other internal properties of
#   of the server object.


class StationList(QtWidgets.QTreeWidget):
    """A widget that displays all objects in a qcodes station"""

    cols = ['Name', 'Type']

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

    def addInstrument(self, bp: InstrumentModuleBluePrint):
        lst = [bp.name, f"{bp.instrument_module_class}"]
        self.addTopLevelItem(QtWidgets.QTreeWidgetItem(lst))

    def removeObject(self, name: str):
        items = self.findItems(name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
        if len(items) > 0:
            item = items[0]
            idx = self.indexOfTopLevelItem(item)
            self.takeTopLevelItem(idx)
            del item

    def _processSelection(self):
        items = self.selectedItems()
        if len(items) == 0:
            return
        item = items[0]
        self.componentSelected.emit(item.text(0))


class StationObjectInfo(QtWidgets.QTextEdit):

    # TODO: make this a bit better looking
    # TODO: add a TOC for the instrument?

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)

    @QtCore.Slot(object)
    def setObject(self, obj: InstrumentModuleBluePrint):
        self.setHtml(bluePrintToHtml(obj))


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

    def __init__(self,
                 startServer: Optional[bool] = True,
                 serverPort: Optional[int] = DEFAULT_PORT):
        super().__init__()

        self._paramValuesFile = os.path.join('.', 'parameters.json')
        self._serverPort = serverPort
        self.stationServer = None
        self.stationServerThread = None

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

        # FIXME this won't work yet
        self.refreshStationComponents()

        # A test client, just a simple helper object
        self.client = EmbeddedClient()
        self.serverStatus.testButton.clicked.connect(
            lambda x: self.client.ask("Ping server.")
        )
        if startServer:
            self.startServer()

    def log(self, message, level=LogLevels.info):
        log(logger, message, level)

    def closeEvent(self, event):
        if hasattr(self, 'stationServerThread'):
            if self.stationServerThread.isRunning():
                self.client.sendMessage(self.stationServer.SAFEWORD)
        event.accept()

    def startServer(self):
        """Start the instrument server in a separate thread."""
        self.stationServer = StationServer(port=self._serverPort)
        self.stationServerThread = QtCore.QThread()
        self.stationServer.moveToThread(self.stationServerThread)
        self.stationServerThread.started.connect(self.stationServer.startServer)
        self.stationServer.finished.connect(lambda: self.log('ZMQ server closed.'))
        self.stationServer.finished.connect(self.stationServerThread.quit)
        self.stationServer.finished.connect(self.stationServer.deleteLater)

        # connecting some additional things for messages
        self.stationServer.serverStarted.connect(self.serverStatus.setListeningAddress)
        self.stationServer.serverStarted.connect(self.client.start)
        self.stationServer.finished.connect(
            lambda: self.log('Server thread finished.', LogLevels.info)
        )
        self.stationServer.messageReceived.connect(self._messageReceived)
        self.stationServer.instrumentCreated.connect(self.addInstrumentToGui)

        self.stationServerThread.start()

    def getServerIfRunning(self):
        if self.stationServer is not None and self.stationServerThread.isRunning():
            return self.stationServer
        else:
            return None

    @QtCore.Slot(str, str)
    def _messageReceived(self, message: str, reply: str):
        maxLen = 80
        messageSummary = message[:maxLen]
        if len(message) > maxLen:
            messageSummary += " [...]"
        replySummary = reply[:maxLen]
        if len(reply) > maxLen:
            replySummary += " [...]"
        self.log(f"Server received: {message}", LogLevels.debug)
        self.log(f"Server replied: {reply}", LogLevels.debug)
        self.serverStatus.addMessageAndReply(messageSummary, replySummary)

    def addInstrumentToGui(self, instrumentBluePrint: InstrumentModuleBluePrint):
        """Add an instrument to the station list."""
        self.stationList.addInstrument(instrumentBluePrint)

    def removeInstrumentFromGui(self, name: str):
        """Remove an instrument from the station list."""
        self.stationList.removeObject(name)

    def refreshStationComponents(self):
        """clear and re-populate the widget holding the station components, using
        the objects that are currently registered in the station."""
        self.stationList.clear()


        # for _, obj in self.station.components.items():
        #     self.stationList.addObject(obj)
        #
        # for i in range(self.stationList.topLevelItemCount()):
        #     item = self.stationList.topLevelItem(i)
        #     self.stationList.expandItem(item)
        #
        # for i, _ in enumerate(self.stationList.cols):
        #     self.stationList.resizeColumnToContents(i)

    def loadParamsFromFile(self):
        """load the values of all parameters present in the server's params json file
        to parameters registered in the station (incl those in instruments)."""

        # self.log(f"Loading parameters from file: "
        #          f"{os.path.abspath(self._paramValuesFile)}", LogLevels.info)
        # serialize.loadParamsFromFile(self._paramValuesFile, self.station)

    def saveParamsToFile(self):
        """save the values of all parameters registered in the station (incl
         those in instruments) to the server's param json file."""

        # self.log(f"Saving parameters to file: "
        #          f"{os.path.abspath(self._paramValuesFile)}", LogLevels.info)
        # serialize.saveParamsToFile(self.station, self._paramValuesFile)

    @QtCore.Slot(str)
    def displayComponentInfo(self, name: Union[str, None]):
        if name is not None:
            bp = self.client.getBluePrint(name)
        else:
            bp = None
        self.stationObjInfo.setObject(bp)


def startServerGuiApplication(port: int = DEFAULT_PORT) -> "ServerGui":
    """Create a server gui window.
    """
    window = ServerGui(startServer=True, serverPort=port)
    window.show()
    return window


class EmbeddedClient(QtClient):
    """A simple client we can use to communicate with the server object
    inside the server application."""

    @QtCore.Slot(str)
    def start(self, addr: str):
        self.addr = "tcp://localhost:" + addr.split(':')[-1]
        self.connect()

    @QtCore.Slot(str)
    def sendMessage(self, msg: str):
        logger.debug(f"Test client sending request: {msg}")
        reply = self.ask(msg)
        logger.debug(f"Test client received reply: {reply}")


def bluePrintToHtml(bp: Union[ParameterBluePrint, InstrumentModuleBluePrint]):
    if isinstance(bp, ParameterBluePrint):
        return parameterToHtml(bp, headerLevel=1)
    else:
        return instrumentToHtml(bp)


def parameterToHtml(bp: ParameterBluePrint, headerLevel=None):
    ret = ""
    if headerLevel is not None:
        ret = f"<h{headerLevel}>{bp.name}</h{headerLevel}>"

    ret += f"""
<ul>
    <li><b>Type:</b> {bp.parameter_class} ({bp.base_class})</li>
    <li><b>Unit:</b> {bp.unit}</li>
    <li><b>Validator:</b> {html.escape(str(bp.vals))}</li>
    <li><b>Doc:</b> {html.escape(bp.docstring)}</li>
</ul>
    """
    return ret


def instrumentToHtml(bp: InstrumentModuleBluePrint):
    ret = f"""
<h1>{bp.name}</h1>
<ul>
    <li><b>Type:</b> {bp.instrument_module_class} ({bp.base_class}) </li>
    <li><b>Doc:</b> {html.escape(bp.docstring)}</li>
</ul>
"""

    ret += """<h2>Parameters:</h2>
<ul>
    """
    for pn in sorted(bp.parameters):
        pbp = bp.parameters[pn]
        ret += f"<li>{parameterToHtml(pbp, 2)}</li>"
    ret += "</ul>"

    ret += """<h2>Methods:</h2>
<ul>
"""
    for pn in sorted(bp.methods):
        mbp = bp.methods[pn]
        ret += f"""
<li>
    <h3>{mbp.name}</h3>
    <ul>
        <li><b>Call signature:</b> {html.escape(str(mbp.call_signature))}</li>
        <li><b>Doc:</b> {html.escape(mbp.docstring)}</li>
    </ul>
</li>
"""
    ret += "</ul>"

    return ret