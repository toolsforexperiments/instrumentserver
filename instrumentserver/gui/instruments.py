import json
import logging
import inspect
from pprint import pprint
from typing import Optional, Any, List, Tuple, Union, Callable, Dict, Type

from instrumentserver.gui.misc import AlertLabelGreen
from qcodes import Parameter, Instrument

from . import parameters, keepSmallHorizontally
from .base_instrument import InstrumentDisplayBase, ItemBase, InstrumentModelBase, InstrumentTreeViewBase, DelegateBase
from .parameters import ParameterWidget, AnyInput, AnyInputForMethod
from .. import QtWidgets, QtCore, QtGui
from ..blueprints import ParameterBroadcastBluePrint
from ..client import ProxyInstrument, SubClient
from ..helpers import stringToArgsAndKwargs, nestedAttributeFromString
from ..params import ParameterManager, paramTypeFromName, ParameterTypes, parameterTypes
from ..serialize import toParamDict
from ast import literal_eval

# TODO: all styles set through a global style sheet.
# TODO: [maybe] add a column for information on valid input values?

logger = logging.getLogger(__name__)


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
        self.nameEdit.returnPressed.connect(self.addButton.click)
        self.valueEdit.returnPressed.connect(self.addButton.click)
        self.unitEdit.returnPressed.connect(self.addButton.click)
        layout.addWidget(self.addButton, 0, 6, 1, 1)
        self.addButton.setAutoDefault(True)

        self.clearButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"),
            ' Clear',
            parent=self)

        self.clearButton.setAutoDefault(True)
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


