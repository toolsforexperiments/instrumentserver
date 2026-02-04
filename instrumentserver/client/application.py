from pathlib import Path
from typing import Optional, Union
import sys
import json
import logging
import importlib

from qcodes import Instrument
from qtpy.QtWidgets import QFileDialog, QMenu, QWidget, QSizePolicy, QSplitter
from qtpy.QtGui import QGuiApplication
from qtpy.QtCore import Qt

from instrumentserver import QtCore, QtWidgets, QtGui, getInstrumentserverPath
from instrumentserver.client import QtClient, Client, ClientStation
from instrumentserver.client.proxy import SubClient
from instrumentserver.gui.instruments import GenericInstrument
from instrumentserver.gui.misc import DetachableTabWidget
from instrumentserver.log import LogLevels, LogWidget, log
from instrumentserver.log import logger as get_instrument_logger
from instrumentserver.server.application import StationList, StationObjectInfo
from instrumentserver.blueprints import ParameterBroadcastBluePrint

# instrument class key in configuration files for configurations that will be applied to all instruments
DEFAULT_INSTRUMENT_KEY = "__default__"

logger = get_instrument_logger()
logger.setLevel(logging.INFO)


class ServerWidget(QtWidgets.QWidget):
    def __init__(self, client_station:ClientStation, parent=None):
        super().__init__(parent)
        self.client_station = client_station

        # ---- Form (host/port + label for command) ----
        form = QWidget(self)
        form_layout = QtWidgets.QFormLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)
        form_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        # Non-editable
        self.host = QtWidgets.QLineEdit(self.client_station._host)
        self.host.setReadOnly(True)
        self.port = QtWidgets.QLineEdit(str(self.client_station._port))
        self.port.setReadOnly(True)

        self._tint_readonly(self.host)
        self._tint_readonly(self.port)

        # Command editor
        self.cmd = QtWidgets.QPlainTextEdit()
        self.cmd.setPlaceholderText("THIS IS NOT WORKING YET!!!")
        self.cmd.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.cmd.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        rows = 6
        lh = self.cmd.fontMetrics().lineSpacing()
        self.cmd.setFixedHeight(lh * rows + 2 * self.cmd.frameWidth() + 8)
        # Let it grow horizontally
        self.cmd.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        form_layout.addRow("Host:", self.host)
        form_layout.addRow("Port:", self.port)

        # todo: Remote server calls to be implemented
        # form_layout.addRow(QtWidgets.QLabel("Start Server Command:"))
        # form_layout.addRow(self.cmd)

        # ---- Buttons
        # restart_button = QtWidgets.QPushButton("Restart")
        # restart_button.clicked.connect(self.restart_server)

        # btns = QtWidgets.QHBoxLayout()
        # btns.addWidget(restart_button)

        # ---- Main layout ----
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(6, 6, 6, 6)
        main.addWidget(form)
        # main.addLayout(btns)
        main.addStretch(1)

    def _tint_readonly(self, le, bg="#f3f6fa"):
        pal = le.palette()
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(bg))
        le.setPalette(pal)

    # def restart_server(self):
        # todo: to be implemented, ssh to server pc and start the server there.
        #   need to close the port if occupied.
        # print(self.cmd.toPlainText())



