import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union, cast

from qcodes import Instrument

from instrumentserver.gui.misc import AlertLabelGreen

from .. import DEFAULT_PORT, QtCore, QtGui, QtWidgets
from ..blueprints import (
    PARAMETER_CALL,
    PARAMETER_CREATION,
    PARAMETER_DELETION,
    PARAMETER_UPDATE,
    PM_LOCK_UPDATE,
    PM_TYPE_UPDATE,
    ParameterBroadcastBluePrint,
    PMLockBluePrint,
    PMTypeBluePrint,
)
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
                parameterTypes[ParameterTypes.numeric]["name"]  # type: ignore[arg-type]
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

        element = item.element  # type: ignore[attr-defined]

        ret = ParameterWidget(element, widget)
        self.parameters[item.name] = ret  # type: ignore[attr-defined]
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

    #: Signal(str, object) --
    #: Emitted on a ``pm-lock-update`` Broadcast: the Follower's path relative
    #: to the instrument, and its :class:`PMLockBluePrint` (``None`` when its
    #: Lock was removed). No model item is touched for this action.
    lockChanged = QtCore.Signal(str, object)

    #: Signal(str, object) --
    #: Emitted on a ``pm-type-update`` Broadcast: the Type's name (the part
    #: after the instrument name), and its :class:`PMTypeBluePrint` (``None``
    #: when the Type was removed). No model item is touched for this action.
    typeChanged = QtCore.Signal(str, object)

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

        if bp.action == PARAMETER_CREATION:
            if fullName not in self.instrument.list():
                self.instrument.update()
            if fullName in self.instrument.list():
                self.addItem(
                    fullName,
                    element=nestedAttributeFromString(self.instrument, fullName),
                )

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

        elif bp.action == PM_LOCK_UPDATE:
            # Locks and Types claim no model item of their own: the Lock
            # column and the Type tints are separate tasks. The Parameter
            # Manager GUI records the change in its PMState (D10).
            self.lockChanged.emit(fullName, bp.value)

        elif bp.action == PM_TYPE_UPDATE:
            self.typeChanged.emit(fullName, bp.value)

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


class ModelParameterManager(ModelParameters):
    #: Signal() --
    #: Emitted after a Broadcast changed the tree's structure (a parameter
    #: was created or removed), so the Parameter Manager GUI can recompute
    #: the Type claims that the tints and gutter bands show.
    structureChanged = QtCore.Signal()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # ModelParameters pins the column count at 3 after loading; widen it
        # again and give every loaded row the gutter item the narrow count
        # dropped
        self.setColumnCount(GUTTER_COLUMN + 1)
        self.setHorizontalHeaderLabels([self.attr, "unit", "", ""])
        self._ensure_gutter_items(self.invisibleRootItem())

    def _ensure_gutter_items(self, parent: QtGui.QStandardItem) -> None:
        """Give every row under ``parent`` its gutter item."""
        for row in range(parent.rowCount()):
            if parent.child(row, GUTTER_COLUMN) is None:
                parent.setChild(row, GUTTER_COLUMN, QtGui.QStandardItem())
            item = parent.child(row, 0)
            if item is not None and item.hasChildren():
                self._ensure_gutter_items(item)

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
            gutterItem = QtGui.QStandardItem()

            if parent == self:
                rowCount = self.rowCount()
                self.setItem(rowCount, 0, item)
                self.setItem(rowCount, 1, unitItem)
                self.setItem(rowCount, 2, extraItem)
                self.setItem(rowCount, GUTTER_COLUMN, gutterItem)
            else:
                parent.appendRow([item, unitItem, extraItem, gutterItem])

            self.newItem.emit(item)

    def updateParameter(self, bp: ParameterBroadcastBluePrint) -> None:
        super().updateParameter(bp)
        if bp.action in (PARAMETER_CREATION, PARAMETER_DELETION):
            # matching depends on which parameters exist: the tints and
            # gutter bands must be recomputed after a structural Broadcast
            self.structureChanged.emit()


class ParametersTreeView(InstrumentTreeViewBase):
    def __init__(
        self,
        model: QtCore.QAbstractItemModel,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, [2], *args, **kwargs)

        self.delegate = ParameterDelegate(self)
        self.delegate.navFilter = ValueCellNavigationFilter(self)

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

# ----------------- Parameters Manager Classes - Beginning -----------------------------


# ----------------- Parameter Manager tints - Beginning --------------------------------


