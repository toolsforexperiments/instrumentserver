import ast
import inspect
import logging
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
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
        # dropped, and the Lock column item (plan task 5.3)
        self.setColumnCount(LOCK_COLUMN + 1)
        self.setHorizontalHeaderLabels([self.attr, "unit", "", "", "locked to"])
        self._ensure_extra_items(self.invisibleRootItem())

    def _ensure_extra_items(self, parent: QtGui.QStandardItem) -> None:
        """Give every row under ``parent`` its gutter item and its Lock
        column item."""
        for row in range(parent.rowCount()):
            for column in (GUTTER_COLUMN, LOCK_COLUMN):
                if parent.child(row, column) is None:
                    parent.setChild(row, column, QtGui.QStandardItem())
            item = parent.child(row, 0)
            if item is not None and item.hasChildren():
                self._ensure_extra_items(item)

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
            lockItem = QtGui.QStandardItem()

            if parent == self:
                rowCount = self.rowCount()
                self.setItem(rowCount, 0, item)
                self.setItem(rowCount, 1, unitItem)
                self.setItem(rowCount, 2, extraItem)
                self.setItem(rowCount, GUTTER_COLUMN, gutterItem)
                self.setItem(rowCount, LOCK_COLUMN, lockItem)
            else:
                parent.appendRow([item, unitItem, extraItem, gutterItem, lockItem])

            self.newItem.emit(item)

    def _has_row(self, full_name: str) -> bool:
        """Whether the model holds a row for the dotted path ``full_name``
        (the Broadcast name with the instrument name stripped)."""
        return bool(
            self.findItems(
                full_name,
                cast(
                    "QtCore.Qt.MatchFlags",
                    QtCore.Qt.MatchFlag.MatchExactly
                    | QtCore.Qt.MatchFlag.MatchRecursive,
                ),
                0,
            )
        )

    def updateParameter(self, bp: ParameterBroadcastBluePrint) -> None:
        fullName = ".".join(bp.name.split(".")[1:])
        known_row = bp.action == PARAMETER_UPDATE and self._has_row(fullName)
        super().updateParameter(bp)
        # a parameter-update for a row the model did not know adds one
        # through the base update branch; matching depends on which
        # parameters exist, so the tints and gutter bands must be
        # recomputed for it too (plan task 5.6), or the new row would
        # stay untinted until the next recompute
        added_row = (
            bp.action == PARAMETER_UPDATE
            and not known_row
            and self._has_row(fullName)
        )
        if bp.action in (PARAMETER_CREATION, PARAMETER_DELETION) or added_row:
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


def _instance_candidates(parameters: Mapping[str, str]) -> List[str]:
    """Every submodule path the parameter rows imply, sorted: every proper
    dotted prefix of a parameter path, never the root and never anything
    under the Globals submodule (D12). This is the candidate set both
    :func:`compute_claims` and :func:`instances_of_type` match against."""
    candidates = set()
    for path in parameters:
        segments = path.split(".")
        for depth in range(1, len(segments)):
            candidate = ".".join(segments[:depth])
            if "_globals" in candidate.split("."):
                continue  # Globals is excluded from matching at any depth
            candidates.add(candidate)
    return sorted(candidates)


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
    candidates = _instance_candidates(parameters)

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
        for instance in candidates:
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


# ----------------- Parameter Manager Locks - Beginning --------------------------------


#: Logical index of the Lock column of :class:`ModelParameterManager`
#: (plan task 5.3). The existing columns keep their indexes: name (0),
#: unit (1), delegate (2), gutter (3). The view shows the Lock column
#: between the unit and the delegate column.
LOCK_COLUMN = 4

#: Fixed default pixel width of the Lock column in the view (the user can
#: resize it: the section is Interactive).
LOCK_COLUMN_WIDTH = 140

#: The mock's one purple (its ``--log-value`` token): the fill of a row's
#: lock button while its Lock is locked.
LOCK_COLOUR = "#7e5bef"


def lock_button_tooltip(locked: bool, target: str) -> str:
    """The lock/relock button's tooltip for one Lock state (the mock's
    strings), with ``target`` relative to the Parameter Manager. Shared by
    the tree's per-row widget (plan task 5.3) and the Locks panel (plan
    task 5.4)."""
    if locked:
        return f"locked to {target} — unlock and go back to its own value"
    return f"unlocked — lock to {target} again"


def make_lock_button(
    parent: QtWidgets.QWidget, locked: bool, target: Optional[str] = None
) -> QtWidgets.QPushButton:
    """The lock/relock toggle button shared by the tree's per-row widget
    (plan task 5.3) and the Locks panel (plan task 5.4): the lock icon and
    the purple ``locked`` fill. ``target`` is the Target relative to the
    Parameter Manager for the state tooltip; the tree's delegate passes
    ``None`` and leaves the tooltip to
    :meth:`ParameterManagerGui._update_row_lock_widget`."""
    button = QtWidgets.QPushButton(
        QtGui.QIcon(":/icons/lock.svg"), "", parent=parent
    )
    button.setProperty("locked", locked)
    button.setStyleSheet(
        f"QPushButton[locked=\"true\"] {{ background-color: {LOCK_COLOUR} }}"
    )
    if target is not None:
        button.setToolTip(lock_button_tooltip(locked, target))
    keepSmallHorizontally(button)
    return button


def relative_path(full: str, instrument_name: str) -> str:
    """The path relative to the Parameter Manager: ``full`` with the
    ``<instrument_name>.`` prefix stripped. ``PMLockBluePrint.target``
    stores the full dotted path, while model item names and every string
    the GUI shows the user are relative to the Parameter Manager."""
    prefix = f"{instrument_name}."
    return full[len(prefix):] if full.startswith(prefix) else full


def lock_column_text(
    path: str,
    locks: Mapping[str, PMLockBluePrint],
    instrument_name: str,
) -> str:
    """The text the Lock column shows for the parameter row ``path`` (a
    path relative to the Parameter Manager), computed client-side over the
    state's Locks (plan task 5.3; the mock's lock cell).

    A Follower shows its own Lock state: ``locked to <target>`` while
    locked, ``unlocked · <target>`` (middle dot) while unlocked, with the
    Target relative to the Parameter Manager. A parameter that is no
    Follower but the Target of ``N`` Locks — locked and unlocked alike,
    the way :meth:`ParameterManager.followers_of` counts — shows
    ``target ×N`` (multiplication sign). Every other row shows nothing.

    A row that is both Follower and Target shows its Follower text, which
    wins over the Target note (the mock's ``rec.lockedTo || srcNote(p)``).
    """
    lock = locks.get(path)
    if lock is not None:
        # the Follower's own Lock state wins over the Target note
        target = relative_path(lock.target, instrument_name)
        if lock.locked:
            return f"locked to {target}"
        return f"unlocked · {target}"
    full_path = f"{instrument_name}.{path}"
    count = sum(1 for other in locks.values() if other.target == full_path)
    if count:
        return f"target ×{count}"
    return ""


def followers_reaching(
    path: str,
    locks: Mapping[str, PMLockBluePrint],
    instrument_name: str,
) -> List[str]:
    """Paths (relative to the Parameter Manager) of every Follower whose
    locked Lock targets the parameter at ``path``, directly or over a
    chain of locked Locks.

    Only locked hops count (D7): an unlocked Lock answers ``get`` with its
    own value, so the Followers behind it do not see an update made past
    it. The walk follows each hop's Target and stops there — no infinite
    loop on a cycle, and every Follower appears once.
    """
    prefix = f"{instrument_name}."
    found: List[str] = []
    seen: set = set()
    targets = [prefix + path]
    index = 0
    while index < len(targets):
        current = targets[index]
        index += 1
        for follower, lock in locks.items():
            if not lock.locked or lock.target != current or follower in seen:
                continue
            seen.add(follower)
            found.append(follower)
            targets.append(prefix + follower)
    return found


def rank_lock_targets(
    follower: str,
    candidates: Iterable[str],
    claims: Mapping[str, Claim],
    arm_rel: Optional[str] = None,
) -> List[str]:
    """The arm strip's Target candidates in the mock's completer order.

    ``arm_rel`` is the Follower's path relative to its Instance (the part
    behind the Claiming Type's Instance path), or ``None`` when the
    Follower is claimed by no Type; an explicit ``arm_rel`` argument
    overrides it, which the Types tab's Type Lock re-target (plan task
    5.5) uses to rank for a Type's entry path — there is no claimed
    Follower and so nothing to exclude. Rank 0: the candidate's own
    relative path equals ``arm_rel`` (the same leaf on a sibling Instance,
    the mock's first pick). Rank 1: ``.<arm_rel>`` occurs in the candidate
    (a submodule on the way). Rank 2: everything else. Equal ranks order
    alphabetically; the Follower itself is never a candidate. Cycles are
    not filtered here: the Server refuses them and the arm strip shows its
    error text.
    """
    if arm_rel is None:
        follower_claim = claims.get(follower)
        arm_rel = (
            follower[len(follower_claim.instance) + 1:]
            if follower_claim is not None
            else None
        )

    def own_rel(candidate: str) -> Optional[str]:
        claim = claims.get(candidate)
        if claim is None:
            return None
        return candidate[len(claim.instance) + 1:]

    ranked: List[Tuple[int, str]] = []
    for candidate in candidates:
        if candidate == follower:
            continue  # the Follower itself is never a candidate
        rel = own_rel(candidate)
        if arm_rel is not None and rel == arm_rel:
            rank = 0
        elif arm_rel is not None and f".{arm_rel}" in candidate:
            rank = 1
        else:
            rank = 2
        ranked.append((rank, candidate))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))
    return [path for _, path in ranked]


@dataclass
class LockRow:
    """One row of the Locks panel (plan task 5.4): a Target of one or more
    Locks — plain, or the Target of a Type Lock — and the Followers beneath
    it, recursively for chains. ``type_locks`` holds every ``(Type name,
    entry path)`` whose Type Lock Target the row is; ``lock`` is the row's
    own Lock (``None`` for a plain Target)."""

    path: str
    type_locks: List[Tuple[str, str]]
    lock: Optional[PMLockBluePrint]
    children: List["LockRow"]


def lock_root(
    path: str,
    locks: Mapping[str, PMLockBluePrint],
    instrument_name: str,
) -> str:
    """The end of the chain of locked Locks that starts at ``path`` (the
    mock's ``root``): the parameter a locked read at ``path`` finally asks.
    Only locked hops count (D7): an unlocked Lock answers ``get`` with its
    own value, so the walk stops there. A ``seen`` set guards against a
    cycle. Paths are relative to the Parameter Manager, except the stored
    ``PMLockBluePrint.target``, which is relativized on the way."""
    current = path
    seen: set = set()
    while current not in seen:
        seen.add(current)
        lock = locks.get(current)
        if lock is None or not lock.locked:
            return current
        current = relative_path(lock.target, instrument_name)
    return current


def build_lock_rows(
    locks: Mapping[str, PMLockBluePrint],
    types: Mapping[str, PMTypeBluePrint],
    instrument_name: str,
) -> List[LockRow]:
    """The Locks panel's rows from the client-side state (plan task 5.4;
    the mock's locks-panel walk).

    ``locks`` maps each Follower's path (relative to the Parameter
    Manager) to its :class:`PMLockBluePrint`; ``types`` maps each Type's
    name to its :class:`PMTypeBluePrint`. An unlocked Lock still
    remembers its Target (D5), so a Follower's Lock names its Target
    whether the Lock is locked or not.

    The Targets are the unique Targets of the Locks, in ``locks`` order.
    The roots are the Targets that carry no Lock of their own, the Type
    Lock Targets first (a stable sort, like the mock's), each walked
    recursively into its Followers — a ``seen`` set guards against loops —
    and then any Target the first walk did not reach (the mock's second
    pass, e.g. a cycle among Followers). Every row carries its own Lock
    (``None`` for a plain Target) and its ``(Type, entry)`` pairs.
    """

    def target_of(follower: str) -> Optional[str]:
        lock = locks.get(follower)
        return (
            None if lock is None else relative_path(lock.target, instrument_name)
        )

    targets: List[str] = []
    for follower in locks:
        target = target_of(follower)
        if target is not None and target not in targets:
            targets.append(target)

    def type_locks_at(path: str) -> List[Tuple[str, str]]:
        found: List[Tuple[str, str]] = []
        for type_name, blueprint in types.items():
            for entry_path, spec in blueprint.parameters.items():
                entry_target = spec.get("target")
                if (
                    entry_target is not None
                    and relative_path(entry_target, instrument_name) == path
                ):
                    found.append((type_name, entry_path))
        return found

    def followers(path: str) -> List[str]:
        return [
            follower for follower in locks if target_of(follower) == path
        ]

    rows: List[LockRow] = []
    seen: set = set()

    def walk(path: str) -> Optional[LockRow]:
        if path in seen:
            return None
        seen.add(path)
        row = LockRow(
            path=path,
            type_locks=type_locks_at(path),
            lock=locks.get(path),
            children=[],
        )
        for child_path in followers(path):
            child = walk(child_path)
            if child is not None:
                row.children.append(child)
        return row

    # Type Lock Targets first, plain Targets follow — a stable sort,
    # like the mock's
    roots = [target for target in targets if target not in locks]
    roots.sort(key=lambda target: 0 if type_locks_at(target) else 1)
    for target in roots:
        row = walk(target)
        if row is not None:
            rows.append(row)
    # the mock's second pass: any Target the first walk did not reach
    for target in targets:
        row = walk(target)
        if row is not None:
            rows.append(row)
    return rows


