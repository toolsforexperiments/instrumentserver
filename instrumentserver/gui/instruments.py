from typing import Optional, Any, Dict

from qcodes import Parameter

from .. import QtWidgets, QtCore
from ..serialize import toParamDict
from ..param_manager import ParameterManager

from .parameters import ParameterWidget

# TODO: adding parameters
# TODO: deleting parameters
# TODO: refreshing parameters
# TODO: loading/saving parameters? profiles?
# TODO: filter

class ParameterManagerGui(QtWidgets.QWidget):

    def __init__(self, ins: ParameterManager,
                 parent: Optional[QtWidgets.QWidget] = None):

        super().__init__(parent)

        self.setMinimumWidth(400)
        self.setMinimumHeight(400)

        self._instrument = ins
        self._widgets = {}

        self.plist = ParameterList(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.plist)
        self.setLayout(layout)

        self.populateList()

    def populateList(self):
        for pname in sorted(toParamDict([self._instrument])):
            fullName = '.'.join(pname.split('.')[1:])
            param = self._instrument.parameter(fullName)
            item = self.plist.addParameter(param, fullName)
            w = ParameterWidget(param)
            self._widgets[fullName] = w
            self.plist.setItemWidget(item, 1, w)

        self.plist.expandAll()
        self.plist.resizeColumnToContents(0)
        self.plist.resizeColumnToContents(1)
        self.plist.resize(self.plist.sizeHint())
        self.resize(self.minimumSizeHint())


class ParameterList(QtWidgets.QTreeWidget):

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        self.setColumnCount(2)
        self.setHeaderLabels(['Parameter name', ''])
        self.setHeaderHidden(False)
        self.setSortingEnabled(True)

    def addParameter(self, p: Parameter, fullName: str) -> QtWidgets.QTreeWidgetItem:
        path = fullName.split('.')[:-1]
        paramName = fullName.split('.')[-1]

        parent = self
        smName = None
        for sm in path:
            if smName is None:
                smName = sm
            else:
                smName = smName + f".{sm}"

            items = self.findItems(
                smName, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0
            )
            if len(items) == 0:
                newItem = QtWidgets.QTreeWidgetItem([smName, ''])
                self._addChildTo(parent, newItem)
                parent = newItem
            else:
                parent = items[0]

        paramItem = QtWidgets.QTreeWidgetItem([fullName, ''])
        self._addChildTo(parent, paramItem)
        return paramItem

    def _addChildTo(self, parent, child):
        if isinstance(parent, ParameterList):
            parent.addTopLevelItem(child)
        else:
            parent.addChild(child)


