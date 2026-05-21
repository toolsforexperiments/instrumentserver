import inspect
import logging
from typing import Any, Callable, Dict, Optional, Union, cast

from qcodes import Instrument

from instrumentserver.gui.misc import AlertLabelGreen

from .. import DEFAULT_PORT, QtCore, QtGui, QtWidgets
from ..blueprints import ParameterBroadcastBluePrint
from ..client import ProxyInstrument, SubClient
from ..helpers import nestedAttributeFromString
from ..params import ParameterManager, ParameterTypes, parameterTypes, paramTypeFromName
from . import keepSmallHorizontally
from .base_instrument import (
    DelegateBase,
    InstrumentDisplayBase,
    InstrumentModelBase,
    InstrumentTreeViewBase,
    ItemBase,
)
from .parameters import AnyInput, AnyInputForMethod, ParameterWidget

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

    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, typeInput: bool = False
    ) -> None:
        super().__init__(parent)

        self.typeInput = typeInput

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.nameEdit = QtWidgets.QLineEdit(self)
        lbl = QtWidgets.QLabel("Name:")
        lbl.setAlignment(
            cast(
                "QtCore.Qt.Alignment",
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        )
        layout.addWidget(lbl, 0, 0)
        layout.addWidget(self.nameEdit, 0, 1)

        self.valueEdit = QtWidgets.QLineEdit(self)
        lbl = QtWidgets.QLabel("Value:")
        lbl.setAlignment(
            cast(
                "QtCore.Qt.Alignment",
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        )
        layout.addWidget(lbl, 0, 2)
        layout.addWidget(self.valueEdit, 0, 3)

        self.unitEdit = QtWidgets.QLineEdit(self)
        lbl = QtWidgets.QLabel("Unit:")
        lbl.setAlignment(
            cast(
                "QtCore.Qt.Alignment",
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        )
        layout.addWidget(lbl, 0, 4)
        layout.addWidget(self.unitEdit, 0, 5)

        if typeInput:
            self.typeSelect = QtWidgets.QComboBox(self)
            names: list[str] = []
            for t, v in parameterTypes.items():
                names.append(str(v["name"]))
            for n in sorted(names):
                self.typeSelect.addItem(n)
            self.typeSelect.setCurrentText(
                str(parameterTypes[ParameterTypes.numeric]["name"])
            )
            lbl = QtWidgets.QLabel("Type:")
            lbl.setAlignment(
                cast(
                    "QtCore.Qt.Alignment",
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter,
                )
            )
            layout.addWidget(lbl, 1, 0)
            layout.addWidget(self.typeSelect, 1, 1)

            self.valsArgsEdit = QtWidgets.QLineEdit(self)
            lbl = QtWidgets.QLabel("Type opts.:")
            lbl.setToolTip(
                "Optional, for constraining parameter values."
                "Allowed args and defaults:\n"
                " - 'Numeric': min_value=-1e18, max_value=1e18\n"
                " - 'Integer': min_value=-inf, max_value=inf\n"
                " - 'String': min_length=0, max_length=1e9\n"
                "See qcodes.utils.validators for details."
            )
            lbl.setAlignment(
                cast(
                    "QtCore.Qt.Alignment",
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter,
                )
            )
            layout.addWidget(lbl, 1, 2)
            layout.addWidget(self.valsArgsEdit, 1, 3)

        self.addButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/plus-square.svg"), " Add", parent=self
        )

        self.addButton.clicked.connect(self.requestNewParameter)
        self.nameEdit.returnPressed.connect(self.addButton.click)
        self.valueEdit.returnPressed.connect(self.addButton.click)
        self.unitEdit.returnPressed.connect(self.addButton.click)
        layout.addWidget(self.addButton, 0, 6, 1, 1)
        self.addButton.setAutoDefault(True)

        self.clearButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"), " Clear", parent=self
        )

        self.clearButton.setAutoDefault(True)
        self.clearButton.clicked.connect(self.clear)
        layout.addWidget(self.clearButton, 0, 7, 1, 1)

        self.setLayout(layout)
        self.invalidParamRequested.connect(self.setError)

    @QtCore.Slot()
    def clear(self) -> None:
        self.clearError()
        self.nameEdit.setText("")
        self.valueEdit.setText("")
        self.unitEdit.setText("")
        if self.typeInput:
            self.typeSelect.setCurrentText(
                parameterTypes[ParameterTypes.numeric]["name"] # type: ignore[arg-type]
            )
            self.valsArgsEdit.setText("")

    @QtCore.Slot(bool)
    def requestNewParameter(self, _: bool) -> None:
        self.clearError()

        name = self.nameEdit.text().strip()
        if len(name) == 0:
            self.invalidParamRequested.emit("Name must not be empty.")
            return
        value = self.valueEdit.text()
        unit = self.unitEdit.text()

        if hasattr(self, "typeSelect"):
            ptype = paramTypeFromName(self.typeSelect.currentText())
            valsArgs = self.valsArgsEdit.text()
        else:
            ptype = ParameterTypes.any
            valsArgs = ""

        self.newParamRequested.emit(name, value, unit, ptype, valsArgs)

    @QtCore.Slot(str)
    def setError(self, message: str) -> None:
        self.addButton.setStyleSheet("""
        QPushButton { background-color: red }
        """)
        self.addButton.setToolTip(message)

    def clearError(self) -> None:
        self.addButton.setStyleSheet("")
        self.addButton.setToolTip("")


class MethodDisplay(QtWidgets.QWidget):
    #: Signal(str)
    #: emitted when the widget runs a function and fails. Emits the exception as a string.
    runFailed = QtCore.Signal(str)

    #: Signal(str)
    #: emitted when the widget runs a function and is successful. Emits the return value as a string.
    runSuccessful = QtCore.Signal(str)

    def __init__(
        self,
        fun: Callable,
        fullName: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
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
    def runFun(self) -> None:
        try:
            args, kwargs = self.anyInput.value()
            if kwargs is not None:
                ret = self.fun(*args, **kwargs)
            else:
                if isinstance(args, list) or isinstance(args, tuple) or args != "":
                    ret = self.fun(*args)
                else:
                    ret = self.fun()
            self.runSuccessful.emit(str(ret))
            logger.info(f"'{self.fullName}' returned: {ret}")

        except Exception as e:
            self.runFailed.emit(str(e))
            logger.warning(f"'{self.fullName}' Raised the following execution: {e}")

    @classmethod
    def getTooltipFromFun(cls, fun: Callable) -> str:
        """
        Returns the signature of the function with its documentation underneath.
        """
        sig = inspect.signature(fun)
        doc = inspect.getdoc(fun)
        return str(sig) + "\n\n" + str(doc)


# ----------------- Parameters Display Classes - Beginning -----------------------------


class ItemParameters(ItemBase):
    def __init__(self, unit: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.unit = unit


class ParameterDelegate(DelegateBase):
    """
    The delegate for the InstrumentParameters widget.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent=parent)

        # Stores as key the name of the item and as value the widget that the delegate creates.
        # used to keep a reference to the widget.
        self.parameters: Dict[str, QtWidgets.QWidget] = {}

    def createEditor( # type: ignore[override]
        self,
        widget: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget:
        """
        This is the function that is supposed to create the widget. It should return it.
        """
        item = self.getItem(index)
        element = item.element  # type: ignore[attr-defined]

        ret = ParameterWidget(element, widget)
        self.parameters[item.name] = ret  # type: ignore[attr-defined]
        # Try to fetch and display current value immediately
        # ---- Chao: removed because the constructor of ParameterWidget object already calls parameter get ----
        # if element.gettable:
        #     try:
        #         val = element.get()
        #         ret._setMethod(val)
        #     except Exception as e:
        #         logger.warning(f"Failed to get value for parameter {element.name}: {e}")
        return ret


class ModelParameters(InstrumentModelBase):
    # : Signal(item, object) : Emitted when an item in the model has received a new value, first object is the item's
    # name, second object is its new value
    itemNewValue = QtCore.Signal(object, object)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # make sure we pass the server ip and port properly to the subscriber when the values are not defaults.
        subClientArgs = {
            "sub_host": kwargs.pop("sub_host", "localhost"),
            "sub_port": kwargs.pop("sub_port", DEFAULT_PORT + 1),
        }
        super().__init__(*args, **kwargs)

        self.setColumnCount(3)
        self.setHorizontalHeaderLabels([self.attr, "unit", ""])

        # Live updates items
        self.cliThread = QtCore.QThread()
        self.subClient = SubClient([self.instrument.name], **subClientArgs)
        self.subClient.moveToThread(self.cliThread)

        self.cliThread.started.connect(self.subClient.connect)  # type: ignore[arg-type]
        self.subClient.update.connect(self.updateParameter)
        self.subClient.finished.connect(self.cliThread.quit)

        self.cliThread.start()

    def stopListener(self) -> None:
        """Stop the background listener thread and wait for it to exit."""
        if self.subClient is not None:
            self.subClient.stop()
        if self.cliThread is not None:
            self.cliThread.quit()
            self.cliThread.wait(3000)

    @QtCore.Slot(ParameterBroadcastBluePrint)
    def updateParameter(self, bp: ParameterBroadcastBluePrint) -> None:
        fullName = ".".join(bp.name.split(".")[1:])

        if bp.action == "parameter-creation":
            if fullName not in self.instrument.list():
                self.instrument.update()
            if fullName in self.instrument.list():
                self.addItem(
                    fullName,
                    element=nestedAttributeFromString(self.instrument, fullName),
                )

        elif bp.action == "parameter-deletion":
            self.removeItem(fullName)

        elif bp.action == "parameter-update" or bp.action == "parameter-call":
            item = self.findItems(
                fullName,
                cast(
                    "QtCore.Qt.MatchFlags",
                    QtCore.Qt.MatchFlag.MatchExactly
                    | QtCore.Qt.MatchFlag.MatchRecursive,
                ),
                0,
            )
            if len(item) == 0:
                if fullName not in self.itemsHide:  # type: ignore[operator]
                    try:
                        self.addItem(
                            fullName,
                            element=nestedAttributeFromString(
                                self.instrument, fullName
                            ),
                        )
                    except AttributeError:
                        # Parameter/submodule no longer exists (likely due to profile switch)
                        logger.debug(
                            f"Ignoring broadcast for non-existent parameter: {fullName}"
                        )
            else:
                assert isinstance(item[0], ItemBase)
                # The model can't actually modify the widget since it knows nothing about the view itself.
                self.itemNewValue.emit(item[0].name, bp.value)

    def insertItemTo(
        self, parent: QtGui.QStandardItem, item: QtGui.QStandardItem
    ) -> None:
        if item is not None:
            # A parameter might not have a unit
            unit = ""
            if item.element is not None:  # type: ignore[attr-defined]
                unit = item.element.unit  # type: ignore[attr-defined]
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
    def __init__(
        self,
        model: QtCore.QAbstractItemModel,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, [2], *args, **kwargs)

        self.delegate = ParameterDelegate(self)

        self.setItemDelegateForColumn(2, self.delegate)
        self.setAllDelegatesPersistent()

    @QtCore.Slot(object, object)
    def onItemNewValue(self, itemName: str, value: Any) -> None:
        widget = self.delegate.parameters[itemName]
        try:
            # use the abstract set method defined in parameter widget so it works for different types of widgets
            widget._setMethod(value)
        except RuntimeError:
            logger.debug(
                f"Could not set value for {itemName} to {value}. Object is not being shown right now."
            )


class InstrumentParameters(InstrumentDisplayBase):
    def __init__(
        self,
        instrument: Any,
        parent: Optional[QtWidgets.QWidget] = None,
        viewType: type = ParametersTreeView,
        callSignals: bool = True,
        **kwargs: Any,
    ) -> None:
        if "instrument" in kwargs:
            del kwargs["instrument"]
        modelKwargs = {}
        if "parameters-star" in kwargs:
            modelKwargs["itemsStar"] = kwargs.pop("parameters-star")
        if "parameters-trash" in kwargs:
            modelKwargs["itemsTrash"] = kwargs.pop("parameters-trash")
        if "parameters-hide" in kwargs:
            modelKwargs["itemsHide"] = kwargs.pop("parameters-hide")

        # parameters for realtime update subscriber
        if "sub_host" in kwargs:
            modelKwargs["sub_host"] = kwargs.pop("sub_host")
        if "sub_port" in kwargs:
            modelKwargs["sub_port"] = kwargs.pop("sub_port")

        shortcutManager = kwargs.pop("shortcutManager", None)
        print(shortcutManager)

        super().__init__(
            instrument=instrument,
            parent=parent,
            attr="parameters",
            itemType=ItemParameters,
            modelType=ModelParameters,
            viewType=viewType,
            callSignals=callSignals,
            shortcutManager=shortcutManager,
            **modelKwargs,
        )

    def connectSignals(self) -> None:
        super().connectSignals()
        self.model.itemNewValue.connect(self.view.onItemNewValue)
        self.shortcutManager.register("refresh_item", self._refreshCurrentItem, self)
        self.shortcutManager.register(
            "toggle_python", self._togglePythonCurrentItem, self
        )
        self.shortcutManager.register("edit_value", self._focusToParameterValue, self)

    @QtCore.Slot()
    def _refreshCurrentItem(self) -> None:
        proxy_index = self.view.currentIndex()
        if not proxy_index.isValid():
            return
        source_index = self.proxyModel.mapToSource(proxy_index)
        if source_index.column() != 0:
            source_index = source_index.sibling(source_index.row(), 0)
        item = self.model.itemFromIndex(source_index)
        if isinstance(item, ItemBase):
            widget = self.view.delegate.parameters.get(item.name)
            if widget is not None:
                widget.setWidgetFromParameter()

    @QtCore.Slot()
    def _togglePythonCurrentItem(self) -> None:
        proxy_index = self.view.currentIndex()
        if not proxy_index.isValid():
            return
        source_index = self.proxyModel.mapToSource(proxy_index)
        if source_index.column() != 0:
            source_index = source_index.sibling(source_index.row(), 0)
        item = self.model.itemFromIndex(source_index)
        if isinstance(item, ItemBase):
            widget = self.view.delegate.parameters.get(item.name)
            if widget is not None and isinstance(widget.paramWidget, AnyInput):
                widget.paramWidget.doEval.toggle()

    @QtCore.Slot()
    def _focusToParameterValue(self) -> None:
        proxy_index = self.view.currentIndex()
        if not proxy_index.isValid():
            return
        source_index = self.proxyModel.mapToSource(proxy_index)
        if source_index.column() != 0:
            source_index = source_index.sibling(source_index.row(), 0)
        item = self.model.itemFromIndex(source_index)
        if isinstance(item, ItemBase):
            widget = self.view.delegate.parameters.get(item.name)
            if widget and hasattr(widget, "paramWidget"):
                pw = widget.paramWidget
                if isinstance(pw, AnyInput):
                    pw.input.setFocus()
                else:
                    pw.setFocus()


# ----------------- Parameters Display Classes - Ending --------------------------------

# ----------------- Parameters Manager Classes - Beginning -----------------------------


class ParameterDeleteDelegate(ParameterDelegate):
    #: Signal(str)
    #: Emits the name of the parameter to be deleted when the user presses the delete button.
    removeParameter = QtCore.Signal(str)

    def createEditor(  # type: ignore[override]
        self,
        widget: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget:
        item = self.getItem(index)
        element = item.element  # type: ignore[attr-defined]
        rw = self.makeRemoveWidget(item.name, widget)  # type: ignore[attr-defined]

        ret = ParameterWidget(parameter=element, parent=widget, additionalWidgets=[rw])
        self.parameters[item.name] = ret  # type: ignore[attr-defined]

        return ret

    def makeRemoveWidget(
        self, fullName: str, widget: QtWidgets.QWidget
    ) -> QtWidgets.QPushButton:
        w = QtWidgets.QPushButton(QtGui.QIcon(":/icons/delete.svg"), "", parent=widget)
        w.setStyleSheet("""
            QPushButton { background-color: salmon }
        """)
        w.setToolTip("Delete this parameter")
        keepSmallHorizontally(w)

        w.pressed.connect(lambda: self.removeParameter.emit(fullName))
        return w


# TODO: Make sure that the refresh button refreshes the profiles as well as the model
class ParameterManagerTreeView(InstrumentTreeViewBase):
    def __init__(
        self,
        model: QtCore.QAbstractItemModel,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, [2], *args, **kwargs)

        self.delegate = ParameterDeleteDelegate(self)

        self.setItemDelegateForColumn(2, self.delegate)
        self.setAllDelegatesPersistent()

    @QtCore.Slot(object, object)
    def onItemNewValue(self, itemName: str, value: Any) -> None:
        widget = self.delegate.parameters[itemName]
        widget.paramWidget.setValue(value)


class ProfilesManager(QtWidgets.QComboBox):
    #: Signal()
    #: Emitted when the selected index changed.
    indexChanged = QtCore.Signal()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.setEditable(False)
        self.params = self.parent().instrument  # type: ignore[union-attr]
        self.refreshing = False

        loadingProfile = None
        for profile in self.params.list_profiles():
            self.addItem(self.params.cleanProfileName(profile))
            if loadingProfile is None:
                loadingProfile = profile

        self.currentIndexChanged.connect(self.onCurrentIndexChanged)

    def refresh(self) -> None:
        self.refreshing = True
        currentlySelected = self.currentText()
        self.clear()
        for profile in self.params.list_profiles():
            self.addItem(self.params.cleanProfileName(profile))
            if self.params.cleanProfileName(profile) == currentlySelected:
                self.setCurrentIndex(self.count() - 1)
        self.refreshing = False

    @QtCore.Slot(int)
    def onCurrentIndexChanged(self, index: int) -> None:
        if not self.refreshing:
            self.indexChanged.emit()


class ParameterManagerGui(InstrumentParameters):
    #: Signal(str) --
    #: emitted when there's an error during parameter creation.
    parameterCreationError = QtCore.Signal(str)

    #: Signal() --
    #:  emitted when a parameter was created successfully
    parameterCreated = QtCore.Signal()

    def __init__(
        self,
        instrument: Union[ProxyInstrument, ParameterManager],
        parent: Optional[QtWidgets.QWidget] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            instrument,
            parent=None,
            viewType=ParameterManagerTreeView,
            callSignals=False,
            **kwargs,
        )
        self.profileManager = ProfilesManager(parent=self)
        self.addParam = AddParameterWidget(parent=self)
        layout = self.layout()
        assert isinstance(layout, QtWidgets.QVBoxLayout)
        layout.insertWidget(0, self.profileManager)
        layout.addWidget(self.addParam)
        self.connectSignals()
        self.loadProfile()

    def connectSignals(self) -> None:
        super().connectSignals()
        self.view.delegate.removeParameter.connect(self.removeParameter)
        self.addParam.newParamRequested.connect(self.addParameter)
        self.parameterCreationError.connect(self.addParam.setError)
        self.parameterCreated.connect(self.addParam.clear)
        self.profileManager.indexChanged.connect(self.loadProfile)
        self.shortcutManager.register("delete_item", self._deleteCurrentItem, self)
        self.shortcutManager.register("clear_add", self.addParam.clear, self)
        self.shortcutManager.register("add_item", self.addParam.nameEdit.setFocus, self)
        self.shortcutManager.register("load_items", self.loadFromFile, self)
        self.shortcutManager.register("save_items", self.saveToFile, self)

    @QtCore.Slot()
    def _deleteCurrentItem(self) -> None:
        proxy_index = self.view.currentIndex()
        if not proxy_index.isValid():
            return
        source_index = self.proxyModel.mapToSource(proxy_index)
        if source_index.column() != 0:
            source_index = source_index.sibling(source_index.row(), 0)
        item = self.model.itemFromIndex(source_index)
        if isinstance(item, ItemBase):
            self.removeParameter(item.name)

    def makeToolbar(self) -> QtWidgets.QToolBar:
        toolbar = super().makeToolbar()

        toolbar.addSeparator()

        loadParamAction = toolbar.addAction(
            QtGui.QIcon(":/icons/load.svg"),
            "Load parameters from file",
        )
        loadParamAction.triggered.connect(lambda x: self.loadFromFile())  # type: ignore[union-attr]
        self.shortcutManager.apply_to_action("load_items", loadParamAction)

        saveParamAction = toolbar.addAction(
            QtGui.QIcon(":/icons/save.svg"),
            "Save parameters to file",
        )
        saveParamAction.triggered.connect(lambda x: self.saveToFile())  # type: ignore[union-attr]
        self.shortcutManager.apply_to_action("save_items", saveParamAction)

        return toolbar

    def refreshAll(self) -> None:
        super().refreshAll()
        self.instrument.refresh_profiles()
        self.profileManager.refresh()

    def removeParameter(self, fullName: str) -> None:
        if self.instrument.has_param(fullName):
            self.instrument.remove_parameter(fullName)

    def addParameter(self, fullName: str, value: Any, unit: str) -> None:
        try:
            # Validators are commented out until they can be serialized.
            self.instrument.add_parameter(
                fullName,
                initial_value=value,
                unit=unit,
            )  # vals=vals)
            self.parameterCreated.emit()
        except Exception as e:
            self.parameterCreationError.emit(
                f"Could not create parameter.Adding parameter raised{type(e)}: {e.args}"
            )
            return

    @QtCore.Slot()
    def loadProfile(self) -> None:
        profileName = self.profileManager.currentText()
        self.instrument.switch_to_profile(profileName)
        super().refreshAll()
        self.instrument.refresh_profiles()

    @QtCore.Slot()
    def loadFromFile(self, loadFile: Optional[str] = None) -> None:
        try:
            self.instrument.fromFile(filePath=loadFile, deleteMissing=False)
            self.refreshAll()

        except Exception as e:
            logger.info(f"Loading failed. {type(e)}: {e.args}")

    @QtCore.Slot()
    def saveToFile(self) -> None:
        try:
            self.instrument.toFile()
        except Exception as e:
            logger.info(f"Saving failed. {type(e)}: {e.args}")


# ----------------- Parameters Manager Classes - Ending --------------------------------

# ----------------- Methods Display Classes - Beginning --------------------------------


class MethodsModel(InstrumentModelBase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels([self.attr, "Arguments & Run"])

    def insertItemTo(
        self, parent: QtGui.QStandardItem, item: QtGui.QStandardItem
    ) -> None:
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
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent=parent)

        self.methods: Dict[str, "MethodDisplay"] = {}

    def createEditor(  # type: ignore[override]
        self,
        widget: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget:
        item = self.getItem(index)
        element = item.element  # type: ignore[attr-defined]
        ret = MethodDisplay(element, item.name, parent=widget)  # type: ignore[attr-defined]

        parent = self.parent()
        assert hasattr(parent, "clearAlertsAction")
        # connecting the widget with the clear alert signal
        parent.clearAlertsAction.triggered.connect(ret.alertLabel.clearAlert)  # type: ignore[union-attr]

        self.methods[item.name] = ret  # type: ignore[attr-defined]
        return ret


class MethodsTreeView(InstrumentTreeViewBase):
    def __init__(
        self,
        model: QtCore.QAbstractItemModel,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, [1], *args, **kwargs)

        # Adding the clear alert to the context menu
        self.clearAlertsAction = QtWidgets.QAction("Clear alerts")
        self.contextMenu.addSeparator()
        self.contextMenu.addAction(self.clearAlertsAction)

        self.delegate = MethodsDelegate(self)
        self.setItemDelegateForColumn(1, self.delegate)
        self.setAllDelegatesPersistent()


class InstrumentMethods(InstrumentDisplayBase):
    def __init__(self, instrument: Any, **kwargs: Any) -> None:
        if "instrument" in kwargs:
            del kwargs["instrument"]

        modelKwargs = {}
        if "methods-star" in kwargs:
            modelKwargs["itemsStar"] = kwargs.pop("methods-star")
        if "methods-trash" in kwargs:
            modelKwargs["itemsTrash"] = kwargs.pop("methods-trash")
        if "methods-hide" in kwargs:
            modelKwargs["itemsHide"] = kwargs.pop("methods-hide")

        shortcutManager = kwargs.pop("shortcutManager", None)

        super().__init__(
            instrument=instrument,
            attr="functions",
            modelType=MethodsModel,
            viewType=MethodsTreeView,
            shortcutManager=shortcutManager,
            **modelKwargs,
        )


# ----------------- Methods Display Classes - Ending -----------------------------------


class GenericInstrument(QtWidgets.QWidget):
    """
    Widget that allows the display of real time parameters and changing their values.
    """

    def __init__(
        self,
        ins: Union[ProxyInstrument, Instrument],
        parent: Optional[QtWidgets.QWidget] = None,
        **modelKwargs: Any,
    ) -> None:
        super().__init__(parent=parent)

        self.ins = ins

        if type(ins) is ProxyInstrument:
            inst_type = "Proxy-" + ins.bp.instrument_module_class.split(".")[-1]
        else:
            inst_type = ins.__class__.__name__

        ins_label = f"{ins.name} | type: {inst_type}"

        try:
            # added a unique device_id if the instrument has that method
            device_id = ins.device_id()
            ins_label += f" | id: {device_id}"
        except AttributeError:
            pass

        self._layout = QtWidgets.QVBoxLayout(self)
        self.setLayout(self._layout)

        self.splitter = QtWidgets.QSplitter(self)
        self.splitter.setOrientation(QtCore.Qt.Orientation.Vertical)

        self.parametersList = InstrumentParameters(instrument=ins, **modelKwargs)
        self.methodsList = InstrumentMethods(instrument=ins, **modelKwargs)
        self.instrumentNameLabel = QtWidgets.QLabel(ins_label)

        self._layout.addWidget(self.instrumentNameLabel)
        self._layout.addWidget(self.splitter)
        self.splitter.addWidget(self.parametersList)
        self.splitter.addWidget(self.methodsList)

        # Resize param name, unit, and function name columns after entries loaded
        self.parametersList.view.resizeColumnToContents(0)
        self.parametersList.view.resizeColumnToContents(1)
        self.methodsList.view.resizeColumnToContents(0)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        """Stop the parameter subscriber thread before destruction."""
        model = getattr(self.parametersList, "model", None)
        if model is not None and hasattr(model, "stopListener"):
            model.stopListener()
        super().closeEvent(event)
