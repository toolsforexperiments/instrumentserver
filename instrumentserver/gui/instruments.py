from typing import Optional, Any, Dict, List, Tuple, Union

from qcodes import Instrument, Parameter

from .. import QtWidgets, QtCore, QtGui
from ..serialize import toParamDict
from ..params import ParameterManager, paramTypeFromName, ParameterTypes, parameterTypes
from ..helpers import stringToArgsAndKwargs, nestedAttributeFromString
from ..client import ProxyInstrument

from . import parameters, keepSmallHorizontally
from .parameters import ParameterWidget


# TODO: all styles set through a global style sheet.
# TODO: [maybe] add a column for information on valid input values?


class ParameterManagerGui(QtWidgets.QWidget):
    #: Signal(str) --
    #: emitted when there's an error during parameter creation.
    parameterCreationError = QtCore.Signal(str)

    #: Signal() --
    #  emitted when a parameter was created successfully
    parameterCreated = QtCore.Signal()

    def __init__(self, ins: Union[ParameterManager, ProxyInstrument],
                 parent: Optional[QtWidgets.QWidget] = None,
                 makeAvailable: Optional[List[Tuple[str, Any]]] = []):

        super().__init__(parent)

        for (modName, mod) in makeAvailable:
            setattr(parameters, modName, mod)

        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        self._instrument = ins
        self._widgets = {}
        self._removeWidgets = {}

        # make the main layout and set up all the widgets
        layout = QtWidgets.QVBoxLayout(self)

        # toolbar: refreshing, filtering, and some control over the tree
        self.toolbar = self._makeToolbar()
        layout.addWidget(self.toolbar)

        # the main widget for displaying the parameters
        self.plist = ParameterList(self)
        layout.addWidget(self.plist)

        # at the bottom, a widget to add new parameters
        self.addParam = AddParameterWidget(self)
        self.addParam.newParamRequested.connect(self.addParameter)
        self.parameterCreationError.connect(self.addParam.setError)
        self.parameterCreated.connect(self.addParam.clear)
        layout.addWidget(self.addParam)

        self.setLayout(layout)
        self.populateList()
        
    def _makeToolbar(self):
        toolbar = QtWidgets.QToolBar(self)
        toolbar.setIconSize(QtCore.QSize(16, 16))

        refreshAction = toolbar.addAction(
            QtGui.QIcon(":/icons/refresh.svg"),
            "refresh all parameters from the instrument",
        )
        refreshAction.triggered.connect(lambda x: self.refreshAll())

        toolbar.addSeparator()

        expandAction = toolbar.addAction(
            QtGui.QIcon(":/icons/expand.svg"),
            "expand the parameter tree",
        )
        expandAction.triggered.connect(lambda x: self.plist.expandAll())

        collapseAction = toolbar.addAction(
            QtGui.QIcon(":/icons/collapse.svg"),
            "collapse the parameter tree",
        )
        collapseAction.triggered.connect(lambda x: self.plist.collapseAll())

        toolbar.addSeparator()

        self.filterEdit = QtWidgets.QLineEdit(self)
        self.filterEdit.textChanged.connect(self.filterParameters)
        toolbar.addWidget(QtWidgets.QLabel('Filter:'))
        toolbar.addWidget(self.filterEdit)

        return toolbar

    def getParameter(self, fullName: str):
        param = nestedAttributeFromString(self._instrument, fullName)
        return param

    def populateList(self):
        for pname in sorted(toParamDict([self._instrument])):
            fullName = '.'.join(pname.split('.')[1:])
            param = self.getParameter(fullName)
            self.addParameterWidget(fullName, param)

        self.plist.expandAll()
        self.plist.resizeColumnToContents(0)
        self.plist.resizeColumnToContents(1)

    def addParameter(self, fullName: str, value: Any, unit: str,
                     parameterType: ParameterTypes,
                     valsArgs: Optional[str] = '') -> None:
        """Add a new parameter to the instrument.

        :param fullName: parameter name, incl. submodules, excl. instrument name.
        :param value: the value of the parameter, as string.
            if the parameter type is not string, must be possible to evaluate to
            the right type.
        :param unit: physical unit of the parameter
        :param parameterType: determines the validator we will use.
            see: :class:`.params.ParameterType`.
        :param valsArgs: a string that will be converted as args and kwargs for
            creation of the validator. see :func:`.helpers.stringToArgsAndKwargs`.
        :return: None
        """
        try:
            args, kw = stringToArgsAndKwargs(valsArgs)
        except ValueError as e:
            self.parameterCreationError.emit(f'Cannot create parameter. Validator'
                                             f'arguments invalid (how ironic):'
                                             f'{e.args}')
            return
        vals = parameterTypes[parameterType]['validatorType'](*args, **kw)

        if parameterType is not ParameterTypes.string:
            try:
                value = eval(value)
            except Exception as e:
                value = str(value)

        try:
            self._instrument.add_parameter(fullName, initial_value=value,
                                           unit=unit, vals=vals)
        except Exception as e:
            self.parameterCreationError.emit(f"Could not create parameter."
                                             f"Adding parameter raised"
                                             f"{type(e)}: {e.args}")
            return

        # we cannot get the real instrument .parameter() function because we
        # want the proxy parameter, of course.
        param = self.getParameter(fullName)
        self.addParameterWidget(fullName, param)
        self.parameterCreated.emit()

    def addParameterWidget(self, fullName: str, parameter: Parameter):
        item = self.plist.addParameter(parameter, fullName)

        rw = self.makeRemoveWidget(fullName)
        self._removeWidgets[fullName] = rw

        w = ParameterWidget(parameter, parent=self, additionalWidgets=[rw])
        self._widgets[fullName] = w
        self.plist.setItemWidget(item, 2, w)

    def makeRemoveWidget(self, fullName: str):
        w = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"), "", parent=self)
        w.setStyleSheet("""
            QPushButton { background-color: salmon }
        """)
        w.setToolTip("Delete this parameter")
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

        if self._instrument.has_param(fullName):
            self._instrument.remove_parameter(fullName)

        self.plist.removeEmptyContainers()

    def refreshAll(self):
        insParams = self._instrument.list()

        for n in insParams:
            items = self.plist.findItems(
                n, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
            if len(items) == 0:
                self.addParameterWidget(n, self.getParameter(n))
            else:
                w = self.plist.itemWidget(items[0], 2)
                w.setWidgetFromParameter()

        deleteParams = []
        for pn in self.plist.parameters:
            if pn not in insParams:
                deleteParams.append(pn)
        for pn in deleteParams:
            self.removeParameter(pn)

    def filterParameters(self, filterString: str):
        self.plist.filterItems(filterString)


class ParameterList(QtWidgets.QTreeWidget):

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        self.setColumnCount(2)
        self.setHeaderLabels(['Parameter name', 'Unit', ''])
        self.setHeaderHidden(False)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)

        self.parameters = []
        self.filterString = ''

    def addParameter(self, p: Parameter, fullName: str) \
            -> QtWidgets.QTreeWidgetItem:

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
                newItem = QtWidgets.QTreeWidgetItem([smName, '', ''])
                self._addChildTo(parent, newItem)
                parent = newItem
            else:
                parent = items[0]

        paramItem = QtWidgets.QTreeWidgetItem([fullName, f"{p.unit}", ''])
        self._addChildTo(parent, paramItem)
        self.parameters.append(fullName)
        self.filterItems(self.filterString)
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

        def check(parent):
            parent: Union[QtWidgets.QTreeWidgetItem, ParameterList]
            removeList = []

            nChildren = parent.childCount() if \
                isinstance(parent, QtWidgets.QTreeWidgetItem) else \
                parent.topLevelItemCount()

            for i in range(nChildren):
                if isinstance(parent, QtWidgets.QTreeWidgetItem):
                    item = parent.child(i)
                else:
                    item = parent.topLevelItem(i)

                if item.text(0) not in self.parameters:
                    check(item)
                    nGrandChildren = item.childCount()
                    if nGrandChildren == 0:
                        removeList.append(item)

            for item in removeList:
                if isinstance(parent, QtWidgets.QTreeWidgetItem):
                    parent.removeChild(item)
                else:
                    parent.takeTopLevelItem(parent.indexOfTopLevelItem(item))

        check(self)

    def filterItems(self, filterString: str):
        self.filterString = filterString.strip()
        for pn in self.parameters:
            self.showItem(pn, self.filterString in pn)

        def hideEmptyParent(parent):
            hideme = True
            nChildren = parent.childCount() if \
                isinstance(parent, QtWidgets.QTreeWidgetItem) else \
                parent.topLevelItemCount()

            for i in range(nChildren):
                if isinstance(parent, QtWidgets.QTreeWidgetItem):
                    item = parent.child(i)
                else:
                    item = parent.topLevelItem(i)
                if item.text(0) not in self.parameters:
                    hideEmptyParent(item)
                if not item.isHidden():
                    hideme = False

            if isinstance(parent, QtWidgets.QTreeWidgetItem):
                parent.setHidden(hideme)

        hideEmptyParent(self)

    def showItem(self, name: str, show: bool):
        item = self.findItems(
            name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)[0]
        item.setHidden(not show)


