import html
import logging
import os
import time
from typing import Union, Optional, Any

from instrumentserver.client import QtClient
from instrumentserver.log import LogLevels, LogWidget, log

from .core import (
    StationServer,
    InstrumentModuleBluePrint, ParameterBluePrint
)
from .. import QtCore, QtWidgets, QtGui

logger = logging.getLogger(__name__)


# TODO: parameter file location should be optionally configurable
# TODO: add an option to save one file per station component
# TODO: allow for user shutdown of the server.
# TODO: use the safeword approach to configure the server on the fly
#   allowing users to shut down, etc, set other internal properties of
#   of the server object.
# TODO: add a monitor that refreshes the station now and then and pings the server
# TODO: the station info should be collapsable (tree?) and searchable.


class StationList(QtWidgets.QTreeWidget):
    """A widget that displays all objects in a qcodes station."""

    cols = ['Name', 'Type']

    #: Signal(str) --
    #: emitted when a parameter or Instrument is selected.
    componentSelected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(len(self.cols))
        self.setHeaderLabels(self.cols)
        self.setSortingEnabled(True)
        self.clear()

        self.itemSelectionChanged.connect(self._processSelection)

    def addInstrument(self, bp: InstrumentModuleBluePrint):
        lst = [bp.name, f"{bp.instrument_module_class.split('.')[-1]}"]
        self.addTopLevelItem(QtWidgets.QTreeWidgetItem(lst))
        self.resizeColumnToContents(0)

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

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)

    @QtCore.Slot(object)
    def setObject(self, bp: InstrumentModuleBluePrint):
        self.setHtml(bluePrintToHtml(bp))


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

    def __init__(self, startServer: Optional[bool] = True,
                 **serverKwargs: Any):
        super().__init__()

        self._paramValuesFile = os.path.abspath(os.path.join('.', 'parameters.json'))
        self._bluePrints = {}
        self._serverKwargs = serverKwargs

        self.stationServer = None
        self.stationServerThread = None

        self.setWindowTitle('Instrument server')

        # Central widget is simply a tab container.
        self.tabs = QtWidgets.QTabWidget(self)
        self.setCentralWidget(self.tabs)

        self.stationList = StationList()
        self.stationObjInfo = StationObjectInfo()
        self.stationList.componentSelected.connect(self.displayComponentInfo)

        stationWidgets = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        stationWidgets.addWidget(self.stationList)
        stationWidgets.addWidget(self.stationObjInfo)
        stationWidgets.setSizes([300, 500])
        self.tabs.addTab(stationWidgets, 'Station')

        self.tabs.addTab(LogWidget(level=logging.INFO), 'Log')

        self.serverStatus = ServerStatus()
        self.tabs.addTab(self.serverStatus, 'Server')

        # Toolbar.
        self.toolBar = self.addToolBar('Tools')
        self.toolBar.setIconSize(QtCore.QSize(16, 16))

        # Station tools.
        # The actions must be class parameters so that they are accessible by the tests.
        self.toolBar.addWidget(QtWidgets.QLabel('Station:'))
        self.refreshStationAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/refresh.svg"), 'Refresh', self)
        self.refreshStationAction.triggered.connect(self.refreshStationComponents)
        self.toolBar.addAction(self.refreshStationAction)

        # Parameter tools.
        self.toolBar.addSeparator()
        self.toolBar.addWidget(QtWidgets.QLabel('Params:'))

        self.loadParamsAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/load.svg"), 'Load from file', self)
        self.loadParamsAction.triggered.connect(self.loadParamsFromFile)
        self.toolBar.addAction(self.loadParamsAction)

        self.saveParamsAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/save.svg"), 'Save to file', self)
        self.saveParamsAction.triggered.connect(self.saveParamsToFile)
        self.toolBar.addAction(self.saveParamsAction)

        # A test client, just a simple helper object.
        self.client = EmbeddedClient()
        self.client.recv_timeout = 10_000
        self.serverStatus.testButton.clicked.connect(
            lambda x: self.client.ask("Ping server.")
        )
        if startServer:
            self.startServer()

        # self.refreshStationComponents()

        # development options: they must always be commented out
    #     printSpaceAction = QtWidgets.QAction(QtGui.QIcon(":/icons/code.svg"), 'prints empty space', self)
    #     printSpaceAction.triggered.connect(self._prints_empty_space)
    #     self.toolBar.addAction(printSpaceAction)
    #
    # def _prints_empty_space(self):
    #     print('\n \n \n \n')

    def log(self, message, level=LogLevels.info):
        log(logger, message, level)

    def closeEvent(self, event):
        if hasattr(self, 'stationServerThread'):
            if self.stationServerThread.isRunning():
                self.client.ask(self.stationServer.SAFEWORD)
        event.accept()

    def startServer(self):
        """Start the instrument server in a separate thread."""
        self.stationServer = StationServer(**self._serverKwargs)
        self.stationServerThread = QtCore.QThread()
        self.stationServer.moveToThread(self.stationServerThread)
        self.stationServerThread.started.connect(self.stationServer.startServer)
        self.stationServer.finished.connect(lambda: self.log('ZMQ server closed.'))
        self.stationServer.finished.connect(self.stationServerThread.quit)
        self.stationServer.finished.connect(self.stationServer.deleteLater)

        # Connecting some additional things for messages.
        self.stationServer.serverStarted.connect(self.serverStatus.setListeningAddress)
        self.stationServer.serverStarted.connect(self.client.start)
        self.stationServer.serverStarted.connect(self.refreshStationComponents)
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
        self._bluePrints[instrumentBluePrint.name] = instrumentBluePrint

    def removeInstrumentFromGui(self, name: str):
        """Remove an instrument from the station list."""
        self.stationList.removeObject(name)
        del self._bluePrints[name]

    def refreshStationComponents(self):
        """Clear and re-populate the widget holding the station components, using
        the objects that are currently registered in the station."""
        self.stationList.clear()
        for ins in self.client.list_instruments():
            bp = self.client.getBluePrint(ins)
            self.stationList.addInstrument(bp)
            self._bluePrints[ins] = bp
        self.stationList.resizeColumnToContents(0)

    def loadParamsFromFile(self):
        """Load the values of all parameters present in the server's params json file
        to parameters registered in the station (incl those in instruments)."""

        logger.info(f"Loading parameters from file: "
                    f"{os.path.abspath(self._paramValuesFile)}")
        try:
            self.client.paramsFromFile(self._paramValuesFile)
        except Exception as e:
            logger.error(f"Loading failed. {type(e)}: {e.args}")

    def saveParamsToFile(self):
        """Save the values of all parameters registered in the station (incl
         those in instruments) to the server's param json file."""

        logger.info(f"Saving parameters to file: "
                  f"{os.path.abspath(self._paramValuesFile)}")
        try:
            self.client.paramsToFile(self._paramValuesFile)
        except Exception as e:
            logger.error(f"Saving failed. {type(e)}: {e.args}")

    @QtCore.Slot(str)
    def displayComponentInfo(self, name: Union[str, None]):
        if name is not None and name in self._bluePrints:
            bp = self._bluePrints[name]
        else:
            bp = None
        self.stationObjInfo.setObject(bp)