#: Logical index of the gutter column of :class:`ModelParameterManager`,
#: whose items carry a row's stack of Types for the
#: :class:`GutterDelegate` to draw. The existing columns keep their
#: indexes: name (0), unit (1), delegate (2).
GUTTER_COLUMN = 3

#: Fixed pixel width of the gutter column in the view.
GUTTER_WIDTH = 12

#: Data role under which a row's stack of Type names is stored on its
#: gutter item; :class:`GutterDelegate` reads it to draw the bands.
GUTTER_ROLE = cast(
    "QtCore.Qt.ItemDataRole", QtCore.Qt.ItemDataRole.UserRole + 1
)

#: The mock's TINTS, light values only (D21: no dark theme): ``tint`` and
#: ``tintAlt`` are the row background of a claimed row (``tintAlt`` for
#: every other sibling row), ``bar`` the colour of its gutter band. The
#: slot of a Type is its index in this list.
TINT_PALETTE: List[Dict[str, str]] = [
    {"tint": "#e8f1fb", "tintAlt": "#dfe9f6", "bar": "#4a7fc1"},
    {"tint": "#e9f4e9", "tintAlt": "#e0ede0", "bar": "#4f9e57"},
    {"tint": "#f6efe4", "tintAlt": "#efe7db", "bar": "#b98a3e"},
    {"tint": "#f9ecec", "tintAlt": "#f2e3e3", "bar": "#b5605f"},
    {"tint": "#e5f4f2", "tintAlt": "#dcece9", "bar": "#3f9490"},
]

#: The palette as QColors, in the same slot order.
TINT_COLOURS: List[Dict[str, QtGui.QColor]] = [
    {name: QtGui.QColor(value) for name, value in entry.items()}
    for entry in TINT_PALETTE
]


@dataclass
class Claim:
    """What the tree shows for one row that Types carry (the mock's
    ``claims()``): the Claiming Type whose tint the row shows, the Instance
    submodule path that claims it, and every Type carrying the row,
    outermost first (the gutter draws one band per Type, up to three)."""

    type: str
    instance: str
    stack: List[str]


def _nested_claim_prefixes(
    blueprint: PMTypeBluePrint,
    types: Mapping[str, PMTypeBluePrint],
) -> Dict[str, str]:
    """Map every effective path of the Type ``blueprint`` that a Nested
    Type defines to the dotted submodule chain under which its defining
    Type sits (the mock's ``at``): a ``qubit`` nesting a ``readout`` at its
    submodule ``readout``, with the ``readout`` nesting a ``pulse_window``
    at ``pw``, maps the effective path ``readout.pw.win`` to
    ``readout.pw``.

    Mirrors how ``params.py`` expands the effective set
    (``_collect_effective``): the entries a Type defines itself are left
    out (they claim at the Instance itself) and each Nested Type's own
    entries are recorded under the chain that leads to it.
    """
    at_by_path: Dict[str, str] = {}

    def walk(blueprint: PMTypeBluePrint, prefix: str, seen: Tuple[str, ...]) -> None:
        for submodule, nested_name in blueprint.nested.items():
            if nested_name in seen:
                continue  # cycles are refused by the Parameter Manager
            nested = types.get(nested_name)
            if nested is None:
                continue
            at = prefix + submodule
            for path, spec in nested.effective.items():
                if spec.get("from_type") == nested_name:
                    at_by_path[f"{at}.{path}"] = at
            walk(nested, f"{at}.", seen + (nested_name,))

    walk(blueprint, "", (blueprint.name,))
    return at_by_path


def _carries_effective_set(
    instance: str,
    effective: Mapping[str, Mapping[str, str]],
    parameters: Mapping[str, str],
) -> bool:
    """Whether the candidate Instance ``instance`` carries every path of
    the effective set ``effective`` with the unit the Type declares (D12):
    matching requires existence and unit, compared as strings; values are
    irrelevant."""
    prefix = f"{instance}."
    for path, spec in effective.items():
        if parameters.get(prefix + path) != spec["unit"]:
            return False
    return True