def _lock_row_paths(rows: List[LockRow]) -> List[str]:
    """Every row path of the built rows, depth first."""
    paths: List[str] = []
    for row in rows:
        paths.append(row.path)
        paths.extend(_lock_row_paths(row.children))
    return paths


class LockArmStrip(QtWidgets.QWidget):
    """The arm strip under the toolbar while a Lock's Target is being
    picked (plan task 5.3): a label naming the Follower, a line edit with
    a completer over the ranked candidate paths, a Cancel button and an
    error label for the Server's refusal text.

    Picking works three ways: a completion from the popup, Return with the
    exact typed path (or the first completion the completer filters for
    the typed text; a text that matches no candidate picks nothing), and
    clicking a tree row — the last one is wired by the Parameter Manager
    GUI, which owns the strip. Cancel is the button or Escape while the
    strip or one of its children has focus."""

    #: Signal(str)
    #: Emitted when a Target was picked. The path is relative to the
    #: Parameter Manager.
    targetPicked = QtCore.Signal(str)

    #: Signal()
    #: Emitted when the user cancels the pick (Cancel button or Escape).
    cancelled = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QtWidgets.QLabel(self)

        self.lineEdit = QtWidgets.QLineEdit(self)
        self.lineEdit.setPlaceholderText("type part of the target path, or click a row")

        # the completer keeps the ranked candidate order (UnsortedModel)
        # and filters it by what the user typed
        self.completerModel = QtCore.QStringListModel(self)
        self.completer = QtWidgets.QCompleter(self)
        self.completer.setModel(self.completerModel)
        self.completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.completer.setCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive
        )
        self.completer.setModelSorting(
            QtWidgets.QCompleter.ModelSorting.UnsortedModel
        )
        self.lineEdit.setCompleter(self.completer)

        self.cancelButton = QtWidgets.QPushButton("Cancel", self)

        self.errorLabel = QtWidgets.QLabel(self)
        self.errorLabel.setStyleSheet(
            "QLabel { background-color: red; color: white; font-weight: bold }"
        )
        self.errorLabel.setVisible(False)

        layout.addWidget(self.label)
        layout.addWidget(self.lineEdit, 1)
        layout.addWidget(self.cancelButton)
        layout.addWidget(self.errorLabel)
        self.setLayout(layout)

        self.completer.activated[str].connect(self.targetPicked)  # type: ignore[index]
        self.lineEdit.returnPressed.connect(self._on_return_pressed)
        self.cancelButton.clicked.connect(self.cancelled)

        self.escShortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Escape"), self)
        self.escShortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.escShortcut.activated.connect(self.cancelled)

    @QtCore.Slot()
    def _on_return_pressed(self) -> None:
        """Pick the exact typed path, or the first completion the
        completer filters for the typed text (the mock's Enter picks the
        first match); a text that matches no candidate picks nothing."""
        text = self.lineEdit.text().strip()
        if not text:
            return
        if text in self.completerModel.stringList():
            self.targetPicked.emit(text)
            return
        # the completer's filtered matches for what was typed, in ranked
        # order; its filter mode (MatchContains) and case sensitivity apply
        self.completer.setCompletionPrefix(text)
        if self.completer.completionCount() > 0:
            first = self.completer.completionModel().index(0, 0)
            self.targetPicked.emit(
                self.completer.completionModel().data(
                    first, QtCore.Qt.ItemDataRole.DisplayRole
                )
            )

    def arm(self, follower: str, candidates: List[str]) -> None:
        """Arm the strip for the Follower at ``follower``: name it in the
        label, load the ranked candidates into the completer, clear the
        line edit and any error, show the strip and focus the line edit."""
        self.label.setText(f"Target for {follower}")
        self.completerModel.setStringList(candidates)
        self.lineEdit.clear()
        self.clear_error()
        self.setVisible(True)
        self.lineEdit.setFocus()

    def show_error(self, text: str) -> None:
        """Show the Server's error text on the error label."""
        self.errorLabel.setText(text)
        self.errorLabel.setVisible(True)

    def clear_error(self) -> None:
        """Hide and clear the error label (the next pick or cancel does
        this)."""
        self.errorLabel.setText("")
        self.errorLabel.setVisible(False)

    def disarm(self) -> None:
        """Hide the strip and clear it."""
        self.setVisible(False)
        self.lineEdit.clear()
        self.clear_error()


#: The Locks panel's default note (the mock's ``lockNote``, in glossary
#: words): shown until an action error or a skipped-Lock warning replaces
#: it.
LOCK_PANEL_NOTE = (
    "A Type Lock row — marked with its Type — holds one value for every "
    "Instance of that Type. Unlock a Follower to let it keep its own "
    "value, remove its Lock to take it out; the lock button on the Type "
    "Lock row locks them all again."
)

#: Fixed pixel width of the Locks panel's value column (the mock's value
#: column) and of its buttons column.
LOCK_PANEL_VALUE_WIDTH = 200
LOCK_PANEL_BUTTONS_WIDTH = 84

#: Data role under which a Locks panel row's path (relative to the
#: Parameter Manager) is stored on its first item, so the rows can be
#: found again after a rebuild.
LOCK_ROW_ROLE = cast(
    "QtCore.Qt.ItemDataRole", QtCore.Qt.ItemDataRole.UserRole + 2
)


class LocksPanel(QtWidgets.QWidget):
    """The Locks panel right of the Parameter Manager tree (plan task 5.4;
    the mock's locks panel): one root row per Target — the Type Lock
    Targets first, labelled with their Type — with each Target's Followers
    beneath it, recursively for chains.

    A Target row holds a value editor (a plain ``set`` on the Target); a
    locked Follower row shows its value read-only, and every Follower row
    that is not a Type Lock row carries the lock/relock toggle and the
    remove button. A Type Lock row carries "lock all" and "remove rule".
    The panel never talks to the Server itself: every action is emitted as
    a signal —
    ``toggleLockRequested``, ``removeLockRequested``, ``lockAllRequested``,
    ``removeRuleRequested`` and ``lockSelectionRequested`` — and the
    Parameter Manager GUI, which owns the panel, performs it and reports
    errors and skipped Locks on the note label."""

    #: Signal(str)
    #: Emitted when the user presses a Follower row's lock/relock button;
    #: the path is relative to the Parameter Manager.
    toggleLockRequested = QtCore.Signal(str)

    #: Signal(str)
    #: Emitted when the user presses a Follower row's remove button; the
    #: path is relative to the Parameter Manager.
    removeLockRequested = QtCore.Signal(str)

    #: Signal(str, str, str)
    #: Emitted when the user presses a Type Lock row's "lock all" button:
    #: the Type's name, the entry path, and the entry's stored Target
    #: relative to the Parameter Manager.
    lockAllRequested = QtCore.Signal(str, str, str)

    #: Signal(str, str)
    #: Emitted when the user presses a Type Lock row's "remove rule"
    #: button: the Type's name and the entry path.
    removeRuleRequested = QtCore.Signal(str, str)

    #: Signal()
    #: Emitted when the user presses "Lock selection to…".
    lockSelectionRequested = QtCore.Signal()

    def __init__(
        self, instrument_name: str, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.instrument_name = instrument_name

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.model = QtGui.QStandardItemModel(0, 3, self)
        self.model.setHorizontalHeaderLabels(["locks", "value", ""])

        self.view = QtWidgets.QTreeView(self)
        self.view.setModel(self.model)
        self.view.setHeaderHidden(False)
        self.view.setAlternatingRowColors(True)
        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header = self.view.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, LOCK_PANEL_VALUE_WIDTH)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, LOCK_PANEL_BUTTONS_WIDTH)

        self.lockSelectionButton = QtWidgets.QPushButton(
            "Lock selection to…", self
        )
        self.selectedLabel = QtWidgets.QLabel(self)
        self.selectedLabel.setText("no parameter selected")

        self.noteLabel = QtWidgets.QLabel(self)
        self.noteLabel.setWordWrap(True)
        self.noteLabel.setText(LOCK_PANEL_NOTE)

        layout.addWidget(self.view, 1)
        selectionRow = QtWidgets.QHBoxLayout()
        selectionRow.setContentsMargins(0, 0, 0, 0)
        selectionRow.addWidget(self.lockSelectionButton)
        selectionRow.addWidget(self.selectedLabel, 1)
        layout.addLayout(selectionRow)
        layout.addWidget(self.noteLabel)
        self.setLayout(layout)

        # The widgets of every panel row, keyed by the row path (relative
        # to the Parameter Manager); :meth:`refresh_values` re-reads the
        # values without a rebuild.
        self.rowWidgets: Dict[str, Dict[str, Any]] = {}

        self.lockSelectionButton.clicked.connect(self.lockSelectionRequested)

    def rebuild(
        self,
        rows: List[LockRow],
        elements: Mapping[str, Any],
        types: Mapping[str, PMTypeBluePrint],
        locks: Mapping[str, PMLockBluePrint],
    ) -> None:
        """Rebuild every row from ``rows`` (see :func:`build_lock_rows`).

        ``elements`` maps each row path to the row's parameter object (the
        GUI resolves it through the Proxy or the local instrument);
        ``types`` and ``locks`` are the client-side state the "lock all"
        Target and the tooltips come from. Every row is expanded after the
        rebuild; no collapsed state is kept."""
        self.model.removeRows(0, self.model.rowCount())
        self.rowWidgets = {}
        self._build_rows(rows, elements, types, locks, self.model.invisibleRootItem())
        self.view.expandAll()

    def refresh_values(self, paths: Iterable[str]) -> None:
        """Re-read the value of every named row the panel holds:
        editors through :meth:`ParameterWidget.setWidgetFromParameter`,
        the read-only labels of locked rows through a fresh ``get``. A row
        whose widget is gone — a rebuild replaced it — is skipped."""
        for path in paths:
            entry = self.rowWidgets.get(path)
            if entry is None:
                continue
            try:
                if entry.get("editor") is not None:
                    entry["editor"].setWidgetFromParameter()
                elif (
                    entry.get("label") is not None
                    and entry.get("element") is not None
                ):
                    entry["label"].setText(str(entry["element"].get()))
            except RuntimeError:
                logger.debug(
                    f"Could not refresh the value of {path}. "
                    "Object is not being shown right now."
                )

    def show_error(self, text: str) -> None:
        """Show an action error (the mock's ``lockError``) in red on the
        note label."""
        self.noteLabel.setStyleSheet("QLabel { color: red }")
        self.noteLabel.setText(text)

    def show_note(self, text: str) -> None:
        """Show ``text`` on the note label in the normal colour (a
        skipped-Lock warning, for example)."""
        self.noteLabel.setStyleSheet("")
        self.noteLabel.setText(text)

    def reset_note(self) -> None:
        """Restore the default explanatory note."""
        self.show_note(LOCK_PANEL_NOTE)

    def _build_rows(
        self,
        rows: List[LockRow],
        elements: Mapping[str, Any],
        types: Mapping[str, PMTypeBluePrint],
        locks: Mapping[str, PMLockBluePrint],
        parent_item: QtGui.QStandardItem,
    ) -> None:
        for row in rows:
            if row.type_locks:
                label = (
                    f"[type: {', '.join(t for t, _ in row.type_locks)}] {row.path}"
                )
            else:
                label = row.path
            name_item = QtGui.QStandardItem(label)
            name_item.setData(row.path, LOCK_ROW_ROLE)
            value_item = QtGui.QStandardItem()
            buttons_item = QtGui.QStandardItem()
            parent_item.appendRow([name_item, value_item, buttons_item])
            self._build_row_widgets(
                row,
                elements.get(row.path),
                types,
                locks,
                value_item,
                buttons_item,
            )
            self._build_rows(
                row.children, elements, types, locks, name_item
            )

    def _build_row_widgets(
        self,
        row: LockRow,
        element: Any,
        types: Mapping[str, PMTypeBluePrint],
        locks: Mapping[str, PMLockBluePrint],
        value_item: QtGui.QStandardItem,
        buttons_item: QtGui.QStandardItem,
    ) -> None:
        """Build one row's value cell (a read-only label for a locked
        Follower, a value editor for every other row with a parameter) and
        its buttons cell (the Type Lock controls, or the Follower's toggle
        and remove), and record the widgets in ``rowWidgets``."""
        path = row.path
        entry: Dict[str, Any] = {
            "element": element,
            "editor": None,
            "label": None,
            "toggle": None,
            "remove": None,
            "lockAll": None,
            "removeRule": None,
        }
        self.rowWidgets[path] = entry

        if row.lock is not None and row.lock.locked:
            # a locked Follower reads its Target's value (D3) and refuses
            # writes: a read-only label, like the mock's
            target = relative_path(row.lock.target, self.instrument_name)
            root = lock_root(path, locks, self.instrument_name)
            label = QtWidgets.QLabel(self.view.viewport())
            value = ""
            if element is not None:
                try:
                    value = element.get()
                except Exception as exc:
                    logger.debug(f"could not read the value of {path}: {exc}")
            label.setText(str(value))
            label.setToolTip(f"locked to {target} — set the value on {root}")
            self.view.setIndexWidget(self.model.indexFromItem(value_item), label)
            entry["label"] = label
        elif element is not None:
            editor = ParameterWidget(element, self.view.viewport())
            if row.type_locks:
                tooltip = (
                    f"set the value — every Instance of "
                    f"{row.type_locks[0][0]} follows it"
                )
            else:
                tooltip = "set the Target value — every locked Follower follows it"
            editor.setButton.setToolTip(tooltip)
            self.view.setIndexWidget(self.model.indexFromItem(value_item), editor)
            entry["editor"] = editor

        container: Optional[QtWidgets.QWidget] = None
        if row.type_locks:
            # the Type Lock controls; like the mock, the first (Type,
            # entry) pair acts when several share the Target
            type_name, entry_path = row.type_locks[0]
            blueprint = types.get(type_name)
            spec = (
                blueprint.parameters.get(entry_path, {})
                if blueprint is not None
                else {}
            )
            stored = spec.get("target")
            stored_relative = (
                relative_path(stored, self.instrument_name)
                if stored is not None
                else path
            )
            container = QtWidgets.QWidget(self.view.viewport())
            buttons_layout = QtWidgets.QHBoxLayout(container)
            buttons_layout.setContentsMargins(0, 0, 0, 0)
            lock_all = QtWidgets.QPushButton(
                QtGui.QIcon(":/icons/lock.svg"), "", parent=container
            )
            lock_all.setToolTip(f"lock every Instance of {type_name} to this again")
            keepSmallHorizontally(lock_all)
            lock_all.pressed.connect(
                lambda: self.lockAllRequested.emit(
                    type_name, entry_path, stored_relative
                )
            )
            remove_rule = QtWidgets.QPushButton(
                QtGui.QIcon(":/icons/delete.svg"), "", parent=container
            )
            remove_rule.setStyleSheet("QPushButton { background-color: salmon }")
            remove_rule.setToolTip(
                "remove the Type Lock — the Instances' Locks stay until "
                "removed one by one"
            )
            keepSmallHorizontally(remove_rule)
            remove_rule.pressed.connect(
                lambda: self.removeRuleRequested.emit(type_name, entry_path)
            )
            buttons_layout.addWidget(lock_all)
            buttons_layout.addWidget(remove_rule)
            entry["lockAll"] = lock_all
            entry["removeRule"] = remove_rule
        elif row.lock is not None:
            # a Follower's lock/relock toggle and remove button
            container = QtWidgets.QWidget(self.view.viewport())
            buttons_layout = QtWidgets.QHBoxLayout(container)
            buttons_layout.setContentsMargins(0, 0, 0, 0)
            target = relative_path(row.lock.target, self.instrument_name)
            toggle = make_lock_button(container, row.lock.locked, target)
            toggle.pressed.connect(
                lambda follower=path: self.toggleLockRequested.emit(follower)
            )
            remove = QtWidgets.QPushButton(
                QtGui.QIcon(":/icons/delete.svg"), "", parent=container
            )
            remove.setStyleSheet("QPushButton { background-color: salmon }")
            remove.setToolTip(f"remove the Lock — {path} keeps its own value")
            keepSmallHorizontally(remove)
            remove.pressed.connect(
                lambda follower=path: self.removeLockRequested.emit(follower)
            )
            buttons_layout.addWidget(toggle)
            buttons_layout.addWidget(remove)
            entry["toggle"] = toggle
            entry["remove"] = remove
        if container is not None:
            self.view.setIndexWidget(
                self.model.indexFromItem(buttons_item), container
            )