class AddParameterWidget(QtWidgets.QWidget):
    """A widget that allows parameter creation.

    :param parent: parent widget
    :param typeInput: if ``True``, add input fields for creating a value
        validator.
    """

    #: Signal(str, str, str, ParameterTypes, str)
    newParamRequested = QtCore.Signal(str, str, str, ParameterTypes, str)

    #: Signal(str)
    invalidParamRequested = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None,
                 typeInput: bool = False):
        super().__init__(parent)

        self.typeInput = typeInput

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.nameEdit = QtWidgets.QLineEdit(self)
        lbl = QtWidgets.QLabel("Name:")
        lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        layout.addWidget(lbl, 0, 0)
        layout.addWidget(self.nameEdit, 0, 1)

        self.valueEdit = QtWidgets.QLineEdit(self)
        lbl = QtWidgets.QLabel("Value:")
        lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        layout.addWidget(lbl, 0, 2)
        layout.addWidget(self.valueEdit, 0, 3)

        self.unitEdit = QtWidgets.QLineEdit(self)
        lbl = QtWidgets.QLabel("Unit:")
        lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        layout.addWidget(lbl, 0, 4)
        layout.addWidget(self.unitEdit, 0, 5)

        if typeInput:
            self.typeSelect = QtWidgets.QComboBox(self)
            names = []
            for t, v in parameterTypes.items():
                names.append(v['name'])
            for n in sorted(names):
                self.typeSelect.addItem(n)
            self.typeSelect.setCurrentText(parameterTypes[ParameterTypes.numeric]['name'])
            lbl = QtWidgets.QLabel("Type:")
            lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            layout.addWidget(lbl, 1, 0)
            layout.addWidget(self.typeSelect, 1, 1)

            self.valsArgsEdit = QtWidgets.QLineEdit(self)
            lbl = QtWidgets.QLabel('Type opts.:')
            lbl.setToolTip("Optional, for constraining parameter values."
                           "Allowed args and defaults:\n"
                           " - 'Numeric': min_value=-1e18, max_value=1e18\n"
                           " - 'Integer': min_value=-inf, max_value=inf\n"
                           " - 'String': min_length=0, max_length=1e9\n"
                           'See qcodes.utils.validators for details.')
            lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            layout.addWidget(lbl, 1, 2)
            layout.addWidget(self.valsArgsEdit, 1, 3)

        self.addButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/plus-square.svg"),
            ' Add',
            parent=self)

        self.addButton.clicked.connect(self.requestNewParameter)
        layout.addWidget(self.addButton, 0, 6, 1, 1)

        self.clearButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"),
            ' Clear',
            parent=self)

        self.clearButton.clicked.connect(self.clear)
        layout.addWidget(self.clearButton, 0, 7, 1, 1)

        self.setLayout(layout)
        self.invalidParamRequested.connect(self.setError)

    @QtCore.Slot()
    def clear(self):
        self.clearError()
        self.nameEdit.setText('')
        self.valueEdit.setText('')
        self.unitEdit.setText('')
        if self.typeInput:
            self.typeSelect.setCurrentText(parameterTypes[ParameterTypes.numeric]['name'])
            self.valsArgsEdit.setText('')

    @QtCore.Slot(bool)
    def requestNewParameter(self, _):
        self.clearError()

        name = self.nameEdit.text().strip()
        if len(name) == 0:
            self.invalidParamRequested.emit("Name must not be empty.")
            return
        value = self.valueEdit.text()
        unit = self.unitEdit.text()

        if hasattr(self, 'typeSelect'):
            ptype = paramTypeFromName(self.typeSelect.currentText())
            valsArgs = self.valsArgsEdit.text()
        else:
            ptype = ParameterTypes.any
            valsArgs = ''

        self.newParamRequested.emit(name, value, unit, ptype, valsArgs)

    @QtCore.Slot(str)
    def setError(self, message: str):
        self.addButton.setStyleSheet("""
        QPushButton { background-color: red }
        """)
        self.addButton.setToolTip(message)

    def clearError(self):
        self.addButton.setStyleSheet("")
        self.addButton.setToolTip("")

