from typing import Optional, Any, Dict

from qcodes import Parameter

from .. import QtWidgets, QtCore, QtGui
from ..serialize import toParamDict
from ..param_manager import ParameterManager

from .parameters import ParameterWidget
from . import keepSmallHorizontally

# TODO: adding parameters
# TODO: refreshing parameters
# TODO: loading/saving parameters? profiles?
# TODO: filter


class ParameterManagerGui(QtWidgets.QWidget):

    def __init__(self, ins: ParameterManager,
                 parent: Optional[QtWidgets.QWidget] = None):

        super().__init__(parent)

        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        self._instrument = ins
        self._widgets = {}
        self._removeWidgets = {}

        self.plist = ParameterList(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.plist)
        self.setLayout(layout)

        self.populateList()

    def populateList(self):
        for pname in sorted(toParamDict([self._instrument])):
            fullName = '.'.join(pname.split('.')[1:])
            param = self._instrument.parameter(fullName)
            self.addParameterWidget(fullName, param)

        self.plist.expandAll()
        self.plist.resizeColumnToContents(0)
        self.plist.resizeColumnToContents(1)
        self.plist.resize(self.plist.sizeHint())
        self.resize(self.minimumSizeHint())

    def addParameterWidget(self, fullName: str, parameter: Parameter):
        item = self.plist.addParameter(parameter, fullName)

        rw = self.makeRemoveWidget(fullName)
        self._removeWidgets[fullName] = rw

        w = ParameterWidget(parameter, parent=self, additionalWidgets=[rw])
        self._widgets[fullName] = w
        self.plist.setItemWidget(item, 1, w)

    def makeRemoveWidget(self, fullName: str):
        w = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"), "", parent=self)
        keepSmallHorizontally(w)

        w.pressed.connect(lambda: self.removeParameter(fullName))
        return w

    def removeParameter(self, fullName: str):
        items = self.plist.findItems(
            fullName, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
        if len(items) > 0:
            item = items[0]
            parent = item.parent()
            if isinstance(parent, QtWidgets.QTreeWidgetItem):
                parent.removeChild(item)
            else:
                self.plist.takeTopLevelItem(self.plist.indexOfTopLevelItem(item))
            del item

        if fullName in self.plist.parameters:
            self.plist.parameters.remove(fullName)

        if fullName in self._widgets:
            self._widgets[fullName].deleteLater()
            del self._widgets[fullName]

        if fullName in self._removeWidgets:
            self._removeWidgets[fullName].deleteLater()
            del self._removeWidgets[fullName]

        self._instrument.remove(fullName)
        self.plist.removeEmptyContainers()


class ParameterList(QtWidgets.QTreeWidget):

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        self.setColumnCount(2)
        self.setHeaderLabels(['Parameter name', ''])
        self.setHeaderHidden(False)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)

        self.parameters = []

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
        self.parameters.append(fullName)
        return paramItem

    @staticmethod
    def _addChildTo(parent, child):
        if isinstance(parent, ParameterList):
            parent.addTopLevelItem(child)
        else:
            parent.addChild(child)

    def removeEmptyContainers(self):
        """Delete all items that are not parameters and don't contain any
        parameters."""

        removeList = []

        def check(parent):
            parent: QtWidgets.QTreeWidgetItem
            for i in range(parent.childCount()):
                item_ = parent.child(i)
                if item_.text(0) not in self.parameters:
                    check(item_)
            if parent.childCount() == 0:
                removeList.append(parent.text(0))

        for k in range(self.topLevelItemCount()):
            item = self.topLevelItem(k)
            if item.text(0) not in self.parameters:
                check(item)

        for k in removeList:
            item = self.findItems(
                k, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)[0]
            parent = item.parent()
            if isinstance(parent, QtWidgets.QTreeWidgetItem):
                parent.removeChild(item)
            else:
                self.takeTopLevelItem(self.indexOfTopLevelItem(item))
            del item