def compute_claims(
    types: Mapping[str, PMTypeBluePrint],
    parameters: Mapping[str, str],
) -> Dict[str, Claim]:
    """The mock's ``claims()`` ported to the client-side state (plan task
    5.2): which Type claims each row of the Parameter Manager tree, and
    which stack of Types carries it.

    :param types: the Parameter Manager's Types (``PMState.types``), each
        as its :class:`PMTypeBluePrint`.
    :param parameters: every parameter row of the tree as ``{path relative
        to the Parameter Manager: unit}``.
    :return: for every claimed parameter path and submodule path, its
        :class:`Claim`.

    Matching mirrors ``ParameterManager.instances_of`` (D12) client-side:
    a candidate is every submodule path derived from the parameter paths
    (every proper dotted prefix; never the root, never anything under
    Globals) and it is an Instance when it carries every effective path
    with the declared unit. The Claiming Type is the innermost (the
    longest Instance path), then the largest effective set, then the Type
    name. A Nested Type claims at and below its submodule, so a row it
    defines is claimed by it, with the outer Types behind it in the stack.
    """
    # candidate Instances: every proper dotted prefix of a parameter path
    candidates = set()
    for path in parameters:
        segments = path.split(".")
        for depth in range(1, len(segments)):
            candidate = ".".join(segments[:depth])
            if "_globals" in candidate.split("."):
                continue  # Globals is excluded from matching at any depth
            candidates.add(candidate)

    claims_by_path: Dict[str, List[Tuple[str, str, int]]] = {}
    winning: Dict[str, Tuple[str, str, int]] = {}

    def put(path: str, type_name: str, instance: str, size: int) -> None:
        # one (Type, Instance, effective set size) claim, as the mock's
        # all/map pair; the winner keeps the innermost Instance, then the
        # largest effective set, then the Type name
        claim = (type_name, instance, size)
        claims_by_path.setdefault(path, []).append(claim)
        old = winning.get(path)
        if old is None or (-len(instance), -size, type_name) < (
            -len(old[1]),
            -old[2],
            old[0],
        ):
            winning[path] = claim

    for type_name, blueprint in types.items():
        effective = blueprint.effective
        if not effective:
            continue  # an empty Type has no Instances
        size = len(effective)
        at_by_path = _nested_claim_prefixes(blueprint, types)
        for instance in sorted(candidates):
            if not _carries_effective_set(instance, effective, parameters):
                continue
            # the Instance row itself is claimed by its Type, as in the mock
            put(instance, type_name, instance, size)
            for path in effective:
                # every row at and above the parameter, down to the
                # parameter itself, is claimed at the Instance
                at = at_by_path.get(path, "")
                spec = effective[path]
                owner_instance = f"{instance}.{at}" if at else None
                at_depth = len(at.split(".")) if at else 0
                segments = path.split(".")
                for depth in range(1, len(segments) + 1):
                    row = f"{instance}.{'.'.join(segments[:depth])}"
                    put(row, type_name, instance, size)
                    if owner_instance is not None and depth >= at_depth:
                        # the Nested Type claims at and below its submodule
                        put(row, spec["from_type"], owner_instance, size)

    claims: Dict[str, Claim] = {}
    for path, path_claims in claims_by_path.items():
        # the stack is every Type carrying the row, outermost first
        # (shortest Instance path, then the larger effective set),
        # de-duplicated by Type
        stack: List[str] = []
        for name in [
            entry[0]
            for entry in sorted(
                path_claims, key=lambda entry: (len(entry[1]), -entry[2], entry[0])
            )
        ]:
            if name not in stack:
                stack.append(name)
        type_name, instance, _ = winning[path]
        claims[path] = Claim(type=type_name, instance=instance, stack=stack)
    return claims


class TypePalette:
    """Assigns the fixed tint palette's slots to the Types the GUI knows.

    A Type keeps its slot while it exists: the slot is assigned when the
    GUI first sees the Type (in ``PMState.types`` order after a refresh,
    then each new Type from a ``pm-type-update`` Broadcast), it never
    changes while the Type is in the state, and it is freed when the Type
    is removed. A new Type takes the lowest free slot, or slot 0 when all
    five are used (the mock's ``freeTint`` recycles when exhausted).
    """

    def __init__(self) -> None:
        self.slots: Dict[str, int] = {}

    def sync(self, type_names: Any) -> None:
        """Free the slots of Types that are gone and assign slots to new
        ones, in the given creation order.

        :param type_names: the names of the Types the GUI knows
            (``PMState.types``).
        """
        names = list(type_names)
        for name in [known for known in self.slots if known not in names]:
            del self.slots[name]
        used = set(self.slots.values())
        for name in names:
            if name in self.slots:
                continue
            slot = next(
                (index for index in range(len(TINT_PALETTE)) if index not in used),
                0,
            )
            self.slots[name] = slot
            used.add(slot)

    def colours(self, type_name: str) -> Optional[Dict[str, QtGui.QColor]]:
        """The palette entry of the Type ``type_name`` (``tint``,
        ``tintAlt`` and ``bar``), or ``None`` when it has no slot."""
        slot = self.slots.get(type_name)
        return None if slot is None else TINT_COLOURS[slot]

    def bar_colour(self, type_name: str) -> Optional[QtGui.QColor]:
        """The gutter band colour of the Type ``type_name``."""
        colours = self.colours(type_name)
        return None if colours is None else colours["bar"]