class ClientStationGui(QtWidgets.QMainWindow):
    def __init__(self, station: ClientStation):
        """
        GUI frontend for viewing and managing instruments in a ClientStation.

        :param station: An instance of ClientStation containing proxy instruments.
                       GUI configuration (hide patterns, etc.) is read from the station's config.
        """
        super().__init__()
        self.setWindowTitle("Instrument Client GUI")
        # Set unique Windows App ID so that this app can have separate taskbar entry than other Qt apps
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("InstrumentServer.ClientStation")
        self.setWindowIcon(QtGui.QIcon(getInstrumentserverPath("resource","icons")+"/client_app_icon.svg"))
        self.station = station
        self.cli = station.client

        # set up the listener thread and worker that listens to update messages emitted by the server (from all clients)
        self.listenerThread = QtCore.QThread()
        self.listener = SubClient(instruments=None, sub_host=self.cli.host, sub_port=self.cli.port+1)
        self.listener.moveToThread(self.listenerThread)
        self.listenerThread.started.connect(self.listener.connect)
        self.listener.finished.connect(self.listenerThread.quit)
        self.listener.finished.connect(self.listener.deleteLater)
        self.listener.finished.connect(self.listenerThread.deleteLater)
        self.listener.update.connect(self.listenerEvent)
        self.listenerThread.start()

        self.instrumentTabsOpen = {}

        # --- main tabs
        self.tabs = DetachableTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.onTabClosed.connect(self.onTabDeleted)
        self.tabs.currentChanged.connect(self.onTabChanged)

        # --- client station
        self.stationList = StationList() # instrument list
        self.stationObjInfo = StationObjectInfo() # instrument docs

        for inst in self.station.instruments.values():
            self.stationList.addInstrument(inst.bp)
        self.stationList.componentSelected.connect(self._displayComponentInfo)
        self.stationList.itemDoubleClicked.connect(self.openInstrumentTab)
        self.stationList.closeRequested.connect(self.closeInstrument)

        stationWidgets = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        stationWidgets.addWidget(self.stationList)
        stationWidgets.addWidget(self.stationObjInfo)
        stationWidgets.setSizes([200, 500])

        self.tabs.addUnclosableTab(stationWidgets, 'Station')

        self.addParameterLoadSaveToolbar()

        # --- log widget
        self.log_widget = LogWidget(level=logging.INFO)
        self.tabs.addUnclosableTab(self.log_widget, 'Log')

        # --- server widget
        self.server_widget = ServerWidget(self.station)
        self.tabs.addUnclosableTab(self.server_widget, 'Server')


        # adjust window size
        screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
        width = int(screen_geometry.width() * 0.3)  # 30% of screen width
        height = int(screen_geometry.height() * 0.7)  # 70% of screen height
        self.resize(width, height)

    @QtCore.Slot(ParameterBroadcastBluePrint)
    def listenerEvent(self, message: ParameterBroadcastBluePrint):
        if message.action == 'parameter-update':
            logger.info(f"{message.action}: {message.name}: {message.value}")

    def openInstrumentTab(self, item: QtWidgets.QListWidgetItem, index: int):
        """
        Gets called when the user double clicks and item of the instrument list.
         Adds a new generic instrument GUI window to the tab bar.
         If the tab already exists switches to that one.
        """
        name = item.text(0)
        if name not in self.instrumentTabsOpen:
            instrument = self.station.get_instrument(name)

            # Get GUI config from station config (patterns already merged by config.py)
            instrument_config = self.station.full_config.get(name, {})
            gui_config = instrument_config.get('gui', {})
            gui_kwargs = gui_config.get('kwargs', {})

            widgetClass = GenericInstrument

            # Check if a custom GUI type is specified
            if 'type' in gui_config:
                try:
                    # import the widget
                    moduleName = '.'.join(gui_config['type'].split('.')[:-1])
                    widgetClassName = gui_config['type'].split('.')[-1]
                    module = importlib.import_module(moduleName)
                    widgetClass = getattr(module, widgetClassName)
                except (ImportError, AttributeError) as e:
                    logger.warning(f"Failed to load custom GUI '{gui_config['type']}' for '{name}': {e}. Using default GenericInstrument.")
                    widgetClass = GenericInstrument

            ins_widget = widgetClass(instrument, parent=self, sub_host=self.cli.host, sub_port=self.cli.port+1,
                                     **gui_kwargs)

            # add tab
            ins_widget.setObjectName(name)
            index = self.tabs.addTab(ins_widget, name)
            self.tabs.setCurrentIndex(index)
            self.instrumentTabsOpen[name] = ins_widget

        elif name in self.instrumentTabsOpen:
            self.tabs.setCurrentWidget(self.instrumentTabsOpen[name])

    @QtCore.Slot(str)
    def _displayComponentInfo(self, name: Union[str, None]):
        if name is not None:
            bp = self.station[name].bp
        else:
            bp = None
        self.stationObjInfo.setObject(bp)

    @QtCore.Slot(int)
    def onTabChanged(self, index):
        widget = self.tabs.widget(index)
        # if instrument tab is not in 'instrumentTabsOpen' yet, tab must be just open, in this case the constructor
        # of the parameter widget should have already called refresh, so we don't have to do that again.
        if hasattr(widget, "parametersList") and (widget.objectName() in self.instrumentTabsOpen):
            widget.parametersList.model.refreshAll()

    @QtCore.Slot(str)
    def onTabDeleted(self, name: str) -> None:
        if name in self.instrumentTabsOpen:
            del self.instrumentTabsOpen[name]

    def addParameterLoadSaveToolbar(self):
        # --- toolbar basics ---
        self.toolBar = QtWidgets.QToolBar("Params", self)
        self.toolBar.setIconSize(QtCore.QSize(22, 22))
        self.toolBar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.addToolBar(self.toolBar)

        # --- composite path widget
        pathWidget = QtWidgets.QWidget(self.toolBar)
        pathLayout = QtWidgets.QHBoxLayout(pathWidget)
        pathLayout.setContentsMargins(0, 0, 0, 0)
        pathLayout.setSpacing(6)

        lbl = QtWidgets.QLabel("Params:", pathWidget)

        self.paramPathEdit = QtWidgets.QLineEdit(pathWidget)
        self.paramPathEdit.setPlaceholderText("Parameter file path")
        self.paramPathEdit.setText(str(Path.cwd()/"client_params.json"))
        self.paramPathEdit.setClearButtonEnabled(True)
        self.paramPathEdit.setMinimumWidth(280)
        h = self.paramPathEdit.fontMetrics().height() + 10
        self.paramPathEdit.setFixedHeight(h)
        self.paramPathEdit.setTextMargins(6, 0, 6, 0)

        if self.station.param_path:
            self.paramPathEdit.setText(self.station.param_path)

        pathLayout.addWidget(lbl)
        pathLayout.addWidget(self.paramPathEdit, 1)  # stretch
        
        pathAction = QtWidgets.QWidgetAction(self.toolBar)
        pathAction.setDefaultWidget(pathWidget)
        self.toolBar.addAction(pathAction)

        # --- actions ---
        browseBtn = QtWidgets.QAction(QtGui.QIcon(":/icons/folder.svg"), "Browse", self)
        browseBtn.triggered.connect(self.browseParamPath)
        loadAct = QtWidgets.QAction(QtGui.QIcon(":/icons/load.svg"), "Load", self)
        saveAct = QtWidgets.QAction(QtGui.QIcon(":/icons/save.svg"), "Save", self)
        loadAct.triggered.connect(self.loadParams)
        saveAct.triggered.connect(self.saveParams)
        
        self.toolBar.addAction(browseBtn)
        self.toolBar.addAction(loadAct)
        self.toolBar.addAction(saveAct)

        # enter to load
        self.paramPathEdit.returnPressed.connect(self.loadParams)

    @QtCore.Slot()
    def browseParamPath(self):
        filePath, _ = QFileDialog.getOpenFileName(
            self, "Select Parameter File", ".", "JSON Files (*.json);;All Files (*)"
        )
        if filePath:
            self.paramPathEdit.setText(filePath)

    @QtCore.Slot()
    def saveParams(self):
        file_path = self.paramPathEdit.text()
        if not file_path:
            QtWidgets.QMessageBox.warning(self, "No file path", "Please specify a path to save parameters.")
            return
        try:
            self.station.save_parameters(file_path)
            logger.info(f"Saved parameters to {file_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save Error", str(e))

    @QtCore.Slot()
    def loadParams(self):
        file_path = self.paramPathEdit.text()
        if not file_path:
            QtWidgets.QMessageBox.warning(self, "No file path", "Please specify a path to load parameters.")
            return
        try:
            self.station.load_parameters(file_path)
            logger.info(f"Loaded parameters from {file_path}")

            # Refresh all tabs
            for i in range(self.tabs.count()):
                widget = self.tabs.widget(i)
                if hasattr(widget, 'parametersList') and hasattr(widget.parametersList, 'model'):
                    widget.parametersList.model.refreshAll()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))


    @QtCore.Slot(str)
    def closeInstrument(self, name: str):#, item: QtWidgets.QListWidgetItem):
        try:
            # close instrument on server
            self.station.close_instrument(name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Close Error", f"Failed to close '{name}':\n{e}")
            return

        # remove from gui
        self.removeInstrumentFromGui(name)

        logger.info(f"Closed instrument '{name}'")


    def removeInstrumentFromGui(self, name: str):
        """Remove an instrument from the station list."""
        self.stationList.removeObject(name)
        self.stationObjInfo.clear()
        if name in self.instrumentTabsOpen:
            self.tabs.removeTab(self.tabs.indexOf(self.instrumentTabsOpen[name]))
            del self.instrumentTabsOpen[name]

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Cleanup listener thread before closing the window."""
        self.listener.stop()
        self.listenerThread.quit()
        self.listenerThread.wait(3000)  # Wait up to 3 seconds for thread to finish
        super().closeEvent(event)
