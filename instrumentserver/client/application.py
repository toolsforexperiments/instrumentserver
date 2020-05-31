from typing import Optional

from .. import QtCore, QtWidgets, QtGui
from .proxy import QtClient


class InstrumentClientMainWindow(QtWidgets.QMainWindow):

    def __init__(self, client: QtClient, parent=None):
        super().__init__(parent)

        self.client = client
        self._widgets = {}

        # GUI setup
        self.setWindowTitle("Instrument client")
        self.toolBar = QtWidgets.QToolBar('Tools', self)
        self.toolBar.setObjectName("toolBar")
        self.addToolBar(self.toolBar)

        # dock setup
        self.setDockNestingEnabled(True)
        self.setDockOptions(self.AllowNestedDocks | self.AllowTabbedDocks)

        # the central widget is only a dummy for now
        self.setCentralWidget(QtWidgets.QWidget(self))

    def addWidget(self, widget: QtWidgets.QWidget, name: str, visible: bool = True,
                  position: QtCore.Qt.DockWidgetArea_Mask = QtCore.Qt.TopDockWidgetArea):

        widget.setParent(self)
        dock = QtWidgets.QDockWidget(name, self)
        dock.setObjectName(f"dock_{name}")
        dock.setAllowedAreas(QtCore.Qt.AllDockWidgetAreas)
        dock.setWidget(widget)
        self._widgets[name] = dock
        self.addDockWidget(position, dock)
        action = dock.toggleViewAction()
        self.toolBar.addAction(action)
        if not visible:
            dock.close()

