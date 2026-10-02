import inspect
import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    Union,
    cast,
)

from qcodes import Instrument

from instrumentserver.gui.misc import AlertLabelGreen

from .. import DEFAULT_PORT, QtCore, QtGui, QtWidgets
from ..blueprints import (
    PARAMETER_CALL,
    PARAMETER_CREATION,
    PARAMETER_DELETION,
    PARAMETER_UPDATE,
    ParameterBroadcastBluePrint,
)
from ..client import ProxyInstrument, SubClient
from ..helpers import nestedAttributeFromString
from .base_instrument import (
    DelegateBase,
    InstrumentDisplayBase,
    InstrumentModelBase,
    InstrumentTreeViewBase,
    ItemBase,
)
from .parameters import AnyInput, AnyInputForMethod, ParameterWidget

if TYPE_CHECKING:
    from .parameter_manager import ParameterManagerGui, PMState

# TODO: all styles set through a global style sheet.
# TODO: [maybe] add a column for information on valid input values?

logger = logging.getLogger(__name__)

#: Names that moved to :mod:`instrumentserver.gui.parameter_manager` and are
#: still served from this module, so station configs that name
#: ``instrumentserver.gui.instruments.ParameterManagerGui`` keep loading.
_MOVED_TO_PARAMETER_MANAGER = ("ParameterManagerGui", "PMState")