# ----------------- Parameter Manager Locks - Ending -----------------------------------


# ----------------- Parameter Manager Types tab - Beginning ----------------------------


@dataclass
class EntryRow:
    """One row of the Types tab's entries pane (plan task 5.5; the mock's
    ``tParamRows``): a submodule row of the selected Type's tree, or one
    entry of it.

    ``kind`` is ``"submodule"`` or ``"entry"``. A submodule row carries
    ``nested_type`` — the Type required at that submodule, or ``None`` for
    a structural row that only carries the rows below it. An entry row
    carries
    the effective entry's ``unit`` and defining Type (``from_type``),
    whether the selected Type defines the entry itself (``own``), its
    ``default`` — an own entry's stored default, a Nested Type entry's
    default as stored on the defining Type — and, own entries only, the
    ``target`` of the entry's Type Lock relative to the Parameter Manager
    (``None`` while it has none).
    """

    path: str
    kind: str
    unit: str = ""
    nested_type: Optional[str] = None
    own: bool = False
    from_type: Optional[str] = None
    default: Any = None
    target: Optional[str] = None


def _nested_type_at(
    blueprint: PMTypeBluePrint,
    types: Mapping[str, PMTypeBluePrint],
    submodule: str,
) -> Optional[str]:
    """The Type required at the submodule ``submodule`` (a dotted path
    relative to the Type ``blueprint``): the walk follows the ``nested``
    maps down the segments, the way :func:`_nested_claim_prefixes` walks.
    ``None`` when no Nested Type is required there — a structural row —
    or when a nested Type of the chain is missing from ``types``."""
    current = blueprint
    for segment in submodule.split("."):
        if current is None:
            return None
        nested_name = current.nested.get(segment)
        if nested_name is None:
            return None
        current = types.get(nested_name)
    return current.name if current is not None else None


def type_entry_rows(
    type_name: str,
    types: Mapping[str, PMTypeBluePrint],
    instrument_name: str = "",
) -> List[EntryRow]:
    """The entries-pane rows of the Type ``type_name`` (plan task 5.5):
    its effective parameter set as a segment-sorted tree of submodule and
    entry rows.

    The sort is segment-wise like the mock's (paths order by their dotted
    segments), so a submodule row sorts directly before the rows below it
    and the list reads as a tree in order.

    An entry the Type defines itself (``from_type == type_name``) is
    ``own``: its ``default`` and ``target`` come from the Type's own
    entry, with the stored Type Lock Target relativized with
    ``instrument_name``. An entry a Nested Type defines shows that Type
    as ``from_type`` and the defining Type's own default for the path
    relative to it (the mock's ``ownerRel``).

    :param type_name: the selected Type's name.
    :param types: the Parameter Manager's Types (``PMState.types``).
    :param instrument_name: the Parameter Manager's name, for
        relativizing the stored Type Lock Targets; without it the stored
        full-form Targets are returned unchanged.
    :return: the rows, parents before children.
    """
    blueprint = types.get(type_name)
    if blueprint is None:
        return []
    at_by_path = _nested_claim_prefixes(blueprint, types)
    rows: List[EntryRow] = []
    submodule_paths: set = set()
    for path in sorted(blueprint.effective, key=lambda entry: entry.split(".")):
        segments = path.split(".")
        for depth in range(1, len(segments)):
            submodule = ".".join(segments[:depth])
            if submodule in submodule_paths:
                continue
            submodule_paths.add(submodule)
            rows.append(
                EntryRow(
                    path=submodule,
                    kind="submodule",
                    nested_type=_nested_type_at(blueprint, types, submodule),
                )
            )
        spec = blueprint.effective[path]
        from_type = spec["from_type"]
        own = from_type == type_name
        if own:
            entry = blueprint.parameters.get(path, {})
            default = entry.get("default")
            target = entry.get("target")
            if target is not None and instrument_name:
                target = relative_path(target, instrument_name)
        else:
            at = at_by_path.get(path, "")
            relative = path[len(at) + 1:] if at else path
            defining = types.get(from_type)
            default = (
                defining.parameters.get(relative, {}).get("default")
                if defining is not None
                else None
            )
            target = None
        rows.append(
            EntryRow(
                path=path,
                kind="entry",
                unit=spec["unit"],
                own=own,
                from_type=from_type,
                default=default,
                target=target,
            )
        )
    return rows


def instances_of_type(
    type_name: str,
    types: Mapping[str, PMTypeBluePrint],
    parameters: Mapping[str, str],
) -> List[str]:
    """Paths (relative to the Parameter Manager) of every Instance of the
    Type ``type_name``, computed client-side over the model's parameter
    rows (plan task 5.5; the mock's ``instancesOf``): the same candidate
    rules :func:`compute_claims` matches by — every proper dotted prefix,
    never the root, never anything under Globals — carrying every
    effective path with the declared unit (D12). An empty Type has no
    Instances. The Instances are sorted, for a stable pane order."""
    blueprint = types.get(type_name)
    if blueprint is None:
        return []
    effective = blueprint.effective
    if not effective:
        return []
    return [
        candidate
        for candidate in _instance_candidates(parameters)
        if _carries_effective_set(candidate, effective, parameters)
    ]


def also_types(
    instance: str,
    types: Mapping[str, PMTypeBluePrint],
    parameters: Mapping[str, str],
) -> List[str]:
    """Every Type the submodule ``instance`` is an Instance of (plan task
    5.5; the mock's ``also`` cell), in ``types`` order. The Types pane
    shows the ones besides the selected Type as ``also <t1>, <t2>``."""
    return [
        type_name
        for type_name in types
        if instance in instances_of_type(type_name, types, parameters)
    ]


def parse_default_text(text: str) -> Any:
    """The value a default line edit's text stands for: ``None`` when the
    text is empty, otherwise the text parsed with ``ast.literal_eval``,
    falling back to the raw string when it does not parse."""
    if text.strip() == "":
        return None
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


#: Fixed pixel widths of the entries pane's unit, "locked to" and default
#: columns (the mock's 60/200/252 trio).
ENTRIES_UNIT_WIDTH = 60
ENTRIES_LOCK_WIDTH = 210
ENTRIES_DEFAULT_WIDTH = 250

#: Fixed pixel widths of the instances pane's parameter-count, "also" and
#: button columns (the mock's 150/160/110 trio).
INSTANCES_COUNT_WIDTH = 110
INSTANCES_ALSO_WIDTH = 160
INSTANCES_BUTTON_WIDTH = 80