class MethodDisplay(QtWidgets.QWidget):
    #: Signal(str)
    #: emitted when the widget runs a function and fails. Emits the exception as a string.
    runFailed = QtCore.Signal(str)

    #: Signal(str)
    #: emitted when the widget runs a function and is successful. Emits the return value as a string.
    runSuccessful = QtCore.Signal(str)

    def __init__(self, fun, fullName=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fun = fun

        # Only used for logging purposes.
        self.fullName = fullName

        self.anyInput = AnyInputForMethod()
        self.anyInput.input.setPlaceholderText(str(inspect.signature(fun)))
        self.anyInput.input.setToolTip(self.getTooltipFromFun(fun))
        self.anyInput.input.returnPressed.connect(self.runFun)

        self.runButton = QtWidgets.QPushButton("Run", parent=self)
        self.runButton.clicked.connect(self.runFun)

        self.alertLabel = AlertLabelGreen(parent=self)
        self.runFailed.connect(self.alertLabel.setAlert)
        self.runSuccessful.connect(self.alertLabel.setSuccssefulAlert)

        self._layout = QtWidgets.QHBoxLayout(self)
        self.setLayout(self._layout)
        self._layout.addWidget(self.anyInput)
        self._layout.addWidget(self.runButton)
        self._layout.addWidget(self.alertLabel)

        self._layout.setContentsMargins(1, 1, 1, 1)

    @QtCore.Slot()
    def runFun(self):
        try:
            args, kwargs = self.anyInput.value()
            if kwargs is not None:
                ret = self.fun(*args, **kwargs)
            else:
                if isinstance(args, list) or isinstance(args, tuple) or args != '':
                    ret = self.fun(*args)
                else:
                    ret = self.fun()
            self.runSuccessful.emit(str(ret))
            logger.info(f"'{self.fullName}' returned: {ret}")

        except Exception as e:
            self.runFailed.emit(str(e))
            logger.warning(f"'{self.fullName}' Raised the following execution: {e}")

    @classmethod
    def getTooltipFromFun(cls, fun: Callable):
        """
        Returns the signature of the function with its documentation underneath.
        """
        sig = inspect.signature(fun)
        doc = inspect.getdoc(fun)
        return str(sig) + '\n\n' + str(doc)


# ----------------- Parameters Display Classes - Beginning -----------------------------

class ItemParameters(ItemBase):
    def __init__(self, unit='', **kwargs):
        super().__init__(**kwargs)

        self.unit = unit


class ParameterDelegate(DelegateBase):
    """
    The delegate for the InstrumentParameters widget.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Stores as key the name of the item and as value the widget that the delegate creates.
        # used to keep a reference to the widget.
        self.parameters: Dict[str, QtWidgets.QWidget] = {}

    def createEditor(self, widget: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        """
        This is the function that is supposed to create the widget. It should return it.
        """
        item = self.getItem(index)
        element = item.element

        ret = ParameterWidget(element, widget)
        self.parameters[item.name] = ret
        return ret


class ModelParameters(InstrumentModelBase):
    # : Signal(item, object) : Emitted when an item in the model has received a new value, first object is the item's
    # name, second object is its new value
    itemNewValue = QtCore.Signal(object, object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setColumnCount(3)
        self.setHorizontalHeaderLabels([self.attr, 'unit', ''])

        # Live updates items
        self.cliThread = QtCore.QThread()
        self.subClient = SubClient([self.instrument.name])
        self.subClient.moveToThread(self.cliThread)

        self.cliThread.started.connect(self.subClient.connect)
        self.subClient.update.connect(self.updateParameter)

        self.cliThread.start()

    @QtCore.Slot(ParameterBroadcastBluePrint)
    def updateParameter(self, bp: ParameterBroadcastBluePrint):
        fullName = '.'.join(bp.name.split('.')[1:])

        if bp.action == 'parameter-creation':
            if fullName not in self.instrument.list():
                self.instrument.update()
            if fullName in self.instrument.list():
                self.addItem(fullName, element=nestedAttributeFromString(self.instrument, fullName))

        elif bp.action == 'parameter-deletion':
            self.removeItem(fullName)

        elif bp.action == 'parameter-update' or bp.action == 'parameter-call':
            item = self.findItems(fullName, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
            if len(item) == 0:
                self.addItem(fullName, element=nestedAttributeFromString(self.instrument, fullName))
            else:
                # The model can't actually modify the widget since it knows nothing about the view itself.
                self.itemNewValue.emit(item[0].name, bp.value)

    def insertItemTo(self, parent: QtGui.QStandardItem, item):
        if item is not None:
            # A parameter might not have a unit
            unit = ''
            if item.element is not None:
                unit = item.element.unit
            unitItem = QtGui.QStandardItem(unit)
            extraItem = QtGui.QStandardItem()

            if parent == self:
                rowCount = self.rowCount()
                self.setItem(rowCount, 0, item)
                self.setItem(rowCount, 1, unitItem)
                self.setItem(rowCount, 2, extraItem)
            else:
                parent.appendRow([item, unitItem, extraItem])

            self.newItem.emit(item)


class ParametersTreeView(InstrumentTreeViewBase):
    def __init__(self, model, *args, **kwargs):
        super().__init__(model, [2], *args, **kwargs)

        self.delegate = ParameterDelegate(self)

        self.setItemDelegateForColumn(2, self.delegate)
        self.setAllDelegatesPersistent()

    @QtCore.Slot(object, object)
    def onItemNewValue(self, itemName, value):
        widget = self.delegate.parameters[itemName]
        widget.paramWidget.setValue(value)


class InstrumentParameters(InstrumentDisplayBase):
    def __init__(self, instrument, viewType=ParametersTreeView, callSignals: bool = True, **kwargs):
        if 'instrument' in kwargs:
            del kwargs['instrument']
        modelKwargs = {}
        if 'parameters-star' in kwargs:
            modelKwargs['itemsStar'] = kwargs.pop('parameters-star')
        if 'parameters-trash' in kwargs:
            modelKwargs['itemsTrash'] = kwargs.pop('parameters-trash')
        if 'parameters-hide' in kwargs:
            modelKwargs['itemsHide'] = kwargs.pop('parameters-hide')

        super().__init__(instrument=instrument,
                         attr='parameters',
                         itemType=ItemParameters,
                         modelType=ModelParameters,
                         viewType=viewType,
                         callSignals=callSignals,
                         **modelKwargs)

    def connectSignals(self):
        super().connectSignals()
        self.model.itemNewValue.connect(self.view.onItemNewValue)


# ----------------- Parameters Display Classes - Ending --------------------------------

# ----------------- Parameters Manager Classes - Beginning -----------------------------


class ParameterDeleteDelegate(ParameterDelegate):
    #: Signal(str)
    #: Emits the name of the parameter to be deleted when the user presses the delete button.
    removeParameter = QtCore.Signal(str)

    def createEditor(self, widget: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        item = self.getItem(index)
        element = item.element
        rw = self.makeRemoveWidget(item.name, widget)

        ret = ParameterWidget(parameter=element, parent=widget, additionalWidgets=[rw])
        self.parameters[item.name] = ret

        return ret

    def makeRemoveWidget(self, fullName: str, widget: QtWidgets.QWidget):
        w = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"), "", parent=widget)
        w.setStyleSheet("""
            QPushButton { background-color: salmon }
        """)
        w.setToolTip("Delete this parameter")
        keepSmallHorizontally(w)

        w.pressed.connect(lambda: self.removeParameter.emit(fullName))
        return w


class ParameterManagerTreeView(InstrumentTreeViewBase):
    def __init__(self, model, *args, **kwargs):
        super().__init__(model, [2], *args, **kwargs)

        self.delegate = ParameterDeleteDelegate(self)

        self.setItemDelegateForColumn(2, self.delegate)
        self.setAllDelegatesPersistent()

    @QtCore.Slot(object, object)
    def onItemNewValue(self, itemName, value):
        widget = self.delegate.parameters[itemName]
        widget.paramWidget.setValue(value)


class ParameterManagerGui(InstrumentParameters):
    #: Signal(str) --
    #: emitted when there's an error during parameter creation.
    parameterCreationError = QtCore.Signal(str)

    #: Signal() --
    #:  emitted when a parameter was created successfully
    parameterCreated = QtCore.Signal()

    def __init__(self, instrument: Union[ProxyInstrument, ParameterManager], **kwargs):
        super().__init__(instrument, viewType=ParameterManagerTreeView, callSignals=False, **kwargs)
        self.addParam = AddParameterWidget(parent=self)
        self.layout().addWidget(self.addParam)
        self.connectSignals()

    def connectSignals(self):
        super().connectSignals()
        self.view.delegate.removeParameter.connect(self.removeParameter)
        self.addParam.newParamRequested.connect(self.addParameter)
        self.parameterCreationError.connect(self.addParam.setError)
        self.parameterCreated.connect(self.addParam.clear)

    def makeToolbar(self):
        toolbar = super().makeToolbar()

        toolbar.addSeparator()

        loadParamAction = toolbar.addAction(
            QtGui.QIcon(":/icons/load.svg"),
            "Load parameters from file",
        )
        loadParamAction.triggered.connect(lambda x: self.loadFromFile())

        saveParamAction = toolbar.addAction(
            QtGui.QIcon(":/icons/save.svg"),
            "Save parameters to file",
        )
        saveParamAction.triggered.connect(lambda x: self.saveToFile())

        return toolbar

    def removeParameter(self, fullName: str):
        if self.instrument.has_param(fullName):
            self.instrument.remove_parameter(fullName)

    def addParameter(self, fullName, value, unit):
        try:
            # Validators are commented out until they can be serialized.
            self.instrument.add_parameter(fullName, initial_value=value,
                                          unit=unit, )  # vals=vals)
            self.parameterCreated.emit()
        except Exception as e:
            self.parameterCreationError.emit(f"Could not create parameter."
                                             f"Adding parameter raised"
                                             f"{type(e)}: {e.args}")
            return

    @QtCore.Slot()
    def loadFromFile(self):
        try:
            self.instrument.fromFile(deleteMissing=False)
            self.refreshAll()

        except Exception as e:
            logger.info(f"Loading failed. {type(e)}: {e.args}")

    @QtCore.Slot()
    def saveToFile(self):
        try:
            self.instrument.toFile()
        except Exception as e:
            logger.info(f"Saving failed. {type(e)}: {e.args}")


# ----------------- Parameters Manager Classes - Ending --------------------------------

# ----------------- Methods Display Classes - Beginning --------------------------------


class MethodsModel(InstrumentModelBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels([self.attr, 'Arguments & Run'])

    def insertItemTo(self, parent, item):
        if item is not None:
            extraItem = QtGui.QStandardItem()

            if parent == self:
                rowCount = self.rowCount()
                self.setItem(rowCount, 0, item)
                self.setItem(rowCount, 1, extraItem)
            else:
                parent.appendRow([item, extraItem])

            self.newItem.emit(item)


class MethodsDelegate(DelegateBase):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.methods = {}

    def createEditor(self, widget: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        item = self.getItem(index)
        element = item.element
        ret = MethodDisplay(element, item.name, parent=widget)

        # connecting the widget with the clear alert signal
        self.parent().clearAlertsAction.triggered.connect(ret.alertLabel.clearAlert)

        self.methods[item.name] = ret
        return ret


class MethodsTreeView(InstrumentTreeViewBase):
    def __init__(self, model, *args, **kwargs):
        super().__init__(model, [1], *args, **kwargs)

        # Adding the clear alert to the context menu
        self.clearAlertsAction = QtWidgets.QAction('Clear alerts')
        self.contextMenu.addSeparator()
        self.contextMenu.addAction(self.clearAlertsAction)

        self.delegate = MethodsDelegate(self)
        self.setItemDelegateForColumn(1, self.delegate)
        self.setAllDelegatesPersistent()


class InstrumentMethods(InstrumentDisplayBase):

    def __init__(self, instrument, **kwargs):
        if 'instrument' in kwargs:
            del kwargs['instrument']

        modelKwargs = {}
        if 'methods-star' in kwargs:
            modelKwargs['itemsStar'] = kwargs.pop('methods-star')
        if 'methods-trash' in kwargs:
            modelKwargs['itemsTrash'] = kwargs.pop('methods-trash')
        if 'methods-hide' in kwargs:
            modelKwargs['itemsHide'] = kwargs.pop('methods-hide')

        super().__init__(instrument=instrument,
                         attr='functions',
                         modelType=MethodsModel,
                         viewType=MethodsTreeView,
                         **modelKwargs)


# ----------------- Methods Display Classes - Ending -----------------------------------


class GenericInstrument(QtWidgets.QWidget):
    """
    Widget that allows the display of real time parameters and changing their values.
    """

    def __init__(self, ins: Union[ProxyInstrument, Instrument], parent=None, **modelKwargs):
        super().__init__(parent=parent)

        self.ins = ins

        self._layout = QtWidgets.QVBoxLayout(self)
        self.setLayout(self._layout)

        self.splitter = QtWidgets.QSplitter(self)
        self.splitter.setOrientation(QtCore.Qt.Vertical)

        self.parametersList = InstrumentParameters(instrument=ins, **modelKwargs)
        self.methodsList = InstrumentMethods(instrument=ins, **modelKwargs)
        self.instrumentNameLabel = QtWidgets.QLabel(f'{self.ins.name} | type: {type(self.ins)}')

        self._layout.addWidget(self.instrumentNameLabel)
        self._layout.addWidget(self.splitter)
        self.splitter.addWidget(self.parametersList)
        self.splitter.addWidget(self.methodsList)