def startServerGuiApplication(**serverKwargs: Any) -> "ServerGui":
    """Create a server gui window.
    """
    window = ServerGui(startServer=True, **serverKwargs)
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
    def ask(self, msg: str):
        logger.debug(f"Test client sending request: {msg}")
        reply = super().ask(msg)
        logger.debug(f"Test client received reply: {reply}")
        return reply


def bluePrintToHtml(bp: Union[ParameterBluePrint, InstrumentModuleBluePrint]):
    header = f"""<html>
<head>
<style type="text/css">{bpHtmlStyle}</style>
</head>
<body>
    """

    footer = """
</body>
</html>
    """
    if isinstance(bp, ParameterBluePrint):
        return header + parameterToHtml(bp, headerLevel=1) + footer
    else:
        return header + instrumentToHtml(bp) + footer


def parameterToHtml(bp: ParameterBluePrint, headerLevel=None):
    setget = []
    setgetstr = ''
    if bp.gettable:
        setget.append('get')
    if bp.settable:
        setget.append('set')
    if len(setget) > 0:
        setgetstr = f"[{', '.join(setget)}]"

    ret = ""
    if headerLevel is not None:
        ret = f"""<div class="param_container">
<div class="object_name">{bp.name} {setgetstr}</div>"""

    ret += f"""
<ul>
    <li><b>Type:</b> {bp.parameter_class} ({bp.base_class})</li>
    <li><b>Unit:</b> {bp.unit}</li>"""
    # FIXME: We deleted the validator since there is no real easy way of deserializing them. It would be a good idea to
    #  have them here though
    # <li><b>Validator:</b> {html.escape(str(bp.vals))}</li>
    var = """<li><b>Doc:</b> {html.escape(str(bp.docstring))}</li>
</ul>
</div>
    """
    return ret + var


def instrumentToHtml(bp: InstrumentModuleBluePrint):
    ret = f"""<div class="instrument_container">
<div class='instrument_name'>{bp.name}</div>
<ul>
    <li><b>Type:</b> {bp.instrument_module_class} ({bp.base_class}) </li>
    <li><b>Doc:</b> {html.escape(str(bp.docstring))}</li>
</ul>
"""

    ret += """<div class='category_name'>Parameters</div>
<ul>
    """
    for pn in sorted(bp.parameters):
        pbp = bp.parameters[pn]
        ret += f"<li>{parameterToHtml(pbp, 2)}</li>"
    ret += "</ul>"

    ret += """<div class='category_name'>Methods</div>
<ul>
"""
    for mn in sorted(bp.methods):
        mbp = bp.methods[mn]
        ret += f"""
<li>
    <div class="method_container">
    <div class='object_name'>{mbp.name}</div>
    <ul>
        <li><b>Call signature:</b> {html.escape(str(mbp.call_signature_str))}</li>
        <li><b>Doc:</b> {html.escape(str(mbp.docstring))}</li>
    </ul>
    </div>
</li>"""
    ret += "</ul>"

    ret += """
    <div class='category_name'>Submodules</div>
    <ul>
    """
    for sn in sorted(bp.submodules):
        sbp = bp.submodules[sn]
        ret += "<li>" + instrumentToHtml(sbp) + "</li>"
    ret += """
    </ul>
    </div>
    """
    return ret


bpHtmlStyle = """
div.object_name, div.instrument_name, div.category_name { 
    font-weight: bold;
}

div.object_name, div.instrument_name {
    font-family: monospace;
    background: aquamarine;
}

div.instrument_name {
    margin-top: 10px;
    margin-bottom: 10px;
    color: white;
    background: darkblue;
    padding: 10px;
}

div.instrument_container {
    padding: 10px;
}
"""