class TypesPane(QtWidgets.QWidget):
    """The Types tab (plan task 5.5; the mock's Types view): three panes
    around the selected Type.

    Left: the list of Types — name, number of Instances and number of
    effective parameters, each row tinted with the Type's colour — and the
    New type strip. Right, above: the entries of the selected Type as a
    tree. Own entries carry an editable default (Return or the set button
    commits), a Remove button and the Type Lock toggle in the "locked to"
    column, with a re-target button and the Target's path while locked.
    Entries from Nested Types render read-only with "defined by <type>".
    Submodule rows show ``type: <t>`` in the "locked to" column and, for
    the selected Type's own Nested Types, a Remove button. Beneath the
    tree run the "Add to type" and "Nested type" strips and a note line.
    Right, below: the Instances of the selected Type — name, parameter
    count, the other Types the Instance also carries and a Show button —
    with the New instance strip and a note line.

    The pane never talks to the Server: every action is emitted as a
    signal — ``addTypeRequested``, ``addEntryRequested``,
    ``removeEntryRequested``, ``setDefaultRequested``,
    ``toggleTypeLockRequested``, ``retargetTypeLockRequested``,
    ``addNestedRequested``, ``removeNestedRequested``,
    ``addInstanceRequested`` and ``showInstanceRequested`` — and
    :class:`ParameterManagerGui`, which owns the pane, performs it and
    reports errors and skipped Locks on the pane's note labels.
    """

    #: Signal(str)
    #: Emitted when the user presses the New type strip's Add button;
    #: the name is trimmed and not empty.
    addTypeRequested = QtCore.Signal(str)

    #: Signal(str)
    #: Emitted when the selected Type changes (a row click, or a rebuild
    #: that had to pick one).
    typeSelected = QtCore.Signal(str)

    #: Signal(str, str, str, str)
    #: Emitted when the user presses "Add to type": the Type's name, the
    #: entry path, the default text and the unit.
    addEntryRequested = QtCore.Signal(str, str, str, str)

    #: Signal(str, str)
    #: Emitted when the user presses an own entry's Remove button: the
    #: Type's name and the entry path.
    removeEntryRequested = QtCore.Signal(str, str)

    #: Signal(str, str, str)
    #: Emitted when the user commits an own entry's default editor
    #: (Return or the set button): the Type's name, the entry path and
    #: the editor's text.
    setDefaultRequested = QtCore.Signal(str, str, str)

    #: Signal(str, str)
    #: Emitted when the user presses a Type Lock toggle: the Type's name
    #: and the entry path. The GUI locks or unlocks from the entry's
    #: stored Target.
    toggleTypeLockRequested = QtCore.Signal(str, str)

    #: Signal(str, str)
    #: Emitted when the user presses a locked entry's re-target button:
    #: the Type's name and the entry path.
    retargetTypeLockRequested = QtCore.Signal(str, str)

    #: Signal(str, str, str)
    #: Emitted when the user presses "Add nested type": the Type's name,
    #: the submodule and the Nested Type's name.
    addNestedRequested = QtCore.Signal(str, str, str)

    #: Signal(str, str)
    #: Emitted when the user presses an own Nested Type's Remove button:
    #: the Type's name and the submodule.
    removeNestedRequested = QtCore.Signal(str, str)

    #: Signal(str, str)
    #: Emitted when the user presses the New instance strip's button: the
    #: Type's name and the Instance's name.
    addInstanceRequested = QtCore.Signal(str, str)

    #: Signal(str, str)
    #: Emitted when the user presses an instance row's Show button: the
    #: Type's name and the Instance's name.
    showInstanceRequested = QtCore.Signal(str, str)

    def __init__(
        self, instrument_name: str, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.instrument_name = instrument_name

        # the selected Type, and one requested while the Server call that
        # creates it is still in flight (honoured on the next rebuild)
        self.selectedType: Optional[str] = None
        self.requestedType: Optional[str] = None
        # guards the selection slot against the rebuild's own index changes
        self._building = False

        # the widgets of the entries rows, keyed by row path; and the Show
        # buttons of the instance rows, keyed by instance path
        self.entryWidgets: Dict[str, Dict[str, Any]] = {}
        self.showButtons: Dict[str, QtWidgets.QPushButton] = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)

        # -- left: the list of Types and the New type strip
        typeListPane = QtWidgets.QWidget(self.splitter)
        typeListLayout = QtWidgets.QVBoxLayout(typeListPane)
        typeListLayout.setContentsMargins(0, 0, 0, 0)

        self.typeModel = QtGui.QStandardItemModel(0, 3, self)
        self.typeModel.setHorizontalHeaderLabels(["type", "instances", "parameters"])
        self.typeList = QtWidgets.QTreeView(typeListPane)
        self.typeList.setModel(self.typeModel)
        self.typeList.setRootIsDecorated(False)
        self.typeList.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.typeList.setAlternatingRowColors(True)
        typeHeader = self.typeList.header()
        typeHeader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 70), (2, 90)):
            typeHeader.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.Fixed
            )
            typeHeader.resizeSection(column, width)

        typeStrip = QtWidgets.QHBoxLayout()
        typeStrip.setContentsMargins(0, 0, 0, 0)
        typeStrip.addWidget(QtWidgets.QLabel("New type:"))
        self.newTypeEdit = QtWidgets.QLineEdit(typeListPane)
        self.newTypeEdit.setPlaceholderText("cavity")
        self.addTypeButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/plus-square.svg"), " Add"
        )
        keepSmallHorizontally(self.addTypeButton)
        typeStrip.addWidget(self.newTypeEdit, 1)
        typeStrip.addWidget(self.addTypeButton)
        self.typeNote = QtWidgets.QLabel(typeListPane)

        typeListLayout.addWidget(self.typeList, 1)
        typeListLayout.addLayout(typeStrip)
        typeListLayout.addWidget(self.typeNote)

        # -- right: the entries pane above the instances pane
        rightPane = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Vertical, self.splitter
        )

        entriesPane = QtWidgets.QWidget(rightPane)
        entriesLayout = QtWidgets.QVBoxLayout(entriesPane)
        entriesLayout.setContentsMargins(0, 0, 0, 0)

        self.entriesLabel = QtWidgets.QLabel(entriesPane)
        self.entriesModel = QtGui.QStandardItemModel(0, 4, self)
        self.entriesModel.setHorizontalHeaderLabels(
            ["parameter", "unit", "locked to", "default"]
        )
        self.entriesView = QtWidgets.QTreeView(entriesPane)
        self.entriesView.setModel(self.entriesModel)
        self.entriesView.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.entriesView.setAlternatingRowColors(True)
        entriesHeader = self.entriesView.header()
        entriesHeader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column, width in (
            (1, ENTRIES_UNIT_WIDTH),
            (2, ENTRIES_LOCK_WIDTH),
            (3, ENTRIES_DEFAULT_WIDTH),
        ):
            entriesHeader.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.Interactive
            )
            entriesHeader.resizeSection(column, width)

        entryStrip = QtWidgets.QHBoxLayout()
        entryStrip.setContentsMargins(0, 0, 0, 0)
        entryStrip.addWidget(QtWidgets.QLabel("Name:"))
        self.entryNameEdit = QtWidgets.QLineEdit(entriesPane)
        self.entryNameEdit.setPlaceholderText("pulses.pi.drag_multiplier")
        entryStrip.addWidget(self.entryNameEdit, 2)
        entryStrip.addWidget(QtWidgets.QLabel("Default:"))
        self.entryDefaultEdit = QtWidgets.QLineEdit(entriesPane)
        entryStrip.addWidget(self.entryDefaultEdit, 1)
        entryStrip.addWidget(QtWidgets.QLabel("Unit:"))
        self.entryUnitEdit = QtWidgets.QLineEdit(entriesPane)
        entryStrip.addWidget(self.entryUnitEdit, 1)
        self.addEntryButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/plus-square.svg"), "Add to type"
        )
        keepSmallHorizontally(self.addEntryButton)
        entryStrip.addWidget(self.addEntryButton)

        nestedStrip = QtWidgets.QHBoxLayout()
        nestedStrip.setContentsMargins(0, 0, 0, 0)
        nestedStrip.addWidget(QtWidgets.QLabel("Nested type:"))
        self.nestedTypeCombo = QtWidgets.QComboBox(entriesPane)
        nestedStrip.addWidget(self.nestedTypeCombo, 2)
        nestedStrip.addWidget(QtWidgets.QLabel("at:"))
        self.nestedAtEdit = QtWidgets.QLineEdit(entriesPane)
        self.nestedAtEdit.setPlaceholderText("readout")
        nestedStrip.addWidget(self.nestedAtEdit, 1)
        self.addNestedButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/plus-square.svg"), "Add nested type"
        )
        self.addNestedButton.setToolTip("require another Type at that submodule")
        keepSmallHorizontally(self.addNestedButton)
        nestedStrip.addWidget(self.addNestedButton)

        self.entriesNote = QtWidgets.QLabel(entriesPane)
        self.entriesNote.setWordWrap(True)

        entriesLayout.addWidget(self.entriesLabel)
        entriesLayout.addWidget(self.entriesView, 1)
        entriesLayout.addLayout(entryStrip)
        entriesLayout.addLayout(nestedStrip)
        entriesLayout.addWidget(self.entriesNote)

        instancesPane = QtWidgets.QWidget(rightPane)
        instancesLayout = QtWidgets.QVBoxLayout(instancesPane)
        instancesLayout.setContentsMargins(0, 0, 0, 0)

        self.instancesLabel = QtWidgets.QLabel(instancesPane)
        self.instancesModel = QtGui.QStandardItemModel(0, 4, self)
        self.instancesModel.setHorizontalHeaderLabels(
            ["instance", "parameters", "also", ""]
        )
        self.instancesView = QtWidgets.QTreeView(instancesPane)
        self.instancesView.setModel(self.instancesModel)
        self.instancesView.setRootIsDecorated(False)
        self.instancesView.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.instancesView.setAlternatingRowColors(True)
        instancesHeader = self.instancesView.header()
        instancesHeader.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        for column, width in (
            (1, INSTANCES_COUNT_WIDTH),
            (2, INSTANCES_ALSO_WIDTH),
            (3, INSTANCES_BUTTON_WIDTH),
        ):
            instancesHeader.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.Fixed
            )
            instancesHeader.resizeSection(column, width)

        instanceStrip = QtWidgets.QHBoxLayout()
        instanceStrip.setContentsMargins(0, 0, 0, 0)
        instanceStrip.addWidget(QtWidgets.QLabel("New instance:"))
        self.newInstanceEdit = QtWidgets.QLineEdit(instancesPane)
        self.newInstanceEdit.setPlaceholderText("q04")
        instanceStrip.addWidget(self.newInstanceEdit, 1)
        self.addInstanceButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/plus-square.svg"), "Add instance"
        )
        keepSmallHorizontally(self.addInstanceButton)
        instanceStrip.addWidget(self.addInstanceButton)
        self.instancesNote = QtWidgets.QLabel(instancesPane)

        instancesLayout.addWidget(self.instancesLabel)
        instancesLayout.addWidget(self.instancesView, 1)
        instancesLayout.addLayout(instanceStrip)
        instancesLayout.addWidget(self.instancesNote)

        rightPane.addWidget(entriesPane)
        rightPane.addWidget(instancesPane)
        rightPane.setStretchFactor(0, 3)
        rightPane.setStretchFactor(1, 2)
        self.splitter.addWidget(typeListPane)
        self.splitter.addWidget(rightPane)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        layout.addWidget(self.splitter)
        self.setLayout(layout)

        self.addTypeButton.clicked.connect(self._request_add_type)
        self.newTypeEdit.returnPressed.connect(self.addTypeButton.click)
        self.addEntryButton.clicked.connect(self._request_add_entry)
        for edit in (self.entryNameEdit, self.entryDefaultEdit, self.entryUnitEdit):
            edit.returnPressed.connect(self.addEntryButton.click)
        self.addNestedButton.clicked.connect(self._request_add_nested)
        self.nestedAtEdit.returnPressed.connect(self.addNestedButton.click)
        self.addInstanceButton.clicked.connect(self._request_add_instance)
        self.newInstanceEdit.returnPressed.connect(self.addInstanceButton.click)
        self.typeList.selectionModel().currentChanged.connect(self._on_type_selected)

    # ------------------------------------------------------------------
    # rebuilds (plan task 5.5, readings 2-4, 7-8)
    # ------------------------------------------------------------------

    def select_type(self, name: str) -> None:
        """Request the selection of the Type ``name``: honoured on the
        next rebuild, once the Type is in the state the pane rebuilds
        from. Used after the Server call that creates the Type."""
        self.requestedType = name

    def rebuild(
        self,
        types: Mapping[str, PMTypeBluePrint],
        parameters: Mapping[str, str],
        palette: TypePalette,
    ) -> None:
        """Rebuild the three panes from the client-side state (plan task
        5.5): the Type list from ``types`` with Instances counted over
        ``parameters``, the entries and Instances panes from the selected
        Type, and every row tinted with ``palette``."""
        self._rebuild_type_list(types, parameters, palette)
        self._rebuild_selected_panes(types, parameters, palette)

    def _rebuild_type_list(
        self,
        types: Mapping[str, PMTypeBluePrint],
        parameters: Mapping[str, str],
        palette: TypePalette,
    ) -> None:
        names = list(types)
        selection_changed = False
        if self.requestedType is not None and self.requestedType in types:
            selection_changed = self.selectedType != self.requestedType
            self.selectedType = self.requestedType
            self.requestedType = None
        elif self.selectedType not in types:
            # the first Type is selected when none is; the selection is
            # dropped when the Type is gone
            selection_changed = self.selectedType != (names[0] if names else None)
            self.selectedType = names[0] if names else None
        self.typeModel.removeRows(0, self.typeModel.rowCount())
        current_row = -1
        for row, name in enumerate(names):
            count = len(instances_of_type(name, types, parameters))
            name_item = QtGui.QStandardItem(name)
            instances_item = QtGui.QStandardItem(str(count))
            params_item = QtGui.QStandardItem(str(len(types[name].effective)))
            self.typeModel.appendRow([name_item, instances_item, params_item])
            colours = palette.colours(name)
            if colours is not None:
                for item in (name_item, instances_item, params_item):
                    item.setData(
                        colours["tint"], QtCore.Qt.ItemDataRole.BackgroundRole
                    )
            if name == self.selectedType:
                current_row = row
        self._building = True
        if current_row >= 0:
            self.typeList.setCurrentIndex(self.typeModel.index(current_row, 0))
        else:
            self.typeList.setCurrentIndex(QtCore.QModelIndex())
        self._building = False
        if selection_changed and self.selectedType is not None:
            self.typeSelected.emit(self.selectedType)

    def _rebuild_selected_panes(
        self,
        types: Mapping[str, PMTypeBluePrint],
        parameters: Mapping[str, str],
        palette: TypePalette,
    ) -> None:
        selected = self.selectedType or ""
        # with no Type selected the labels keep no trailing space and the
        # three strips are disabled — their actions all need a Type
        # (plan task 5.6)
        has_type = bool(selected)
        self.entriesLabel.setText(
            f"parameters of {selected}" if has_type else "parameters"
        )
        self.instancesLabel.setText(
            f"instances of {selected}" if has_type else "instances"
        )
        self.addEntryButton.setEnabled(has_type)
        self.addNestedButton.setEnabled(has_type)
        self.addInstanceButton.setEnabled(has_type)
        self._rebuild_nested_combo(selected, types)
        self._rebuild_entries(selected, types, palette)
        self._rebuild_instances(selected, types, parameters, palette)

    def _rebuild_nested_combo(
        self, selected: str, types: Mapping[str, PMTypeBluePrint]
    ) -> None:
        self.nestedTypeCombo.clear()
        self.nestedTypeCombo.addItems(
            sorted(name for name in types if name != selected)
        )

    def _clear_index_widgets(
        self, parent: Optional[QtGui.QStandardItem] = None
    ) -> None:
        """Delete the row widgets the entries view still hosts, so a
        rebuild does not leave the old ones behind."""
        if parent is None:
            parent = self.entriesModel.invisibleRootItem()
        for row in range(parent.rowCount()):
            for column in range(parent.columnCount()):
                child = parent.child(row, column)
                if child is None:
                    continue
                widget = self.entriesView.indexWidget(
                    self.entriesModel.indexFromItem(child)
                )
                if widget is not None:
                    widget.deleteLater()
            first = parent.child(row, 0)
            if first is not None and first.hasChildren():
                self._clear_index_widgets(first)

    def _entry_tint_type(
        self, rows: List[EntryRow], index: int, selected: str
    ) -> str:
        """The Type whose tint an entries row shows: an entry row its
        defining Type, a Nested Type row the Type required there, and a
        structural submodule row the defining Type of the first entry
        below it (the selected Type when that entry is own; the mock's
        ``tintsFor(inc ? inc.type : (p.from || selType))``)."""
        row = rows[index]
        if row.kind == "entry":
            return row.from_type or selected
        if row.nested_type is not None:
            return row.nested_type
        for later in rows[index + 1:]:
            if later.kind == "entry":
                return later.from_type or selected
        return selected

    def _rebuild_entries(
        self, selected: str, types: Mapping[str, PMTypeBluePrint], palette: TypePalette
    ) -> None:
        self._clear_index_widgets()
        self.entriesModel.removeRows(0, self.entriesModel.rowCount())
        self.entryWidgets = {}
        blueprint = types.get(selected)
        if selected is None or blueprint is None:
            self.entriesView.expandAll()
            return
        rows = type_entry_rows(selected, types, self.instrument_name)
        items_by_path: Dict[str, QtGui.QStandardItem] = {}
        for index, row in enumerate(rows):
            path = row.path
            parent_item = (
                items_by_path[path.rsplit(".", 1)[0]]
                if "." in path
                else self.entriesModel.invisibleRootItem()
            )
            colours = palette.colours(self._entry_tint_type(rows, index, selected))
            name_item = QtGui.QStandardItem(path.split(".")[-1])
            unit_item = QtGui.QStandardItem("" if row.kind == "submodule" else row.unit)
            lock_item = QtGui.QStandardItem()
            default_item = QtGui.QStandardItem()
            parent_item.appendRow([name_item, unit_item, lock_item, default_item])
            items_by_path[path] = name_item
            if colours is not None:
                for item in (name_item, unit_item, lock_item, default_item):
                    item.setData(
                        colours["tint"], QtCore.Qt.ItemDataRole.BackgroundRole
                    )
            entry: Dict[str, Any] = {
                "editor": None,
                "set": None,
                "remove": None,
                "toggle": None,
                "retarget": None,
                "targetLabel": None,
                "definedBy": None,
                "removeNested": None,
            }
            self.entryWidgets[path] = entry
            if row.kind == "submodule":
                self._build_submodule_row(
                    selected, blueprint, row, lock_item, default_item, entry
                )
            else:
                self._build_entry_row(
                    selected, row, lock_item, default_item, entry
                )
        self.entriesView.expandAll()

    def _build_submodule_row(
        self,
        selected: str,
        blueprint: PMTypeBluePrint,
        row: EntryRow,
        lock_item: QtGui.QStandardItem,
        default_item: QtGui.QStandardItem,
        entry: Dict[str, Any],
    ) -> None:
        if row.nested_type is not None:
            lock_item.setText(f"type: {row.nested_type}")
        if row.path in blueprint.nested:
            # only the selected Type's OWN Nested Types are removable
            nested = blueprint.nested[row.path]
            remove = QtWidgets.QPushButton(
                QtGui.QIcon(":/icons/delete.svg"), "", parent=self.entriesView.viewport()
            )
            remove.setStyleSheet("QPushButton { background-color: salmon }")
            remove.setToolTip(
                f"stop requiring {nested} here — Instances keep the parameters"
            )
            keepSmallHorizontally(remove)
            remove.pressed.connect(
                lambda type_name=selected, submodule=row.path: self.removeNestedRequested.emit(
                    type_name, submodule
                )
            )
            self.entriesView.setIndexWidget(
                self.entriesModel.indexFromItem(default_item), remove
            )
            entry["removeNested"] = remove

    def _build_entry_row(
        self,
        selected: str,
        row: EntryRow,
        lock_item: QtGui.QStandardItem,
        default_item: QtGui.QStandardItem,
        entry: Dict[str, Any],
    ) -> None:
        if row.own:
            self._build_own_entry_cells(selected, row, lock_item, default_item, entry)
        else:
            self._build_nested_entry_cells(selected, row, default_item, entry)

    def _build_own_entry_cells(
        self,
        selected: str,
        row: EntryRow,
        lock_item: QtGui.QStandardItem,
        default_item: QtGui.QStandardItem,
        entry: Dict[str, Any],
    ) -> None:
        # the "locked to" column: the Type Lock toggle, and while the entry
        # is locked the re-target button and the Target's relative path
        locked = row.target is not None
        lock_container = QtWidgets.QWidget(self.entriesView.viewport())
        lock_layout = QtWidgets.QHBoxLayout(lock_container)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        toggle = make_lock_button(lock_container, locked)
        if locked:
            toggle.setToolTip(
                f"locked to {row.target} — unlock and every Instance of "
                f"{selected} goes back to its own value"
            )
        else:
            toggle.setToolTip(
                f"lock — _globals.{selected}.{row.path} is created to hold the "
                f"value, and every Instance of {selected} follows it"
            )
        toggle.pressed.connect(
            lambda type_name=selected, path=row.path: self.toggleTypeLockRequested.emit(
                type_name, path
            )
        )
        lock_layout.addWidget(toggle)
        entry["toggle"] = toggle
        if locked:
            retarget = QtWidgets.QPushButton(
                QtGui.QIcon(":/icons/set.svg"), "", parent=lock_container
            )
            retarget.setToolTip(
                f"lock every Instance of {selected} to another Target — "
                "pick one in the parameter tree"
            )
            keepSmallHorizontally(retarget)
            retarget.pressed.connect(
                lambda type_name=selected, path=row.path: self.retargetTypeLockRequested.emit(
                    type_name, path
                )
            )
            lock_layout.addWidget(retarget)
            entry["retarget"] = retarget
            target_label = QtWidgets.QLabel(row.target, parent=lock_container)
            target_label.setToolTip(
                f"{row.target} — followed by every Instance of {selected}"
            )
            lock_layout.addWidget(target_label, 1)
            entry["targetLabel"] = target_label
        self.entriesView.setIndexWidget(
            self.entriesModel.indexFromItem(lock_item), lock_container
        )

        # the default column: the editable default with its set button and
        # the entry's Remove button
        editor_container = QtWidgets.QWidget(self.entriesView.viewport())
        editor_layout = QtWidgets.QHBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor = QtWidgets.QLineEdit(editor_container)
        editor.setText("" if row.default is None else str(row.default))
        editor.setPlaceholderText("no default")
        set_button = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/set.svg"), "", parent=editor_container
        )
        keepSmallHorizontally(set_button)
        set_button.pressed.connect(
            lambda: self.setDefaultRequested.emit(
                selected, row.path, editor.text()
            )
        )
        editor.returnPressed.connect(set_button.click)
        remove = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/delete.svg"), "", parent=editor_container
        )
        remove.setStyleSheet("QPushButton { background-color: salmon }")
        remove.setToolTip(
            "remove from the Type only — Instances keep the parameter "
            "and lose the Type tint"
        )
        keepSmallHorizontally(remove)
        remove.pressed.connect(
            lambda type_name=selected, path=row.path: self.removeEntryRequested.emit(
                type_name, path
            )
        )
        editor_layout.addWidget(editor, 1)
        editor_layout.addWidget(set_button)
        editor_layout.addWidget(remove)
        self.entriesView.setIndexWidget(
            self.entriesModel.indexFromItem(default_item), editor_container
        )
        entry["editor"] = editor
        entry["set"] = set_button
        entry["remove"] = remove

    def _build_nested_entry_cells(
        self,
        selected: str,
        row: EntryRow,
        default_item: QtGui.QStandardItem,
        entry: Dict[str, Any],
    ) -> None:
        # read-only default text, and "defined by <type>" where the Remove
        # button of an own entry would sit
        container = QtWidgets.QWidget(self.entriesView.viewport())
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        default_label = QtWidgets.QLabel(
            "" if row.default is None else str(row.default), parent=container
        )
        layout.addWidget(default_label, 1)
        defined_by = QtWidgets.QLabel(f"defined by {row.from_type}", parent=container)
        defined_by.setToolTip(
            f"defined by {row.from_type} — change the default there"
        )
        layout.addWidget(defined_by)
        self.entriesView.setIndexWidget(
            self.entriesModel.indexFromItem(default_item), container
        )
        entry["definedBy"] = defined_by

    def _rebuild_instances(
        self,
        selected: str,
        types: Mapping[str, PMTypeBluePrint],
        parameters: Mapping[str, str],
        palette: TypePalette,
    ) -> None:
        self.instancesModel.removeRows(0, self.instancesModel.rowCount())
        self.showButtons = {}
        if not selected:
            return
        colours = palette.colours(selected)
        for instance in instances_of_type(selected, types, parameters):
            count = sum(
                1 for path in parameters if path.startswith(f"{instance}.")
            )
            also = [
                type_name
                for type_name in also_types(instance, types, parameters)
                if type_name != selected
            ]
            name_item = QtGui.QStandardItem(instance)
            count_item = QtGui.QStandardItem(f"{count} parameters")
            also_item = QtGui.QStandardItem(
                f"also {', '.join(also)}" if also else ""
            )
            button_item = QtGui.QStandardItem()
            self.instancesModel.appendRow(
                [name_item, count_item, also_item, button_item]
            )
            if colours is not None:
                for item in (name_item, count_item, also_item, button_item):
                    item.setData(
                        colours["tint"], QtCore.Qt.ItemDataRole.BackgroundRole
                    )
            show = QtWidgets.QPushButton(
                "Show", parent=self.instancesView.viewport()
            )
            show.setToolTip("show in the parameter tree")
            show.pressed.connect(
                lambda type_name=selected, node=instance: self.showInstanceRequested.emit(
                    type_name, node
                )
            )
            self.instancesView.setIndexWidget(
                self.instancesModel.indexFromItem(button_item), show
            )
            self.showButtons[instance] = show

    # ------------------------------------------------------------------
    # selection and strip requests (plan task 5.5, readings 3 and 5)
    # ------------------------------------------------------------------

    @QtCore.Slot(QtCore.QModelIndex, QtCore.QModelIndex)
    def _on_type_selected(
        self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex
    ) -> None:
        """A row click selects the Type for the other two panes."""
        if self._building or not current.isValid():
            return
        name = self.typeModel.item(current.row(), 0)
        if name is None or name.text() == self.selectedType:
            return
        self.selectedType = name.text()
        self.requestedType = None
        self.typeSelected.emit(name.text())

    def refresh_selected_panes(
        self,
        types: Mapping[str, PMTypeBluePrint],
        parameters: Mapping[str, str],
        palette: TypePalette,
    ) -> None:
        """Rebuild only the entries and Instances panes, keeping the Type
        list as it is: the slot of a user selection."""
        self._rebuild_selected_panes(types, parameters, palette)

    @QtCore.Slot()
    def _request_add_type(self) -> None:
        name = self.newTypeEdit.text().strip()
        if not name:
            self.show_type_error("Name must not be empty.")
            return
        self.addTypeRequested.emit(name)

    @QtCore.Slot()
    def _request_add_entry(self) -> None:
        path = self.entryNameEdit.text().strip()
        if not path:
            self.show_entries_error("Name must not be empty.")
            return
        if self.selectedType is None:
            return
        # the unit is stripped: matching compares units exactly (D12), and
        # a trailing space would make the Type match no Instance
        self.addEntryRequested.emit(
            self.selectedType,
            path,
            self.entryDefaultEdit.text(),
            self.entryUnitEdit.text().strip(),
        )

    @QtCore.Slot()
    def _request_add_nested(self) -> None:
        submodule = self.nestedAtEdit.text().strip()
        if not submodule:
            self.show_entries_error("Submodule must not be empty.")
            return
        if self.selectedType is None:
            return
        self.addNestedRequested.emit(
            self.selectedType, submodule, self.nestedTypeCombo.currentText()
        )

    @QtCore.Slot()
    def _request_add_instance(self) -> None:
        name = self.newInstanceEdit.text().strip()
        if not name:
            self.show_instances_error("Name must not be empty.")
            return
        if self.selectedType is None:
            return
        self.addInstanceRequested.emit(self.selectedType, name)

    # ------------------------------------------------------------------
    # note lines (plan task 5.5, reading 5)
    # ------------------------------------------------------------------

    def show_type_error(self, text: str) -> None:
        """Show an action error in red on the New type strip's note."""
        self.typeNote.setStyleSheet("QLabel { color: red }")
        self.typeNote.setText(text)

    def reset_type_note(self) -> None:
        """Restore the New type strip's default note (empty)."""
        self.typeNote.setStyleSheet("")
        self.typeNote.setText("")

    def show_entries_error(self, text: str) -> None:
        """Show an action error in red on the entries pane's note."""
        self.entriesNote.setStyleSheet("QLabel { color: red }")
        self.entriesNote.setText(text)

    def show_entries_note(self, text: str) -> None:
        """Show ``text`` on the entries pane's note in the normal colour
        (a skipped-Lock warning, for example)."""
        self.entriesNote.setStyleSheet("")
        self.entriesNote.setText(text)

    def reset_entries_note(self) -> None:
        """Restore the entries pane's default note (empty)."""
        self.entriesNote.setStyleSheet("")
        self.entriesNote.setText("")

    def show_instances_error(self, text: str) -> None:
        """Show an action error in red on the instances pane's note."""
        self.instancesNote.setStyleSheet("QLabel { color: red }")
        self.instancesNote.setText(text)

    def reset_instances_note(self) -> None:
        """Restore the instances pane's default note (empty)."""
        self.instancesNote.setStyleSheet("")
        self.instancesNote.setText("")