class GutterDelegate(QtWidgets.QStyledItemDelegate):
    """Draws the gutter bands of a row's stack of Types into the gutter
    column: up to three vertical bands of equal width filling the cell,
    one per Type of the stack, outermost first, left to right, in the
    Types' ``bar`` colours. A row with no stack paints nothing beyond the
    background."""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        # Owned by the Parameter Manager GUI and assigned after the view is
        # built; the delegate only reads the Types' colours from it.
        self.typePalette: Optional[TypePalette] = None

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        # the background first (alternating row or Type tint), then the bands
        widget = opt.widget
        style = (
            widget.style() if widget is not None else QtWidgets.QApplication.style()
        )
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget
        )
        if self.typePalette is None:
            return
        stack = index.data(GUTTER_ROLE)
        if not stack:
            return
        bandWidth = opt.rect.width() / len(stack)
        for band, type_name in enumerate(stack):
            colour = self.typePalette.bar_colour(type_name)
            if colour is None:
                continue
            painter.fillRect(
                QtCore.QRectF(
                    opt.rect.x() + band * bandWidth,
                    opt.rect.y(),
                    bandWidth,
                    opt.rect.height(),
                ),
                colour,
            )

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtCore.QSize:
        return QtCore.QSize(
            GUTTER_WIDTH, super().sizeHint(option, index).height()
        )


# ----------------- Parameter Manager tints - Ending -----------------------------------


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

        if not item.showDelegate:  # type: ignore[attr-defined]
            return None  # type: ignore[return-value]

        element = item.element  # type: ignore[attr-defined]
        rw = self.makeRemoveWidget(item.name, widget)  # type: ignore[attr-defined]

        ret = ParameterWidget(parameter=element, parent=widget, additionalWidgets=[rw])
        self.parameters[item.name] = ret  # type: ignore[attr-defined]
        ret.valueCommitted.connect(self.parent().setFocus)  # type: ignore[union-attr]

        if self.navFilter is not None:
            if isinstance(ret.paramWidget, AnyInput):
                input_widget = ret.paramWidget.input
            else:
                input_widget = ret.paramWidget
            input_widget.installEventFilter(self.navFilter)
            self.navFilter.registerWidget(input_widget, index)

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
        self.delegate.navFilter = ValueCellNavigationFilter(self)

        self.setItemDelegateForColumn(2, self.delegate)

        # the gutter column exists only in the Parameter Manager's own model
        # (ModelParameterManager)
        self.gutterDelegate = GutterDelegate(self)
        if self.model().columnCount() > GUTTER_COLUMN:
            self.setItemDelegateForColumn(GUTTER_COLUMN, self.gutterDelegate)
            header = self.header()
            # the gutter moves to visual position 0 with a fixed width; the
            # tree branches stay on the name column
            header.moveSection(GUTTER_COLUMN, 0)
            if header.minimumSectionSize() > GUTTER_WIDTH:
                header.setMinimumSectionSize(GUTTER_WIDTH)
            header.setSectionResizeMode(
                GUTTER_COLUMN, QtWidgets.QHeaderView.ResizeMode.Fixed
            )
            header.resizeSection(GUTTER_COLUMN, GUTTER_WIDTH)
        self.setTreePosition(0)
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