def __getattr__(name: str) -> Union[Type["ParameterManagerGui"], Type["PMState"]]:
    # imported on first use: the parameter_manager package imports this module
    if name in _MOVED_TO_PARAMETER_MANAGER:
        from . import parameter_manager

        return cast(
            Union[Type["ParameterManagerGui"], Type["PMState"]],
            getattr(parameter_manager, name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class MethodDisplay(QtWidgets.QWidget):
    #: Signal(str)
    #: emitted when the widget runs a function and fails. Emits the exception as a string.
    runFailed = QtCore.Signal(str)

    #: Signal(str)
    #: emitted when the widget runs a function and is successful. Emits the return value as a string.
    runSuccessful = QtCore.Signal(str)

    #: Signal() --
    #: emitted when the user commits via Return/Enter, regardless of success or failure
    valueCommitted = QtCore.Signal()

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
        finally:
            self.valueCommitted.emit()

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
        self.navFilter: Optional["ValueCellNavigationFilter"] = None

    def createEditor(  # type: ignore[override]
        self,
        widget: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget:
        """
        This is the function that is supposed to create the widget. It should return it.
        """
        item = self.getItem(index)

        if not item.showDelegate:  # type: ignore[attr-defined]
            return None  # type: ignore[return-value]

        ret = self.makeParameterWidget(item, widget)
        self.parameters[item.name] = ret  # type: ignore[attr-defined]
        # Qt deletes the editor when its row is hidden (the filter, the
        # trash toggle); forget it then, so nobody touches a dead widget
        ret.destroyed.connect(
            lambda _=None, name=item.name, editor=ret: self._forgetEditor(  # type: ignore[attr-defined]
                name, editor
            )
        )
        ret.valueCommitted.connect(self.parent().setFocus)  # type: ignore[union-attr]

        if self.navFilter is not None:
            if isinstance(ret.paramWidget, AnyInput):
                input_widget = ret.paramWidget.input
            else:
                input_widget = ret.paramWidget
            input_widget.installEventFilter(self.navFilter)
            self.navFilter.registerWidget(input_widget, index)

        # Try to fetch and display current value immediately
        # ---- Chao: removed because the constructor of ParameterWidget object already calls parameter get ----
        # if element.gettable:
        #     try:
        #         val = element.get()
        #         ret._setMethod(val)
        #     except Exception as e:
        #         logger.warning(f"Failed to get value for parameter {element.name}: {e}")
        return ret

    def _forgetEditor(self, name: str, editor: QtWidgets.QWidget) -> None:
        """Drop the destroyed ``editor`` of row ``name``, unless a newer
        editor for the same row has already replaced it."""
        if self.parameters.get(name) is editor:
            del self.parameters[name]

    def makeParameterWidget(
        self, item: QtGui.QStandardItem, parent: QtWidgets.QWidget
    ) -> ParameterWidget:
        """The editor widget for the parameter of ``item``. A delegate that
        adds buttons next to the value overrides this;
        :meth:`createEditor` does the rest (registering the widget and
        installing the navigation filter)."""
        return ParameterWidget(item.element, parent)  # type: ignore[attr-defined]


class ValueCellNavigationFilter(QtCore.QObject):
    """Event filter installed on value input widgets to handle Escape, Tab, and Shift+Tab."""

    def __init__(self, treeView: InstrumentTreeViewBase) -> None:
        super().__init__(treeView)
        self._treeView = treeView
        self._widgetIndex: Dict[QtCore.QObject, QtCore.QPersistentModelIndex] = {}

    def registerWidget(self, widget: QtCore.QObject, index: QtCore.QModelIndex) -> None:
        self._widgetIndex[widget] = QtCore.QPersistentModelIndex(index)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if event.type() == QtCore.QEvent.Type.FocusIn:
            if obj in self._widgetIndex:
                idx = self._widgetIndex[obj]
                if idx.isValid():
                    self._treeView.setCurrentIndex(QtCore.QModelIndex(idx))
            return False

        if event.type() == QtCore.QEvent.Type.KeyPress:
            assert isinstance(event, QtGui.QKeyEvent)
            key = QtGui.QKeySequence(event.key()).toString()

            if key == "Esc":
                host = self._findHostWidget(obj)
                if isinstance(host, ParameterWidget):
                    host.setWidgetFromParameter()
                elif isinstance(host, MethodDisplay):
                    host.anyInput.input.clear()
                self._treeView.setFocus()
                return True

            elif key == "Tab":
                self._commitAndMove(obj, 1)
                return True

            elif key == "Backtab":
                self._commitAndMove(obj, -1)
                return True

        return super().eventFilter(obj, event)

    def _findHostWidget(
        self, obj: QtCore.QObject
    ) -> Optional[Union[ParameterWidget, MethodDisplay]]:
        parent = obj.parent()
        while parent is not None:
            if isinstance(parent, (ParameterWidget, MethodDisplay)):
                return parent
            parent = parent.parent()
        return None

    def _commitAndMove(self, obj: QtCore.QObject, direction: int) -> None:
        host = self._findHostWidget(obj)
        if isinstance(host, ParameterWidget):
            host.setButton.click()
        elif isinstance(host, MethodDisplay):
            host.runFun()
        current = self._treeView.currentIndex()
        if current.isValid():
            next_idx = (
                self._treeView.indexBelow(current)
                if direction > 0
                else self._treeView.indexAbove(current)
            )
            if next_idx.isValid():
                self._treeView.setCurrentIndex(next_idx)
        self._treeView.setFocus()


class ModelParameters(InstrumentModelBase):
    #: Signal(item, object) : Emitted when an item in the model has received a new value, first object is the item's
    #: name, second object is its new value
    itemNewValue = QtCore.Signal(object, object)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # make sure we pass the server ip and port properly to the subscriber when the values are not defaults.
        subClientArgs = {
            "sub_host": kwargs.pop("sub_host", "localhost"),
            "sub_port": kwargs.pop("sub_port", DEFAULT_PORT + 1),
        }
        super().__init__(*args, **kwargs)

        labels = self.headerLabels()
        self.setColumnCount(len(labels))
        self.setHorizontalHeaderLabels(labels)

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

        if bp.action == PARAMETER_CREATION:
            # Resolve the parameter on the instrument first: a parameter
            # another Client created while the GUI is open is already in the
            # Proxy's remote list(), so only a fresh resolution tells whether
            # the (Proxy) instrument's blueprint is stale. On a stale one,
            # update() refreshes it and the element resolves on the second
            # attempt (TEST_AUDIT.md, "Parameter Manager GUI — live creation
            # from another client"; fixed in plan task 5.5 by Marcos's
            # decision, an explicit exception to plan rule 6).
            try:
                element = nestedAttributeFromString(self.instrument, fullName)
            except AttributeError:
                if hasattr(self.instrument, "update"):
                    self.instrument.update()
                try:
                    element = nestedAttributeFromString(self.instrument, fullName)
                except AttributeError:
                    logger.debug(
                        f"Ignoring parameter-creation broadcast for a "
                        f"parameter that cannot be resolved: {fullName}"
                    )
                    element = None
            if element is not None:
                self.addItem(fullName, element=element)

        elif bp.action == PARAMETER_DELETION:
            self.removeItem(fullName)

        elif bp.action == PARAMETER_UPDATE or bp.action == PARAMETER_CALL:
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

    def headerLabels(self) -> List[str]:
        """The header label of every column: name, unit and delegate.
        A model with more columns extends this list and :meth:`rowItems`
        together."""
        return [self.attr, "unit", ""]

    def rowItems(self, item: QtGui.QStandardItem) -> List[QtGui.QStandardItem]:
        """The items of one row, ``item`` first, one per column of
        :meth:`headerLabels`. :meth:`insertItemTo` inserts them."""
        # A parameter might not have a unit
        unit = ""
        if item.element is not None:  # type: ignore[attr-defined]
            unit = item.element.unit  # type: ignore[attr-defined]
        return [item, QtGui.QStandardItem(unit), QtGui.QStandardItem()]

    def insertItemTo(
        self, parent: QtGui.QStandardItem, item: QtGui.QStandardItem
    ) -> None:
        if item is not None:
            row = self.rowItems(item)
            if parent == self:
                rowCount = self.rowCount()
                for column, cell in enumerate(row):
                    self.setItem(rowCount, column, cell)
            else:
                parent.appendRow(row)

            self.newItem.emit(item)


class ParametersTreeView(InstrumentTreeViewBase):
    #: The delegate class of the value column (column 2).
    delegateClass: type[ParameterDelegate] = ParameterDelegate

    def __init__(
        self,
        model: QtCore.QAbstractItemModel,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, [2], *args, **kwargs)

        self.delegate = self.delegateClass(self)
        self.delegate.navFilter = ValueCellNavigationFilter(self)

        self.setItemDelegateForColumn(2, self.delegate)
        self.setupColumns()
        self.setAllDelegatesPersistent()

    def setupColumns(self) -> None:
        """Set up the delegates and header of any columns beyond name,
        unit and value. Runs before the persistent editors are opened;
        the default does nothing."""

    @QtCore.Slot(object, object)
    def onItemNewValue(self, itemName: str, value: Any) -> None:
        widget = self.delegate.parameters.get(itemName)
        if widget is None:
            # the row is hidden, so it has no editor to update
            return
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
        modelType: type = ModelParameters,
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

        super().__init__(
            instrument=instrument,
            parent=parent,
            attr="parameters",
            itemType=ItemParameters,
            modelType=modelType,
            viewType=viewType,
            callSignals=callSignals,
            shortcutManager=shortcutManager,
            **modelKwargs,
        )

    def connectSignals(self) -> None:
        super().connectSignals()
        self.model.itemNewValue.connect(self.view.onItemNewValue)

        self.view.editCurrentParameter.connect(self._focusToParameterValue)
        self.view.clearCurrentParameter.connect(self._clearCurrentParameter)

        self.shortcutManager.register("refresh_item", self._refreshCurrentItem, self)
        self.shortcutManager.register(
            "toggle_python", self._togglePythonCurrentItem, self
        )

    def _withCurrentParameter(
        self, callback: Callable[["ParameterWidget"], None]
    ) -> None:
        item = self._getCurrentItem()
        if item is not None:
            widget = self.view.delegate.parameters.get(item.name)
            if widget is not None:
                callback(widget)

    @QtCore.Slot()
    def _refreshCurrentItem(self) -> None:
        self._withCurrentParameter(lambda w: w.setWidgetFromParameter())

    @QtCore.Slot()
    def _togglePythonCurrentItem(self) -> None:
        self._withCurrentParameter(
            lambda w: (
                w.paramWidget.doEval.toggle()
                if isinstance(w.paramWidget, AnyInput)
                else None
            )
        )

    @QtCore.Slot()
    def _focusToParameterValue(self) -> None:
        self._withCurrentParameter(
            lambda w: (
                w.paramWidget.input.setFocus()
                if isinstance(w.paramWidget, AnyInput)
                else None
                if isinstance(w.paramWidget, QtWidgets.QLabel)
                else w.paramWidget.setFocus()
            )
        )

    @QtCore.Slot()
    def _clearCurrentParameter(self) -> None:
        self._withCurrentParameter(
            lambda w: (
                w.paramWidget.input.clear()
                if isinstance(w.paramWidget, AnyInput)
                # read-only parameters are shown in a QLabel; clearing it would blank the display
                else None
                if isinstance(w.paramWidget, QtWidgets.QLabel)
                else w.paramWidget.clear()
                if hasattr(w.paramWidget, "clear")
                else None
            )
        )


# ----------------- Parameters Display Classes - Ending --------------------------------

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
        self.navFilter: Optional[ValueCellNavigationFilter] = None

    def createEditor(  # type: ignore[override]
        self,
        widget: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget:
        item = self.getItem(index)

        if not item.showDelegate:  # type: ignore[attr-defined]
            return None  # type: ignore[return-value]

        element = item.element  # type: ignore[attr-defined]
        ret = MethodDisplay(element, item.name, parent=widget)  # type: ignore[attr-defined]

        parent = self.parent()
        assert hasattr(parent, "clearAlertsAction")
        # connecting the widget with the clear alert signal
        parent.clearAlertsAction.triggered.connect(ret.alertLabel.clearAlert)  # type: ignore[union-attr]

        self.methods[item.name] = ret  # type: ignore[attr-defined]
        ret.valueCommitted.connect(self.parent().setFocus)  # type: ignore[union-attr]

        if self.navFilter is not None:
            ret.anyInput.input.installEventFilter(self.navFilter)
            self.navFilter.registerWidget(ret.anyInput.input, index)

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
        self.delegate.navFilter = ValueCellNavigationFilter(self)
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

    def connectSignals(self) -> None:
        super().connectSignals()

        self.view.editCurrentParameter.connect(self._focusToMethodValue)
        self.view.clearCurrentParameter.connect(self._clearCurrentMethod)

        self.shortcutManager.register(
            "toggle_python", self._togglePythonCurrentItem, self
        )
        self.shortcutManager.register("run_method", self._runCurrentMethod, self)

    def _withCurrentMethod(self, callback: Callable[["MethodDisplay"], None]) -> None:
        item = self._getCurrentItem()
        if item is not None:
            widget = self.view.delegate.methods.get(item.name)
            if widget is not None:
                callback(widget)

    @QtCore.Slot()
    def _togglePythonCurrentItem(self) -> None:
        self._withCurrentMethod(lambda w: w.anyInput.doEval.toggle())

    @QtCore.Slot()
    def _focusToMethodValue(self) -> None:
        self._withCurrentMethod(lambda w: w.anyInput.input.setFocus())

    @QtCore.Slot()
    def _clearCurrentMethod(self) -> None:
        self._withCurrentMethod(lambda w: w.anyInput.input.clear())

    @QtCore.Slot()
    def _runCurrentMethod(self) -> None:
        self._withCurrentMethod(lambda w: w.runFun())


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