# ----------------- Parameter Manager Types tab - Ending -------------------------------


class ParameterDeleteDelegate(ParameterDelegate):
    #: Signal(str)
    #: Emits the name of the parameter to be deleted when the user presses the delete button.
    removeParameter = QtCore.Signal(str)

    #: Signal(str)
    #: Emits the name of the parameter whose lock button the user pressed;
    #: the Parameter Manager GUI toggles that parameter's Lock.
    toggleLock = QtCore.Signal(str)

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
        lw = self.make_lock_widget(item.name, widget)

        ret = ParameterWidget(
            parameter=element, parent=widget, additionalWidgets=[lw, rw]
        )
        # the lock button is kept on the row's ParameterWidget so the
        # Parameter Manager GUI can restyle it with the Lock state
        ret.lockButton = lw
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

    def make_lock_widget(
        self, fullName: str, widget: QtWidgets.QWidget
    ) -> QtWidgets.QPushButton:
        """The per-row lock button. It stays hidden until the row carries a
        Lock (a Lock-less row shows no button, as the mock), fills purple
        while the Lock is locked, and only :meth:`ParameterManagerGui.
        apply_locks` changes its state."""
        w = make_lock_button(widget, locked=False)
        w.setVisible(False)

        w.pressed.connect(lambda: self.toggleLock.emit(fullName))
        return w

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
    #: Signal(str)
    #: Emitted when the user picks "Lock to…" in the context menu; the
    #: Parameter Manager GUI arms the target picker for that parameter.
    lockToRequested = QtCore.Signal(str)

    #: Signal(str)
    #: Emitted when the user picks "Unlock" in the context menu.
    unlockRequested = QtCore.Signal(str)

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
            if self.model().columnCount() > LOCK_COLUMN:
                # the Lock column moves between the unit and the delegate
                # column, with a resizable default width
                header.moveSection(
                    header.visualIndex(LOCK_COLUMN), header.visualIndex(2)
                )
                header.setSectionResizeMode(
                    LOCK_COLUMN, QtWidgets.QHeaderView.ResizeMode.Interactive
                )
                header.resizeSection(LOCK_COLUMN, LOCK_COLUMN_WIDTH)
        self.setTreePosition(0)
        self.setAllDelegatesPersistent()

        # the lock actions act on the row the context menu was opened for
        # (self.lastSelectedItem, set by the base onContextMenuRequested
        # before the menu opens); the Parameter Manager GUI enables and
        # disables them in its aboutToShow slot
        self.lockToAction = QtWidgets.QAction("Lock to…")
        self.lockToAction.triggered.connect(self._on_lock_to_action_trigger)
        self.unlockAction = QtWidgets.QAction("Unlock")
        self.unlockAction.triggered.connect(self._on_unlock_action_trigger)
        self.contextMenu.addSeparator()
        self.contextMenu.addAction(self.lockToAction)
        self.contextMenu.addAction(self.unlockAction)

    @QtCore.Slot()
    def _on_lock_to_action_trigger(self) -> None:
        """The context menu's "Lock to…": arm the target picker for the
        row's parameter; a submodule row has no Lock to arm."""
        item = self.lastSelectedItem
        if item is not None and item.element is not None:
            self.lockToRequested.emit(item.name)

    @QtCore.Slot()
    def _on_unlock_action_trigger(self) -> None:
        """The context menu's "Unlock": unlock the row's Lock; a submodule
        row has no Lock to unlock."""
        item = self.lastSelectedItem
        if item is not None and item.element is not None:
            self.unlockRequested.emit(item.name)

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
        # The Locks panel (plan task 5.4) sits right of the tree in a
        # splitter: the view keeps its identity, so every existing layout
        # consumer and test keeps working. The panel starts hidden and
        # costs nothing until the toolbar action shows it.
        self.locksPanel = LocksPanel(self.instrument.name, parent=self)
        view_index = layout.indexOf(self.view)
        layout.removeWidget(self.view)
        self.locksSplitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Horizontal, self
        )
        self.locksSplitter.addWidget(self.view)
        self.locksSplitter.addWidget(self.locksPanel)
        self.locksSplitter.setStretchFactor(0, 3)
        self.locksSplitter.setStretchFactor(1, 2)
        layout.insertWidget(view_index, self.locksSplitter)
        self.locksPanel.setVisible(False)
        # The existing content becomes tab 0 of the tab widget; tab 1
        # holds the Types pane (plan task 5.5).
        self.parametersTab = QtWidgets.QWidget(self)
        self.parametersTab.setLayout(self.layout())
        self.typesTab = QtWidgets.QWidget(self)
        typesTabLayout = QtWidgets.QVBoxLayout(self.typesTab)
        typesTabLayout.setContentsMargins(0, 0, 0, 0)
        self.typesPane = TypesPane(self.instrument.name, parent=self.typesTab)
        typesTabLayout.addWidget(self.typesPane)
        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.addTab(self.parametersTab, "Parameters")
        self.tabs.addTab(self.typesTab, "Types")
        outerLayout = QtWidgets.QVBoxLayout(self)
        outerLayout.setContentsMargins(0, 0, 0, 0)
        outerLayout.addWidget(self.tabs)
        # The arm strip sits right under the toolbar and stays hidden until
        # a Lock's Target is being picked (plan task 5.3). The Follower the
        # pick is armed for is kept here, and — for the Types tab's Type
        # Lock re-target (plan task 5.5) — the (Type, entry) pair the
        # re-target is armed for.
        self.armed_follower: Optional[str] = None
        self.armed_type_lock: Optional[Tuple[str, str]] = None
        self.armStrip = LockArmStrip(self.parametersTab)
        parametersLayout = self.parametersTab.layout()
        assert isinstance(parametersLayout, QtWidgets.QVBoxLayout)
        toolbar_index = parametersLayout.indexOf(self.toolbar)
        parametersLayout.insertWidget(toolbar_index + 1, self.armStrip)
        self.armStrip.setVisible(False)
        # Escape over the tree cancels the pick too (harmless when the
        # strip is not armed)
        self.viewEscShortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Escape"), self.view
        )
        self.viewEscShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        self.viewEscShortcut.activated.connect(self.cancel_arm)
        # The confirmation dialog for removing a Lock Target (plan task
        # 5.6), kept on the GUI so tests can drive it; ``None`` while no
        # removal that needs one is in flight.
        self.removalDialog: Optional[QtWidgets.QMessageBox] = None
        self.connectSignals()
        self.loadProfile()

    def connectSignals(self) -> None:
        super().connectSignals()
        self.view.delegate.removeParameter.connect(self.removeParameter)
        self.view.delegate.toggleLock.connect(self._toggle_lock)
        self.addParam.newParamRequested.connect(self.addParameter)
        self.parameterCreationError.connect(self.addParam.setError)
        self.parameterCreated.connect(self.addParam.clear)
        self.profileManager.indexChanged.connect(self.loadProfile)
        self.model.lockChanged.connect(self._on_lock_changed)
        self.model.typeChanged.connect(self._on_type_changed)
        self.model.structureChanged.connect(self.apply_tints)
        self.model.structureChanged.connect(self.apply_locks)
        self.model.itemNewValue.connect(self._on_item_new_value)
        # the filter (and the trash toggle) hides rows; when they come
        # back, restoreCollapsedDict has re-opened their persistent
        # editors, so createEditor has built fresh ParameterWidgets whose
        # lock button is hidden and whose input is editable — re-apply the
        # Lock state to them
        self.proxyModel.filterFinished.connect(self.apply_locks)
        self.view.lockToRequested.connect(self.arm_lock)
        self.view.unlockRequested.connect(self._unlock)
        self.view.contextMenu.aboutToShow.connect(self._update_lock_actions)
        self.view.clicked.connect(self._on_view_clicked)
        self.armStrip.targetPicked.connect(self.pick_lock_target)
        self.armStrip.cancelled.connect(self.cancel_arm)
        # the Locks panel (plan task 5.4): its actions run through this GUI,
        # and the tree's current row drives the panel's selected label
        self.locksAction.toggled.connect(self._on_locks_action_toggled)
        self.locksPanel.toggleLockRequested.connect(self._on_panel_toggle_lock)
        self.locksPanel.removeLockRequested.connect(self._on_panel_remove_lock)
        self.locksPanel.lockAllRequested.connect(self._on_panel_lock_all)
        self.locksPanel.removeRuleRequested.connect(self._on_panel_remove_rule)
        self.locksPanel.lockSelectionRequested.connect(
            self._lock_selection_from_panel
        )
        self.view.selectionModel().currentChanged.connect(
            self._on_tree_current_changed
        )
        # the Types pane (plan task 5.5): its actions run through this GUI,
        # and a selection change re-renders the two panes it drives
        self.typesPane.typeSelected.connect(self._on_pane_type_selected)
        self.typesPane.addTypeRequested.connect(self._on_pane_add_type)
        self.typesPane.addEntryRequested.connect(self._on_pane_add_entry)
        self.typesPane.removeEntryRequested.connect(self._on_pane_remove_entry)
        self.typesPane.setDefaultRequested.connect(self._on_pane_set_default)
        self.typesPane.toggleTypeLockRequested.connect(
            self._on_pane_toggle_type_lock
        )
        self.typesPane.retargetTypeLockRequested.connect(self.arm_type_lock)
        self.typesPane.addNestedRequested.connect(self._on_pane_add_nested)
        self.typesPane.removeNestedRequested.connect(self._on_pane_remove_nested)
        self.typesPane.addInstanceRequested.connect(self._on_pane_add_instance)
        self.typesPane.showInstanceRequested.connect(self._on_pane_show_instance)
        self.shortcutManager.register("delete_item", self._deleteCurrentItem, self)
        self.shortcutManager.register("clear_add", self.addParam.clear, self)
        self.shortcutManager.register("add_item", self.addParam.nameEdit.setFocus, self)
        self.shortcutManager.register("load_items", self.loadFromFile, self)
        self.shortcutManager.register("save_items", self.saveToFile, self)
        self.shortcutManager.register("toggle_locks", self.locksAction.toggle, self)
        # the Lock shortcuts (plan task 5.6); the tree's two lock actions
        # carry their key in their tooltips
        self.shortcutManager.register("lock_to", self._lock_current_item, self)
        self.shortcutManager.register("unlock_item", self._unlock_current_item, self)
        self.shortcutManager.register("show_types", self._toggle_tabs, self)
        self.shortcutManager.register_tooltip("lock_to", self.view.lockToAction)
        self.shortcutManager.register_tooltip("unlock_item", self.view.unlockAction)

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

        # the Locks panel toggle (plan task 5.4); the toggled connection
        # and the shortcut are wired in connectSignals, where the panel
        # exists
        self.locksAction = toolbar.addAction(
            QtGui.QIcon(":/icons/lock.svg"),
            "Show the Locks panel",
        )
        self.locksAction.setCheckable(True)
        self.shortcutManager.register_tooltip("toggle_locks", self.locksAction)

        return toolbar

    def refreshAll(self) -> None:
        super().refreshAll()
        self.instrument.refresh_profiles()
        self.profileManager.refresh()
        self.state.refresh(self.instrument)
        self.apply_tints()
        self.apply_locks()

    def removeParameter(self, fullName: str) -> None:
        """Remove the parameter at ``fullName`` (the row's delete button
        and the delete_item shortcut both land here).

        While the parameter is the Target of Locks — deleting it drops
        them (D3) — a QMessageBox names every Follower that will lose its
        Lock and asks for confirmation (plan task 5.6); Cancel returns
        without touching the Server. A parameter without Followers is
        removed without a dialog."""
        self.removalDialog = None
        if not self.instrument.has_param(fullName):
            return
        try:
            followers = self.instrument.followers_of(fullName)
        except Exception:
            # the Server call failed: fall back to the client-side list
            # computed from the state — locked and unlocked alike, the
            # Targets compared through relative_path
            followers = sorted(
                follower
                for follower, lock in self.state.locks.items()
                if relative_path(lock.target, self.instrument.name) == fullName
            )
        if followers:
            lines = []
            for follower in followers:
                lock = self.state.locks.get(follower)
                state = "locked" if lock is not None and lock.locked else "unlocked"
                lines.append(f"{follower} ({state})")
            box = QtWidgets.QMessageBox(self)
            box.setObjectName("removalDialog")
            box.setIcon(QtWidgets.QMessageBox.Icon.Question)
            box.setWindowTitle("Remove Target?")
            # macOS ignores a QMessageBox's window title (windowTitle()
            # reads back empty there); tests pin the dialog through its
            # object name and text instead.
            box.setText(
                f"Removing {fullName} also removes the Locks of:\n"
                + "\n".join(lines)
            )
            box.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Ok
                | QtWidgets.QMessageBox.StandardButton.Cancel
            )
            box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
            self.removalDialog = box
            if box.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
                return
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
        self.apply_locks()

    @QtCore.Slot(str, object)
    def _on_type_changed(
        self, name: str, type_blueprint: Optional[PMTypeBluePrint]
    ) -> None:
        """Record the change a ``pm-type-update`` Broadcast reports about
        the Type ``name`` in the state, then recompute the tints and gutter
        bands it may change, and rebuild the Locks panel (its Type Lock
        rows depend on the Types)."""
        self.state.apply_type(name, type_blueprint)
        self.apply_tints()
        self.refresh_locks_panel()

    @QtCore.Slot(str, object)
    def _on_lock_changed(
        self, path: str, lock: Optional[PMLockBluePrint]
    ) -> None:
        """Record the change a ``pm-lock-update`` Broadcast reports about
        the Follower at ``path``, then recompute the Lock column and the
        row widgets, and repaint the values the change alters: the
        Follower's own and every row whose chain of locked Locks reaches
        it, since locking and unlocking change what ``get`` answers — in
        the tree and, while it is shown, in the Locks panel."""
        self.state.apply_lock(path, lock)
        self.apply_locks()
        refreshed = [
            path,
            *followers_reaching(path, self.state.locks, self.instrument.name),
        ]
        for follower in refreshed:
            self._refresh_row_widget(follower)
        if not self.locksPanel.isHidden():
            self.locksPanel.refresh_values(refreshed)

    @QtCore.Slot(object, object)
    def _on_item_new_value(self, path: object, value: object) -> None:
        """Repaint every Follower whose locked Lock chain reaches the
        parameter a ``parameter-update`` Broadcast names (D3: a locked
        Follower answers ``get`` with the Target's value, and the
        Parameter Manager emits nothing for values). The Broadcast's own
        row is refreshed by the base wiring to
        ``view.onItemNewValue``; this slot handles the rows behind it —
        and, while the Locks panel is shown, the same paths there."""
        followers = followers_reaching(
            str(path), self.state.locks, self.instrument.name
        )
        for follower in followers:
            self._refresh_row_widget(follower)
        if not self.locksPanel.isHidden():
            self.locksPanel.refresh_values([str(path), *followers])

    def _refresh_row_widget(self, path: str) -> None:
        """Re-read the parameter behind the row at ``path`` through the
        Proxy, which pulls the Target's value for a locked Follower, and
        show it on the row's widget."""
        widget = self.view.delegate.parameters.get(path)
        if widget is None:
            return
        try:
            widget.setWidgetFromParameter()
        except RuntimeError:
            logger.debug(
                f"Could not refresh the value of {path}. "
                "Object is not being shown right now."
            )

    @QtCore.Slot()
    def apply_locks(self) -> None:
        """Recompute every parameter row's Lock state from the client-side
        state (plan task 5.3): the Lock column text, the lock button's
        visibility, tooltip and purple fill, and whether the value renders
        read-only.

        Runs after the state was refreshed from the Parameter Manager (on a
        model reload), on every ``pm-lock-update`` Broadcast, and after a
        parameter was created or removed by a Broadcast. Recomputing all
        rows on every change is fine — the tree is small — and keeps one
        clear path. The Locks panel is rebuilt with the same state at the
        end, but only while it is shown."""
        self._apply_locks_to_rows(self.model.invisibleRootItem())
        self.refresh_locks_panel()

    def _apply_locks_to_rows(self, parent: QtGui.QStandardItem) -> None:
        """Walk the source model (never the proxy) and set each row's Lock
        column text, lock button state and read-only flag."""
        for row in range(parent.rowCount()):
            item = parent.child(row, 0)
            if item is None:
                continue
            lockItem = parent.child(row, LOCK_COLUMN)
            if lockItem is None:
                lockItem = QtGui.QStandardItem()
                parent.setChild(row, LOCK_COLUMN, lockItem)
            if item.element is None:
                # a submodule row carries no Lock state of its own
                lockItem.setText("")
            else:
                lockItem.setText(
                    lock_column_text(
                        item.name, self.state.locks, self.instrument.name
                    )
                )
                widget = self.view.delegate.parameters.get(item.name)
                if widget is not None:
                    self._update_row_lock_widget(item.name, widget)
            if item.hasChildren():
                self._apply_locks_to_rows(item)

    def _update_row_lock_widget(
        self, path: str, widget: "ParameterWidget"
    ) -> None:
        """Set one row's lock button and read-only state from the Lock the
        state holds for ``path``. A row without a Lock shows no button and
        renders its value editable."""
        button = getattr(widget, "lockButton", None)
        lock = self.state.locks.get(path)
        if lock is None:
            if button is not None:
                button.setVisible(False)
            widget.set_read_only(False)
            return
        target = relative_path(lock.target, self.instrument.name)
        tooltip = lock_button_tooltip(lock.locked, target)
        if button is not None:
            button.setToolTip(tooltip)
            button.setProperty("locked", lock.locked)
            # re-polish so the locked property restyles the button
            button.style().unpolish(button)
            button.style().polish(button)
            button.setVisible(True)
        widget.set_read_only(lock.locked)

    @QtCore.Slot(str)
    def _toggle_lock(self, path: str) -> None:
        """Toggle the Lock of the parameter at ``path`` (the row's lock
        button). A refused toggle — relocking would close a cycle (D7) —
        shows the Server's error text on the row's alert widget."""
        widget = self.view.delegate.parameters.get(path)
        try:
            self.instrument.toggle_lock(path)
        except Exception as e:
            if widget is not None:
                widget.alertWidget.setAlert(str(e))

    @QtCore.Slot(str)
    def _unlock(self, path: str) -> None:
        """Unlock the Lock of the parameter at ``path`` (the context
        menu's "Unlock"). A refused unlock shows the Server's error text
        on the row's alert widget."""
        widget = self.view.delegate.parameters.get(path)
        try:
            self.instrument.unlock(path)
        except Exception as e:
            if widget is not None:
                widget.alertWidget.setAlert(str(e))

    def _lock_current_item(self) -> None:
        """The lock_to shortcut (plan task 5.6): arm the target picker for
        the tree's current parameter row. A submodule row or no selection
        does nothing."""
        item = self._getCurrentItem()
        if item is not None and item.element is not None:
            self.arm_lock(item.name)

    def _unlock_current_item(self) -> None:
        """The unlock_item shortcut (plan task 5.6): unlock the Lock of
        the tree's current parameter row while it is locked; a row
        without a locked Lock does nothing. A refused unlock shows the
        Server's error text on the row's alert widget, like the context
        menu's Unlock."""
        item = self._getCurrentItem()
        if item is None or item.element is None:
            return
        lock = self.state.locks.get(item.name)
        if lock is None or not lock.locked:
            return
        self._unlock(item.name)

    def _toggle_tabs(self) -> None:
        """The show_types shortcut (plan task 5.6): switch between the
        Parameters and Types tabs."""
        self.tabs.setCurrentIndex(1 if self.tabs.currentIndex() == 0 else 0)

    @QtCore.Slot()
    def _update_lock_actions(self) -> None:
        """Enable the context menu's lock actions for the row the menu was
        opened on: "Lock to…" for every parameter row, "Unlock" only for a
        parameter whose Lock in the state is locked."""
        item = self.view.lastSelectedItem
        is_parameter = item is not None and item.element is not None
        self.view.lockToAction.setEnabled(is_parameter)
        self.view.unlockAction.setEnabled(
            is_parameter
            and item.name in self.state.locks  # type: ignore[union-attr]
            and self.state.locks[item.name].locked  # type: ignore[union-attr]
        )

    def arm_lock(self, follower: str) -> None:
        """Arm the target picker for the Follower at ``follower``: the
        candidates are every other parameter row of the source model,
        ranked like the mock's completer (same relative path inside its
        Instance first), and the strip shows under the toolbar. Arming
        while already armed re-arms for the new Follower."""
        parameters = self._model_parameters()
        claims = compute_claims(self.state.types, parameters)
        self.armed_follower = follower
        self.armed_type_lock = None
        self.armStrip.arm(follower, rank_lock_targets(follower, parameters, claims))

    def arm_type_lock(self, type_name: str, path: str) -> None:
        """Arm the target picker for the Type Lock of the entry ``path``
        of the Type ``type_name`` (plan task 5.5): the strip shows on the
        Parameters tab with the entry named in its label, and the
        candidates are every parameter row of the source model ranked
        with the entry path as the relative path (the same leaf on any
        Instance first). Arming while already armed re-arms for the new
        entry."""
        self.armed_type_lock = (type_name, path)
        self.armed_follower = None
        self.tabs.setCurrentIndex(0)
        parameters = self._model_parameters()
        claims = compute_claims(self.state.types, parameters)
        self.armStrip.arm(
            f"type {type_name} \u00b7 {path}",
            rank_lock_targets("", parameters, claims, arm_rel=path),
        )

    def pick_lock_target(self, target: str) -> None:
        """Pick ``target`` as the Target of the armed pick — a Follower's
        Lock (plan task 5.3) or, while a Type Lock re-target is armed, the
        Type Lock declaration with ``target`` as its Target (plan task
        5.5). A refused Lock — a cycle (D7), a self-lock — shows the
        Server's error text on the strip and stays armed so another
        target can be picked; a successful Lock disarms the strip, and a
        Type Lock declaration names the Instance parameters it skipped
        (D17) on the entries pane's note."""
        if self.armed_type_lock is not None:
            type_name, path = self.armed_type_lock
            try:
                skipped = self.instrument.lock_type_parameter(
                    type_name, path, target=target
                )
            except Exception as exc:
                self.armStrip.show_error(str(exc))
            else:
                if skipped:
                    self.typesPane.show_entries_note(
                        f"skipped: {', '.join(skipped)}"
                    )
                else:
                    # a clean declaration leaves no stale error or
                    # skipped note behind (plan task 5.6)
                    self.typesPane.reset_entries_note()
                self.cancel_arm()
            return
        if self.armed_follower is None:
            return
        try:
            self.instrument.lock(self.armed_follower, target)
        except Exception as exc:
            self.armStrip.show_error(str(exc))
        else:
            self.cancel_arm()

    def cancel_arm(self) -> None:
        """Disarm the target picker without picking anything (either kind
        of pick: a Follower's Lock or a Type Lock's re-target)."""
        self.armed_follower = None
        self.armed_type_lock = None
        self.armStrip.disarm()

    @QtCore.Slot(QtCore.QModelIndex)
    def _on_view_clicked(self, index: QtCore.QModelIndex) -> None:
        """A row click while the pick is armed chooses that row's parameter
        as the Target (the mock's rowClick); a submodule click does
        nothing."""
        if self.armed_follower is None and self.armed_type_lock is None:
            return
        source_index = self.proxyModel.mapToSource(index)
        source_index = source_index.sibling(source_index.row(), 0)
        item = self.model.itemFromIndex(source_index)
        if item is not None and item.element is not None:
            self.pick_lock_target(item.name)

    # ------------------------------------------------------------------
    # the Locks panel (plan task 5.4)
    # ------------------------------------------------------------------

    @QtCore.Slot(bool)
    def _on_locks_action_toggled(self, checked: bool) -> None:
        """Show or hide the Locks panel with the toolbar action, and
        rebuild its rows when it becomes visible (a hidden panel costs
        nothing)."""
        self.locksPanel.setVisible(checked)
        if checked:
            self.refresh_locks_panel()

    @QtCore.Slot()
    def refresh_locks_panel(self) -> None:
        """Rebuild the Locks panel's rows from the client-side state (plan
        task 5.4): the rows from ``PMState.locks`` and ``PMState.types``,
        each row's parameter resolved through the instrument.

        Runs at the end of :meth:`apply_locks` and of
        :meth:`_on_type_changed` — the Type Lock rows depend on the Types —
        and when the toolbar action shows the panel, but only while the
        panel is shown, so a hidden panel costs nothing."""
        if self.locksPanel.isHidden():
            return
        rows = build_lock_rows(
            self.state.locks, self.state.types, self.instrument.name
        )
        elements: Dict[str, Any] = {}
        for path in _lock_row_paths(rows):
            try:
                elements[path] = nestedAttributeFromString(self.instrument, path)
            except (AttributeError, RuntimeError) as exc:
                logger.debug(
                    f"could not resolve the parameter of the Locks panel "
                    f"row {path}: {exc}"
                )
        self.locksPanel.rebuild(
            rows, elements, self.state.types, self.state.locks
        )

    @QtCore.Slot(str)
    def _on_panel_toggle_lock(self, path: str) -> None:
        """The Locks panel's lock/relock toggle: toggle the Lock of the
        parameter at ``path``. A refused toggle shows the Server's error
        text on the panel's note label."""
        try:
            self.instrument.toggle_lock(path)
        except Exception as exc:
            self.locksPanel.show_error(str(exc))
        else:
            self.locksPanel.reset_note()

    @QtCore.Slot(str)
    def _on_panel_remove_lock(self, path: str) -> None:
        """The Locks panel's remove button: remove the Lock of the
        parameter at ``path``. A refused removal shows the Server's error
        text on the panel's note label."""
        try:
            self.instrument.remove_lock(path)
        except Exception as exc:
            self.locksPanel.show_error(str(exc))
        else:
            self.locksPanel.reset_note()

    @QtCore.Slot(str, str, str)
    def _on_panel_lock_all(self, type_name: str, entry: str, target: str) -> None:
        """The Type Lock row's "lock all" button: declare the Type Lock
        again with the entry's stored Target — called with ``target=None``
        the Server would re-point the rule to the Globals default (D17).
        Instance parameters the declaration skips, because they carry a
        Lock on another Target (D17), are named on the note label."""
        try:
            skipped = self.instrument.lock_type_parameter(
                type_name, entry, target=target
            )
        except Exception as exc:
            self.locksPanel.show_error(str(exc))
        else:
            if skipped:
                self.locksPanel.show_note(f"skipped: {', '.join(skipped)}")
            else:
                self.locksPanel.reset_note()

    @QtCore.Slot(str, str)
    def _on_panel_remove_rule(self, type_name: str, entry: str) -> None:
        """The Type Lock row's "remove rule" button: remove only the rule
        (D17); the Locks it created stay until they are removed one by
        one. A refused removal shows the Server's error text on the
        panel's note label."""
        try:
            self.instrument.unlock_type_parameter(type_name, entry)
        except Exception as exc:
            self.locksPanel.show_error(str(exc))
        else:
            self.locksPanel.reset_note()

    @QtCore.Slot()
    def _lock_selection_from_panel(self) -> None:
        """The panel's "Lock selection to…": arm the target picker for the
        tree's current parameter row. With no parameter row current, the
        note label says so and nothing is armed; a successful arm clears a
        stale error from the note (plan task 5.6)."""
        item = self._getCurrentItem()
        if item is None or item.element is None:
            self.locksPanel.show_error("Select a parameter in the tree first.")
            return
        self.locksPanel.reset_note()
        self.arm_lock(item.name)

    @QtCore.Slot(QtCore.QModelIndex, QtCore.QModelIndex)
    def _on_tree_current_changed(
        self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex
    ) -> None:
        """Keep the panel's selected label on the tree's current row: a
        parameter row shows its path, a submodule row or no selection shows
        "no parameter selected"."""
        item = self._getCurrentItem()
        if item is not None and item.element is not None:
            self.locksPanel.selectedLabel.setText(item.name)
        else:
            self.locksPanel.selectedLabel.setText("no parameter selected")

    @QtCore.Slot()
    def apply_tints(self) -> None:
        """Recompute every row's Type claims and repaint the tints and
        gutter bands (plan task 5.2).

        Runs after the state was refreshed from the Parameter Manager (on a
        model reload), on every ``pm-type-update`` Broadcast, and after a
        parameter was created or removed by a Broadcast, since matching
        depends on which parameters exist. The Types pane rebuilds from
        the same state at the end (plan task 5.5).
        """
        self.typePalette.sync(self.state.types)
        claims = compute_claims(self.state.types, self._model_parameters())
        self._apply_tints_to_rows(self.model.invisibleRootItem(), claims)
        self.refresh_types_pane()

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
            rowItems = [parent.child(row, col) for col in range(LOCK_COLUMN + 1)]
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

    # ------------------------------------------------------------------
    # the Types pane (plan task 5.5)
    # ------------------------------------------------------------------

    @QtCore.Slot()
    def refresh_types_pane(self) -> None:
        """Rebuild the Types pane's three panes from the client-side state
        (plan task 5.5): the Types, the model's parameter rows and the
        tint palette.

        Runs at the end of :meth:`apply_tints` — so a refresh, a profile
        load, a ``pm-type-update`` Broadcast and a structural Broadcast
        all refresh it — and after every pane action's Server call
        returns (the Broadcast arrives on top of that; a double rebuild
        is fine). The pane keeps the selected Type across rebuilds and
        drops the selection when the Type is gone."""
        self.typesPane.rebuild(
            self.state.types, self._model_parameters(), self.typePalette
        )

    @QtCore.Slot(str)
    def _on_pane_type_selected(self, name: str) -> None:
        """The Types pane's selected Type changed: re-render the entries
        and Instances panes for it."""
        self.typesPane.refresh_selected_panes(
            self.state.types, self._model_parameters(), self.typePalette
        )

    @QtCore.Slot(str)
    def _on_pane_add_type(self, name: str) -> None:
        """The New type strip: create the Type. A refused creation shows
        the Server's error text on the strip's note; on success the new
        Type is selected once the pane rebuilds (the ``pm-type-update``
        Broadcast brings it into the state)."""
        try:
            self.instrument.add_type(name)
        except Exception as exc:
            self.typesPane.show_type_error(str(exc))
        else:
            self.typesPane.reset_type_note()
            self.typesPane.newTypeEdit.clear()
            self.typesPane.select_type(name)
            self.refresh_types_pane()

    @QtCore.Slot(str, str, str, str)
    def _on_pane_add_entry(
        self, type_name: str, path: str, default_text: str, unit: str
    ) -> None:
        """The "Add to type" strip: add the entry with its parsed default
        (``None`` when the text is empty) and unit (D11, D13). A refused
        edit shows the Server's error text on the entries pane's note."""
        try:
            self.instrument.add_type_parameter(
                type_name, path, default=parse_default_text(default_text), unit=unit
            )
        except Exception as exc:
            self.typesPane.show_entries_error(str(exc))
        else:
            self.typesPane.reset_entries_note()
            self.typesPane.entryNameEdit.clear()
            self.typesPane.entryDefaultEdit.clear()
            self.typesPane.entryUnitEdit.clear()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_remove_entry(self, type_name: str, path: str) -> None:
        """An own entry's Remove button: remove the entry from the Type
        only (D13) — the Instances keep the parameter. A refused removal
        shows the Server's error text on the entries pane's note."""
        try:
            self.instrument.remove_type_parameter(type_name, path)
        except Exception as exc:
            self.typesPane.show_entries_error(str(exc))
        else:
            self.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str, str)
    def _on_pane_set_default(self, type_name: str, path: str, text: str) -> None:
        """An own entry's committed default editor (Return or the set
        button): set the entry's default to the parsed text (D13). A
        refused set shows the Server's error text on the entries pane's
        note."""
        try:
            self.instrument.set_type_parameter_default(
                type_name, path, parse_default_text(text)
            )
        except Exception as exc:
            self.typesPane.show_entries_error(str(exc))
        else:
            self.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_toggle_type_lock(self, type_name: str, path: str) -> None:
        """An entry's Type Lock toggle: declare the Type Lock on the
        default Globals Target while the entry has no Target, remove only
        the rule while it has one (D17). A refused toggle shows the
        Server's error text on the entries pane's note; the Instance
        parameters a declaration skips (D17) are named on it."""
        blueprint = self.state.types.get(type_name)
        target = None
        if blueprint is not None:
            target = blueprint.parameters.get(path, {}).get("target")
        try:
            if target is None:
                skipped = self.instrument.lock_type_parameter(type_name, path)
            else:
                self.instrument.unlock_type_parameter(type_name, path)
                skipped = []
        except Exception as exc:
            self.typesPane.show_entries_error(str(exc))
        else:
            if skipped:
                self.typesPane.show_entries_note(f"skipped: {', '.join(skipped)}")
            else:
                self.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str, str)
    def _on_pane_add_nested(
        self, type_name: str, submodule: str, nested: str
    ) -> None:
        """The "Nested type" strip: require the Nested Type ``nested`` at
        the submodule (D11, D13). A refused edit shows the Server's error
        text on the entries pane's note."""
        try:
            self.instrument.add_nested_type(type_name, submodule, nested)
        except Exception as exc:
            self.typesPane.show_entries_error(str(exc))
        else:
            self.typesPane.reset_entries_note()
            self.typesPane.nestedAtEdit.clear()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_remove_nested(self, type_name: str, submodule: str) -> None:
        """An own Nested Type's Remove button: remove the requirement
        (D13) — the Instances keep the parameters. A refused removal
        shows the Server's error text on the entries pane's note."""
        try:
            self.instrument.remove_nested_type(type_name, submodule)
        except Exception as exc:
            self.typesPane.show_entries_error(str(exc))
        else:
            self.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_add_instance(self, type_name: str, name: str) -> None:
        """The New instance strip: create the Instance ``name`` of the
        Type (D14). A refused creation shows the Server's error text on
        the instances pane's note."""
        try:
            self.instrument.add_instance(type_name, name)
        except Exception as exc:
            self.typesPane.show_instances_error(str(exc))
        else:
            self.typesPane.reset_instances_note()
            self.typesPane.newInstanceEdit.clear()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_show_instance(self, type_name: str, instance: str) -> None:
        """An instance row's Show button: switch to the Parameters tab,
        clear the filter, expand the tree and select the Instance's first
        parameter row — the first effective entry under it, the submodule
        row as the fallback — scrolled into view."""
        self.tabs.setCurrentIndex(0)
        self.lineEdit.clear()
        self.view.expandAll()
        blueprint = self.state.types.get(type_name)
        candidates = [instance]
        if blueprint is not None and blueprint.effective:
            first = sorted(blueprint.effective, key=lambda entry: entry.split("."))[0]
            candidates.insert(0, f"{instance}.{first}")
        for path in candidates:
            matches = self.model.findItems(
                path,
                cast(
                    "QtCore.Qt.MatchFlags",
                    QtCore.Qt.MatchFlag.MatchExactly
                    | QtCore.Qt.MatchFlag.MatchRecursive,
                ),
                0,
            )
            if not matches:
                continue
            proxy_index = self.proxyModel.mapFromSource(
                self.model.indexFromItem(matches[0])
            )
            if proxy_index.isValid():
                self.view.setCurrentIndex(proxy_index)
                self.view.scrollTo(proxy_index)
            break

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