class PMState:
    """Client-side cache of a Parameter Manager's Types and Locks.

    The Parameter Manager GUI owns one instance (``ParameterManagerGui.state``)
    so its widgets can react to Types and Locks without querying the Server
    again. It starts empty and is filled from the Parameter Manager — a Proxy
    Instrument or a local one — with :meth:`refresh`; the ``pm-lock-update``
    and ``pm-type-update`` Broadcasts then keep single entries current through
    :meth:`apply_lock` and :meth:`apply_type` (D22).

    ``types`` maps each Type's name to its :class:`PMTypeBluePrint`; ``locks``
    maps each Follower's path relative to the Parameter Manager — the form
    ``list_locks()`` returns — to its :class:`PMLockBluePrint`.
    """

    def __init__(self) -> None:
        self.types: Dict[str, PMTypeBluePrint] = {}
        self.locks: Dict[str, PMLockBluePrint] = {}

    def refresh(self, instrument: Any) -> None:
        """Re-read every Type and Lock from the Parameter Manager.

        Works with a Proxy Instrument and with a local Parameter Manager:
        both expose ``list_types``, ``get_type`` and ``list_locks``.

        :param instrument: the Parameter Manager whose Types and Locks to
            read.
        """
        self.types = {
            type_name: instrument.get_type(type_name)
            for type_name in instrument.list_types()
        }
        self.locks = dict(instrument.list_locks())

    def apply_lock(self, path: str, lock: Optional[PMLockBluePrint]) -> None:
        """Record the change a ``pm-lock-update`` Broadcast reports about
        the Follower at ``path``.

        :param path: the Follower's path relative to the Parameter Manager.
        :param lock: the Follower's :class:`PMLockBluePrint`, or ``None``
            when its Lock was removed (the entry is dropped then).
        """
        if lock is None:
            self.locks.pop(path, None)
        else:
            self.locks[path] = lock

    def apply_type(self, name: str, type_blueprint: Optional[PMTypeBluePrint]) -> None:
        """Record the change a ``pm-type-update`` Broadcast reports about
        the Type ``name``.

        :param name: the Type's name.
        :param type_blueprint: the Type's :class:`PMTypeBluePrint`, or
            ``None`` when the Type was removed (the entry is dropped then).
        """
        if type_blueprint is None:
            self.types.pop(name, None)
        else:
            self.types[name] = type_blueprint


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
            modelType=ModelParameterManager,
            **kwargs,
        )
        # The client-side cache of the Parameter Manager's Types and Locks.
        # Created before connectSignals, which wires the model's Broadcast
        # routing into it.
        self.state = PMState()
        # The tint palette: maps each Type to its slot in TINT_PALETTE; the
        # view's gutter delegate reads the colours from it.
        self.typePalette = TypePalette()
        self.view.gutterDelegate.typePalette = self.typePalette
        self.profileManager = ProfilesManager(parent=self)
        self.addParam = AddParameterWidget(parent=self)
        layout = self.layout()
        assert isinstance(layout, QtWidgets.QVBoxLayout)
        layout.insertWidget(0, self.profileManager)
        layout.addWidget(self.addParam)
        # The existing content becomes tab 0 of the tab widget; the Types
        # tab stays an empty placeholder until its own task builds it.
        self.parametersTab = QtWidgets.QWidget(self)
        self.parametersTab.setLayout(self.layout())
        self.typesTab = QtWidgets.QWidget(self)
        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.addTab(self.parametersTab, "Parameters")
        self.tabs.addTab(self.typesTab, "Types")
        outerLayout = QtWidgets.QVBoxLayout(self)
        outerLayout.setContentsMargins(0, 0, 0, 0)
        outerLayout.addWidget(self.tabs)
        self.connectSignals()
        self.loadProfile()

    def connectSignals(self) -> None:
        super().connectSignals()
        self.view.delegate.removeParameter.connect(self.removeParameter)
        self.addParam.newParamRequested.connect(self.addParameter)
        self.parameterCreationError.connect(self.addParam.setError)
        self.parameterCreated.connect(self.addParam.clear)
        self.profileManager.indexChanged.connect(self.loadProfile)
        self.model.lockChanged.connect(self.state.apply_lock)
        self.model.typeChanged.connect(self._on_type_changed)
        self.model.structureChanged.connect(self.apply_tints)
        self.shortcutManager.register("delete_item", self._deleteCurrentItem, self)
        self.shortcutManager.register("clear_add", self.addParam.clear, self)
        self.shortcutManager.register("add_item", self.addParam.nameEdit.setFocus, self)
        self.shortcutManager.register("load_items", self.loadFromFile, self)
        self.shortcutManager.register("save_items", self.saveToFile, self)

    @QtCore.Slot()
    def _deleteCurrentItem(self) -> None:
        item = self._getCurrentItem()
        if item is not None:
            self.removeParameter(item.name)

    def makeToolbar(self) -> QtWidgets.QToolBar:
        toolbar = super().makeToolbar()

        toolbar.addSeparator()

        loadParamAction = toolbar.addAction(
            QtGui.QIcon(":/icons/load.svg"),
            "Load parameters from file",
        )
        loadParamAction.triggered.connect(lambda x: self.loadFromFile())  # type: ignore[union-attr]
        self.shortcutManager.register_tooltip("load_items", loadParamAction)

        saveParamAction = toolbar.addAction(
            QtGui.QIcon(":/icons/save.svg"),
            "Save parameters to file",
        )
        saveParamAction.triggered.connect(lambda x: self.saveToFile())  # type: ignore[union-attr]
        self.shortcutManager.register_tooltip("save_items", saveParamAction)

        return toolbar

    def refreshAll(self) -> None:
        super().refreshAll()
        self.instrument.refresh_profiles()
        self.profileManager.refresh()
        self.state.refresh(self.instrument)
        self.apply_tints()

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
        # a profile load emits no parameter-creation/parameter-deletion
        # Broadcasts for the parameters it (re)creates, so the state of the
        # Types and Locks must be re-read from the Parameter Manager
        self.state.refresh(self.instrument)
        self.apply_tints()

    @QtCore.Slot(str, object)
    def _on_type_changed(
        self, name: str, type_blueprint: Optional[PMTypeBluePrint]
    ) -> None:
        """Record the change a ``pm-type-update`` Broadcast reports about
        the Type ``name`` in the state, then recompute the tints and gutter
        bands it may change."""
        self.state.apply_type(name, type_blueprint)
        self.apply_tints()

    @QtCore.Slot()
    def apply_tints(self) -> None:
        """Recompute every row's Type claims and repaint the tints and
        gutter bands (plan task 5.2).

        Runs after the state was refreshed from the Parameter Manager (on a
        model reload), on every ``pm-type-update`` Broadcast, and after a
        parameter was created or removed by a Broadcast, since matching
        depends on which parameters exist.
        """
        self.typePalette.sync(self.state.types)
        claims = compute_claims(self.state.types, self._model_parameters())
        self._apply_tints_to_rows(self.model.invisibleRootItem(), claims)

    def _model_parameters(self) -> Dict[str, str]:
        """Every parameter row of the source model as ``{path: unit}``."""
        parameters: Dict[str, str] = {}
        self._collect_parameters(self.model.invisibleRootItem(), parameters)
        return parameters

    def _collect_parameters(
        self, parent: QtGui.QStandardItem, parameters: Dict[str, str]
    ) -> None:
        for row in range(parent.rowCount()):
            item = parent.child(row, 0)
            if item is None:
                continue
            if item.element is not None:  # type: ignore[attr-defined]
                # a parameter row; a submodule row's element is None
                unitItem = parent.child(row, 1)
                parameters[item.name] = "" if unitItem is None else unitItem.text()
            if item.hasChildren():
                self._collect_parameters(item, parameters)

    def _apply_tints_to_rows(
        self, parent: QtGui.QStandardItem, claims: Dict[str, Claim]
    ) -> None:
        """Tint every row of ``parent`` that has a Claim with the Claiming
        Type's colour on all columns and store its Type stack on the gutter
        item; clear the background of the rows without one."""
        for row in range(parent.rowCount()):
            rowItems = [parent.child(row, col) for col in range(GUTTER_COLUMN + 1)]
            item = rowItems[0]
            if item is None:
                continue
            gutterItem = rowItems[GUTTER_COLUMN]
            if gutterItem is None:
                gutterItem = QtGui.QStandardItem()
                parent.setChild(row, GUTTER_COLUMN, gutterItem)
            claim = claims.get(item.name)
            colours = (
                self.typePalette.colours(claim.type) if claim is not None else None
            )
            if claim is not None and colours is not None:
                # claimed rows carry the Claiming Type's tint, alternating
                # with tintAlt over the sibling rows so the striping survives
                background = colours["tintAlt"] if item.row() % 2 else colours["tint"]
                for rowItem in rowItems:
                    if rowItem is not None:
                        rowItem.setData(
                            background, QtCore.Qt.ItemDataRole.BackgroundRole
                        )
                gutterItem.setData(claim.stack[:3], GUTTER_ROLE)
            else:
                # a lost claim reverts the row to the default look
                for rowItem in rowItems:
                    if rowItem is not None:
                        rowItem.setData(None, QtCore.Qt.ItemDataRole.BackgroundRole)
                gutterItem.setData([], GUTTER_ROLE)
            if item.hasChildren():
                self._apply_tints_to_rows(item, claims)

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
