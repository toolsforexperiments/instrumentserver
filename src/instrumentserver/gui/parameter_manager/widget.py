"""The Parameter Manager widget (:class:`ParameterManagerGui`) and the
model, tree view and create form it is built from."""

import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

from ... import QtCore, QtGui, QtWidgets
from ...blueprints import (
    PARAMETER_DELETION,
    PM_LOCK_UPDATE,
    PM_TYPE_UPDATE,
    ParameterBroadcastBluePrint,
    PMLockBluePrint,
    PMTypeBluePrint,
)
from ...client import ProxyInstrument
from ...helpers import nestedAttributeFromString
from ...params import (
    ParameterManager,
    ParameterTypes,
    parameterTypes,
    paramTypeFromName,
)
from .. import keepSmallHorizontally
from ..instruments import (
    InstrumentParameters,
    ModelParameters,
    ParameterDelegate,
    ParametersTreeView,
)
from ..parameters import ParameterWidget
from .logic import (
    GUTTER_COLUMN,
    GUTTER_ROLE,
    GUTTER_WIDTH,
    LOCK_COLUMN,
    LOCK_COLUMN_WIDTH,
    Claim,
    PMState,
    TypePalette,
    build_lock_rows,
    compute_claims,
    followers_reaching,
    lock_button_tooltip,
    lock_column_text,
    lock_row_paths,
    parse_default_text,
    rank_lock_targets,
    relative_path,
)
from .panels import (
    GutterDelegate,
    LockArmStrip,
    LocksPanel,
    TypesPane,
    make_lock_button,
)

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
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
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


class ModelParameterManager(ModelParameters):
    #: Signal() --
    #: Emitted after a Broadcast changed the tree's structure: a parameter
    #: was created or removed, or a ``parameter-update``/``parameter-call``
    #: added a row the model did not know. The Parameter Manager GUI
    #: recomputes the Type claims that the tints and gutter bands show.
    structureChanged = QtCore.Signal()

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

    def headerLabels(self) -> List[str]:
        # the gutter column (plan task 5.2) and the Lock column (plan
        # task 5.3) follow the name, unit and delegate columns
        return super().headerLabels() + ["", "locked to"]

    def rowItems(self, item: QtGui.QStandardItem) -> List[QtGui.QStandardItem]:
        return super().rowItems(item) + [
            QtGui.QStandardItem(),
            QtGui.QStandardItem(),
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # set by newItem while a Broadcast is handled, so updateParameter
        # knows the Broadcast added a row; rows added while the model loads
        # or reloads never reach updateParameter's check
        self._rows_added = False
        self.newItem.connect(self._on_new_item)

    @QtCore.Slot(object)
    def _on_new_item(self, item: QtGui.QStandardItem) -> None:
        self._rows_added = True

    def parameter_units(self) -> Dict[str, str]:
        """Every parameter row as ``{path: unit}``."""
        parameters: Dict[str, str] = {}
        root = self.invisibleRootItem()
        assert root is not None
        self._collect_parameters(root, parameters)
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

    def updateParameter(self, bp: ParameterBroadcastBluePrint) -> None:
        fullName = ".".join(bp.name.split(".")[1:])
        if bp.action == PM_LOCK_UPDATE:
            # Locks and Types claim no model item of their own: the
            # Parameter Manager GUI records the change in its PMState (D10)
            self.lockChanged.emit(fullName, bp.value)
            return
        if bp.action == PM_TYPE_UPDATE:
            self.typeChanged.emit(fullName, bp.value)
            return
        self._rows_added = False
        super().updateParameter(bp)
        # a creation, or a parameter-update or parameter-call for a row the
        # model did not know, adds rows through the base branches; matching
        # depends on which parameters exist, so the tints and gutter bands
        # must be recomputed then (plan task 5.6), or the new row would
        # stay untinted until the next recompute
        if self._rows_added or bp.action == PARAMETER_DELETION:
            self.structureChanged.emit()


class LockableParameterWidget(ParameterWidget):
    """The value widget of a Parameter Manager row: a
    :class:`~instrumentserver.gui.parameters.ParameterWidget` with the
    row's lock button and delete button after the value. It keeps the lock
    button so the Parameter Manager GUI can restyle it with the Lock
    state."""

    def __init__(
        self,
        parameter: Any,
        lockButton: QtWidgets.QPushButton,
        removeButton: QtWidgets.QPushButton,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parameter=parameter,
            parent=parent,
            additionalWidgets=[lockButton, removeButton],
        )
        self.lockButton = lockButton


class ParameterDeleteDelegate(ParameterDelegate):
    #: Signal(str)
    #: Emits the name of the parameter to be deleted when the user presses the delete button.
    removeParameter = QtCore.Signal(str)

    #: Signal(str)
    #: Emits the name of the parameter whose lock button the user pressed;
    #: the Parameter Manager GUI toggles that parameter's Lock.
    toggleLock = QtCore.Signal(str)

    def makeParameterWidget(
        self, item: QtGui.QStandardItem, parent: QtWidgets.QWidget
    ) -> ParameterWidget:
        rw = self.makeRemoveWidget(item.name, parent)  # type: ignore[attr-defined]
        lw = self.make_lock_widget(item.name, parent)  # type: ignore[attr-defined]

        return LockableParameterWidget(
            item.element,  # type: ignore[attr-defined]
            lockButton=lw,
            removeButton=rw,
            parent=parent,
        )

    def make_lock_widget(
        self, fullName: str, widget: QtWidgets.QWidget
    ) -> QtWidgets.QPushButton:
        """The per-row lock button. It stays hidden until the row carries a
        Lock (a Lock-less row shows no button, as the mock), fills purple
        while the Lock is locked, and only
        :meth:`LocksController.apply_locks` changes its state."""
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
class ParameterManagerTreeView(ParametersTreeView):
    #: Signal(str)
    #: Emitted when the user picks "Lock to…" in the context menu; the
    #: Parameter Manager GUI arms the target picker for that parameter.
    lockToRequested = QtCore.Signal(str)

    #: Signal(str)
    #: Emitted when the user picks "Unlock" in the context menu.
    unlockRequested = QtCore.Signal(str)

    delegateClass = ParameterDeleteDelegate
    delegate: ParameterDeleteDelegate

    def __init__(
        self,
        model: QtCore.QAbstractItemModel,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, *args, **kwargs)

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

    def setupColumns(self) -> None:
        # the view is built over a ModelParameterManager, whose rows carry
        # the gutter and Lock columns
        self.gutterDelegate = GutterDelegate(self)
        self.setItemDelegateForColumn(GUTTER_COLUMN, self.gutterDelegate)
        header = self.header()
        assert header is not None
        # the gutter moves to visual position 0 with a fixed width; the
        # tree branches stay on the name column
        header.moveSection(GUTTER_COLUMN, 0)
        if header.minimumSectionSize() > GUTTER_WIDTH:
            header.setMinimumSectionSize(GUTTER_WIDTH)
        header.setSectionResizeMode(
            GUTTER_COLUMN, QtWidgets.QHeaderView.ResizeMode.Fixed
        )
        header.resizeSection(GUTTER_COLUMN, GUTTER_WIDTH)
        # the Lock column moves between the unit and the delegate column,
        # with a resizable default width
        header.moveSection(header.visualIndex(LOCK_COLUMN), header.visualIndex(2))
        header.setSectionResizeMode(
            LOCK_COLUMN, QtWidgets.QHeaderView.ResizeMode.Interactive
        )
        header.resizeSection(LOCK_COLUMN, LOCK_COLUMN_WIDTH)
        self.setTreePosition(0)

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


class LocksController(QtCore.QObject):
    """The Lock behaviour of a :class:`ParameterManagerGui` (plan tasks
    5.3, 5.4 and 5.6): the tree's Lock column, lock buttons and read-only
    values, the lock and unlock actions and shortcuts, the arm strip's
    target pick, and the Locks panel. It works on the GUI's widgets and
    state and wires them in :meth:`connectSignals`.

    ``armed_follower`` is the Follower a pick is armed for, and
    ``armed_type_lock`` the (Type, entry) pair a Type Lock re-target from
    the Types tab (plan task 5.5) is armed for; both are ``None`` while
    nothing is armed.
    """

    def __init__(self, gui: "ParameterManagerGui") -> None:
        super().__init__(gui)
        self.gui = gui
        self.armed_follower: Optional[str] = None
        self.armed_type_lock: Optional[Tuple[str, str]] = None

    def connectSignals(self) -> None:
        gui = self.gui
        gui.view.delegate.toggleLock.connect(self._toggle_lock)
        gui.model.lockChanged.connect(self._on_lock_changed)
        gui.model.structureChanged.connect(self.apply_locks)
        gui.model.itemNewValue.connect(self._on_item_new_value)
        # the filter (and the trash toggle) hides rows; when they come
        # back, restoreCollapsedDict has re-opened their persistent
        # editors, so createEditor has built fresh ParameterWidgets whose
        # lock button is hidden and whose input is editable — re-apply the
        # Lock state to them
        gui.proxyModel.filterFinished.connect(self.apply_locks)
        gui.view.lockToRequested.connect(self.arm_lock)
        gui.view.unlockRequested.connect(self._unlock)
        gui.view.contextMenu.aboutToShow.connect(self._update_lock_actions)
        gui.view.clicked.connect(self._on_view_clicked)
        gui.viewEscShortcut.activated.connect(self.cancel_arm)
        gui.armStrip.targetPicked.connect(self.pick_lock_target)
        gui.armStrip.cancelled.connect(self.cancel_arm)
        # the Locks panel (plan task 5.4): the tree's current row drives
        # the panel's selected label
        gui.locksAction.toggled.connect(self._on_locks_action_toggled)
        gui.locksPanel.toggleLockRequested.connect(self._on_panel_toggle_lock)
        gui.locksPanel.removeLockRequested.connect(self._on_panel_remove_lock)
        gui.locksPanel.lockAllRequested.connect(self._on_panel_lock_all)
        gui.locksPanel.removeRuleRequested.connect(self._on_panel_remove_rule)
        gui.locksPanel.lockSelectionRequested.connect(
            self._lock_selection_from_panel
        )
        gui.view.selectionModel().currentChanged.connect(
            self._on_tree_current_changed
        )
        # the Types tab's Type Lock re-target arms the same strip
        gui.typesPane.retargetTypeLockRequested.connect(self.arm_type_lock)
        gui.shortcutManager.register("toggle_locks", gui.locksAction.toggle, gui)
        # the Lock shortcuts (plan task 5.6); the tree's two lock actions
        # carry their key in their tooltips
        gui.shortcutManager.register("lock_to", self._lock_current_item, gui)
        gui.shortcutManager.register("unlock_item", self._unlock_current_item, gui)
        gui.shortcutManager.register_tooltip("lock_to", gui.view.lockToAction)
        gui.shortcutManager.register_tooltip("unlock_item", gui.view.unlockAction)

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
        self.gui.state.apply_lock(path, lock)
        self.apply_locks()
        refreshed = [
            path,
            *followers_reaching(path, self.gui.state.locks, self.gui.instrument.name),
        ]
        for follower in refreshed:
            self._refresh_row_widget(follower)
        if not self.gui.locksPanel.isHidden():
            self.gui.locksPanel.refresh_values(refreshed)

    @QtCore.Slot(object, object)
    def _on_item_new_value(self, path: object, value: object) -> None:
        """Repaint every Follower whose locked Lock chain reaches the
        parameter a ``parameter-update`` or ``parameter-call`` Broadcast
        names (D3: a locked Follower answers ``get`` with the Target's
        value, and the Parameter Manager emits nothing for values). The
        Broadcast's own row is refreshed by the base wiring to
        ``view.onItemNewValue``; this slot handles the rows behind it —
        and, while the Locks panel is shown, the same paths there.

        Every row is painted with the Broadcast's ``value``, never a fresh
        ``get``: the Server broadcasts a ``parameter-call`` for every
        ``get``, so a ``get`` here would bring this slot back for the same
        path, forever."""
        followers = followers_reaching(
            str(path), self.gui.state.locks, self.gui.instrument.name
        )
        for follower in followers:
            if follower in self.gui.view.delegate.parameters:
                self.gui.view.onItemNewValue(follower, value)
        if not self.gui.locksPanel.isHidden():
            self.gui.locksPanel.show_value([str(path), *followers], value)

    def _refresh_row_widget(self, path: str) -> None:
        """Re-read the parameter behind the row at ``path`` through the
        Proxy, which pulls the Target's value for a locked Follower, and
        show it on the row's widget."""
        widget = self.gui.view.delegate.parameters.get(path)
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
        self._apply_locks_to_rows(self.gui.model.invisibleRootItem())
        self.refresh_locks_panel()

    def _apply_locks_to_rows(self, parent: QtGui.QStandardItem) -> None:
        """Walk the source model (never the proxy) and set each row's Lock
        column text, lock button state and read-only flag."""
        for row in range(parent.rowCount()):
            item = parent.child(row, 0)
            if item is None:
                continue
            lockItem = parent.child(row, LOCK_COLUMN)
            # ModelParameterManager.rowItems gives every row this item
            assert lockItem is not None
            if item.element is None:
                # a submodule row carries no Lock state of its own
                lockItem.setText("")
            else:
                lockItem.setText(
                    lock_column_text(
                        item.name, self.gui.state.locks, self.gui.instrument.name
                    )
                )
                widget = self.gui.view.delegate.parameters.get(item.name)
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
        button = (
            widget.lockButton
            if isinstance(widget, LockableParameterWidget)
            else None
        )
        lock = self.gui.state.locks.get(path)
        if lock is None:
            if button is not None:
                button.setVisible(False)
            widget.set_read_only(False)
            return
        target = relative_path(lock.target, self.gui.instrument.name)
        tooltip = lock_button_tooltip(lock.locked, target)
        if button is not None:
            button.setToolTip(tooltip)
            button.setProperty("locked", lock.locked)
            # re-polish so the locked property restyles the button
            style = button.style()
            if style is not None:
                style.unpolish(button)
                style.polish(button)
            button.setVisible(True)
        widget.set_read_only(lock.locked)

    @QtCore.Slot(str)
    def _toggle_lock(self, path: str) -> None:
        """Toggle the Lock of the parameter at ``path`` (the row's lock
        button). A refused toggle — relocking would close a cycle (D7) —
        shows the Server's error text on the row's alert widget."""
        widget = self.gui.view.delegate.parameters.get(path)
        try:
            self.gui.instrument.toggle_lock(path)
        except Exception as e:
            if widget is not None:
                widget.alertWidget.setAlert(str(e))

    @QtCore.Slot(str)
    def _unlock(self, path: str) -> None:
        """Unlock the Lock of the parameter at ``path`` (the context
        menu's "Unlock"). A refused unlock shows the Server's error text
        on the row's alert widget."""
        widget = self.gui.view.delegate.parameters.get(path)
        try:
            self.gui.instrument.unlock(path)
        except Exception as e:
            if widget is not None:
                widget.alertWidget.setAlert(str(e))

    def _lock_current_item(self) -> None:
        """The lock_to shortcut (plan task 5.6): arm the target picker for
        the tree's current parameter row. A submodule row or no selection
        does nothing."""
        item = self.gui._getCurrentItem()
        if item is not None and item.element is not None:
            self.arm_lock(item.name)

    def _unlock_current_item(self) -> None:
        """The unlock_item shortcut (plan task 5.6): unlock the Lock of
        the tree's current parameter row while it is locked; a row
        without a locked Lock does nothing. A refused unlock shows the
        Server's error text on the row's alert widget, like the context
        menu's Unlock."""
        item = self.gui._getCurrentItem()
        if item is None or item.element is None:
            return
        lock = self.gui.state.locks.get(item.name)
        if lock is None or not lock.locked:
            return
        self._unlock(item.name)

    @QtCore.Slot()
    def _update_lock_actions(self) -> None:
        """Enable the context menu's lock actions for the row the menu was
        opened on: "Lock to…" for every parameter row, "Unlock" only for a
        parameter whose Lock in the state is locked."""
        item = self.gui.view.lastSelectedItem
        is_parameter = item is not None and item.element is not None
        self.gui.view.lockToAction.setEnabled(is_parameter)
        self.gui.view.unlockAction.setEnabled(
            is_parameter
            and item.name in self.gui.state.locks  # type: ignore[union-attr]
            and self.gui.state.locks[item.name].locked  # type: ignore[union-attr]
        )

    def arm_lock(self, follower: str) -> None:
        """Arm the target picker for the Follower at ``follower``: the
        candidates are every other parameter row of the source model,
        ranked like the mock's completer (same relative path inside its
        Instance first), and the strip shows under the toolbar. Arming
        while already armed re-arms for the new Follower."""
        parameters = self.gui.model.parameter_units()
        claims = compute_claims(self.gui.state.types, parameters)
        self.armed_follower = follower
        self.armed_type_lock = None
        self.gui.armStrip.arm(follower, rank_lock_targets(follower, parameters, claims))

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
        self.gui.tabs.setCurrentIndex(0)
        parameters = self.gui.model.parameter_units()
        claims = compute_claims(self.gui.state.types, parameters)
        self.gui.armStrip.arm(
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
                skipped = self.gui.instrument.lock_type_parameter(
                    type_name, path, target=target
                )
            except Exception as exc:
                self.gui.armStrip.show_error(str(exc))
            else:
                if skipped:
                    self.gui.typesPane.show_entries_note(
                        f"skipped: {', '.join(skipped)}"
                    )
                else:
                    # a clean declaration leaves no stale error or
                    # skipped note behind (plan task 5.6)
                    self.gui.typesPane.reset_entries_note()
                self.cancel_arm()
            return
        if self.armed_follower is None:
            return
        try:
            self.gui.instrument.lock(self.armed_follower, target)
        except Exception as exc:
            self.gui.armStrip.show_error(str(exc))
        else:
            self.cancel_arm()

    def cancel_arm(self) -> None:
        """Disarm the target picker without picking anything (either kind
        of pick: a Follower's Lock or a Type Lock's re-target)."""
        self.armed_follower = None
        self.armed_type_lock = None
        self.gui.armStrip.disarm()

    @QtCore.Slot(QtCore.QModelIndex)
    def _on_view_clicked(self, index: QtCore.QModelIndex) -> None:
        """A row click while the pick is armed chooses that row's parameter
        as the Target (the mock's rowClick); a submodule click does
        nothing."""
        if self.armed_follower is None and self.armed_type_lock is None:
            return
        source_index = self.gui.proxyModel.mapToSource(index)
        source_index = source_index.sibling(source_index.row(), 0)
        item = self.gui.model.itemFromIndex(source_index)
        if item is not None and item.element is not None:
            self.pick_lock_target(item.name)

    @QtCore.Slot(bool)
    def _on_locks_action_toggled(self, checked: bool) -> None:
        """Show or hide the Locks panel with the toolbar action, and
        rebuild its rows when it becomes visible (a hidden panel costs
        nothing)."""
        self.gui.locksPanel.setVisible(checked)
        if checked:
            self.refresh_locks_panel()

    @QtCore.Slot()
    def refresh_locks_panel(self) -> None:
        """Rebuild the Locks panel's rows from the client-side state (plan
        task 5.4): the rows from ``PMState.locks`` and ``PMState.types``,
        each row's parameter resolved through the instrument.

        Runs at the end of :meth:`apply_locks` and of
        :meth:`TypesController._on_type_changed` — the Type Lock rows
        depend on the Types — and when the toolbar action shows the panel,
        but only while the panel is shown, so a hidden panel costs
        nothing."""
        if self.gui.locksPanel.isHidden():
            return
        rows = build_lock_rows(
            self.gui.state.locks, self.gui.state.types, self.gui.instrument.name
        )
        elements: Dict[str, Any] = {}
        for path in lock_row_paths(rows):
            try:
                elements[path] = nestedAttributeFromString(self.gui.instrument, path)
            except (AttributeError, RuntimeError) as exc:
                logger.debug(
                    f"could not resolve the parameter of the Locks panel "
                    f"row {path}: {exc}"
                )
        self.gui.locksPanel.rebuild(
            rows, elements, self.gui.state.types, self.gui.state.locks
        )

    @QtCore.Slot(str)
    def _on_panel_toggle_lock(self, path: str) -> None:
        """The Locks panel's lock/relock toggle: toggle the Lock of the
        parameter at ``path``. A refused toggle shows the Server's error
        text on the panel's note label."""
        try:
            self.gui.instrument.toggle_lock(path)
        except Exception as exc:
            self.gui.locksPanel.show_error(str(exc))
        else:
            self.gui.locksPanel.reset_note()

    @QtCore.Slot(str)
    def _on_panel_remove_lock(self, path: str) -> None:
        """The Locks panel's remove button: remove the Lock of the
        parameter at ``path``. A refused removal shows the Server's error
        text on the panel's note label."""
        try:
            self.gui.instrument.remove_lock(path)
        except Exception as exc:
            self.gui.locksPanel.show_error(str(exc))
        else:
            self.gui.locksPanel.reset_note()

    @QtCore.Slot(str, str, str)
    def _on_panel_lock_all(self, type_name: str, entry: str, target: str) -> None:
        """The Type Lock row's "lock all" button: declare the Type Lock
        again with the entry's stored Target — called with ``target=None``
        the Server would re-point the rule to the Globals default (D17).
        Instance parameters the declaration skips, because they carry a
        Lock on another Target (D17), are named on the note label."""
        try:
            skipped = self.gui.instrument.lock_type_parameter(
                type_name, entry, target=target
            )
        except Exception as exc:
            self.gui.locksPanel.show_error(str(exc))
        else:
            if skipped:
                self.gui.locksPanel.show_note(f"skipped: {', '.join(skipped)}")
            else:
                self.gui.locksPanel.reset_note()

    @QtCore.Slot(str, str)
    def _on_panel_remove_rule(self, type_name: str, entry: str) -> None:
        """The Type Lock row's "remove rule" button: remove only the rule
        (D17); the Locks it created stay until they are removed one by
        one. A refused removal shows the Server's error text on the
        panel's note label."""
        try:
            self.gui.instrument.unlock_type_parameter(type_name, entry)
        except Exception as exc:
            self.gui.locksPanel.show_error(str(exc))
        else:
            self.gui.locksPanel.reset_note()

    @QtCore.Slot()
    def _lock_selection_from_panel(self) -> None:
        """The panel's "Lock selection to…": arm the target picker for the
        tree's current parameter row. With no parameter row current, the
        note label says so and nothing is armed; a successful arm clears a
        stale error from the note (plan task 5.6)."""
        item = self.gui._getCurrentItem()
        if item is None or item.element is None:
            self.gui.locksPanel.show_error("Select a parameter in the tree first.")
            return
        self.gui.locksPanel.reset_note()
        self.arm_lock(item.name)

    @QtCore.Slot(QtCore.QModelIndex, QtCore.QModelIndex)
    def _on_tree_current_changed(
        self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex
    ) -> None:
        """Keep the panel's selected label on the tree's current row: a
        parameter row shows its path, a submodule row or no selection shows
        "no parameter selected"."""
        item = self.gui._getCurrentItem()
        if item is not None and item.element is not None:
            self.gui.locksPanel.selectedLabel.setText(item.name)
        else:
            self.gui.locksPanel.selectedLabel.setText("no parameter selected")


class TypesController(QtCore.QObject):
    """The Type behaviour of a :class:`ParameterManagerGui` (plan tasks
    5.2 and 5.5): the tree's tints and gutter bands, and the Types tab's
    actions. It works on the GUI's widgets and state and wires them in
    :meth:`connectSignals`."""

    def __init__(self, gui: "ParameterManagerGui") -> None:
        super().__init__(gui)
        self.gui = gui

    def connectSignals(self) -> None:
        gui = self.gui
        gui.model.typeChanged.connect(self._on_type_changed)
        gui.model.structureChanged.connect(self.apply_tints)
        # the Types pane (plan task 5.5): a selection change re-renders
        # the two panes it drives
        gui.typesPane.typeSelected.connect(self._on_pane_type_selected)
        gui.typesPane.addTypeRequested.connect(self._on_pane_add_type)
        gui.typesPane.addEntryRequested.connect(self._on_pane_add_entry)
        gui.typesPane.removeEntryRequested.connect(self._on_pane_remove_entry)
        gui.typesPane.setDefaultRequested.connect(self._on_pane_set_default)
        gui.typesPane.toggleTypeLockRequested.connect(
            self._on_pane_toggle_type_lock
        )
        gui.typesPane.addNestedRequested.connect(self._on_pane_add_nested)
        gui.typesPane.removeNestedRequested.connect(self._on_pane_remove_nested)
        gui.typesPane.addInstanceRequested.connect(self._on_pane_add_instance)
        gui.typesPane.showInstanceRequested.connect(self._on_pane_show_instance)

    @QtCore.Slot(str, object)
    def _on_type_changed(
        self, name: str, type_blueprint: Optional[PMTypeBluePrint]
    ) -> None:
        """Record the change a ``pm-type-update`` Broadcast reports about
        the Type ``name`` in the state, then recompute the tints and gutter
        bands it may change, and rebuild the Locks panel (its Type Lock
        rows depend on the Types)."""
        self.gui.state.apply_type(name, type_blueprint)
        self.apply_tints()
        self.gui.locksController.refresh_locks_panel()

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
        self.gui.typePalette.sync(self.gui.state.types)
        claims = compute_claims(self.gui.state.types, self.gui.model.parameter_units())
        self._apply_tints_to_rows(self.gui.model.invisibleRootItem(), claims)
        self.refresh_types_pane()

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
            # ModelParameterManager.rowItems gives every row this item
            assert gutterItem is not None
            claim = claims.get(item.name)
            colours = (
                self.gui.typePalette.colours(claim.type) if claim is not None else None
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
        self.gui.typesPane.rebuild(
            self.gui.state.types, self.gui.model.parameter_units(), self.gui.typePalette
        )

    @QtCore.Slot(str)
    def _on_pane_type_selected(self, name: str) -> None:
        """The Types pane's selected Type changed: re-render the entries
        and Instances panes for it."""
        self.gui.typesPane.refresh_selected_panes(
            self.gui.state.types, self.gui.model.parameter_units(), self.gui.typePalette
        )

    @QtCore.Slot(str)
    def _on_pane_add_type(self, name: str) -> None:
        """The New type strip: create the Type. A refused creation shows
        the Server's error text on the strip's note; on success the new
        Type is selected once the pane rebuilds (the ``pm-type-update``
        Broadcast brings it into the state)."""
        try:
            self.gui.instrument.add_type(name)
        except Exception as exc:
            self.gui.typesPane.show_type_error(str(exc))
        else:
            self.gui.typesPane.reset_type_note()
            self.gui.typesPane.newTypeEdit.clear()
            self.gui.typesPane.select_type(name)
            self.refresh_types_pane()

    @QtCore.Slot(str, str, str, str)
    def _on_pane_add_entry(
        self, type_name: str, path: str, default_text: str, unit: str
    ) -> None:
        """The "Add to type" strip: add the entry with its parsed default
        (``None`` when the text is empty) and unit (D11, D13). A refused
        edit shows the Server's error text on the entries pane's note."""
        try:
            self.gui.instrument.add_type_parameter(
                type_name, path, default=parse_default_text(default_text), unit=unit
            )
        except Exception as exc:
            self.gui.typesPane.show_entries_error(str(exc))
        else:
            self.gui.typesPane.reset_entries_note()
            self.gui.typesPane.entryNameEdit.clear()
            self.gui.typesPane.entryDefaultEdit.clear()
            self.gui.typesPane.entryUnitEdit.clear()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_remove_entry(self, type_name: str, path: str) -> None:
        """An own entry's Remove button: remove the entry from the Type
        only (D13) — the Instances keep the parameter. A refused removal
        shows the Server's error text on the entries pane's note."""
        try:
            self.gui.instrument.remove_type_parameter(type_name, path)
        except Exception as exc:
            self.gui.typesPane.show_entries_error(str(exc))
        else:
            self.gui.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str, str)
    def _on_pane_set_default(self, type_name: str, path: str, text: str) -> None:
        """An own entry's committed default editor (Return or the set
        button): set the entry's default to the parsed text (D13). A
        refused set shows the Server's error text on the entries pane's
        note."""
        try:
            self.gui.instrument.set_type_parameter_default(
                type_name, path, parse_default_text(text)
            )
        except Exception as exc:
            self.gui.typesPane.show_entries_error(str(exc))
        else:
            self.gui.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_toggle_type_lock(self, type_name: str, path: str) -> None:
        """An entry's Type Lock toggle: declare the Type Lock on the
        default Globals Target while the entry has no Target, remove only
        the rule while it has one (D17). A refused toggle shows the
        Server's error text on the entries pane's note; the Instance
        parameters a declaration skips (D17) are named on it."""
        blueprint = self.gui.state.types.get(type_name)
        target = None
        if blueprint is not None:
            target = blueprint.parameters.get(path, {}).get("target")
        try:
            if target is None:
                skipped = self.gui.instrument.lock_type_parameter(type_name, path)
            else:
                self.gui.instrument.unlock_type_parameter(type_name, path)
                skipped = []
        except Exception as exc:
            self.gui.typesPane.show_entries_error(str(exc))
        else:
            if skipped:
                self.gui.typesPane.show_entries_note(f"skipped: {', '.join(skipped)}")
            else:
                self.gui.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str, str)
    def _on_pane_add_nested(
        self, type_name: str, submodule: str, nested: str
    ) -> None:
        """The "Nested type" strip: require the Nested Type ``nested`` at
        the submodule (D11, D13). A refused edit shows the Server's error
        text on the entries pane's note."""
        try:
            self.gui.instrument.add_nested_type(type_name, submodule, nested)
        except Exception as exc:
            self.gui.typesPane.show_entries_error(str(exc))
        else:
            self.gui.typesPane.reset_entries_note()
            self.gui.typesPane.nestedAtEdit.clear()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_remove_nested(self, type_name: str, submodule: str) -> None:
        """An own Nested Type's Remove button: remove the requirement
        (D13) — the Instances keep the parameters. A refused removal
        shows the Server's error text on the entries pane's note."""
        try:
            self.gui.instrument.remove_nested_type(type_name, submodule)
        except Exception as exc:
            self.gui.typesPane.show_entries_error(str(exc))
        else:
            self.gui.typesPane.reset_entries_note()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_add_instance(self, type_name: str, name: str) -> None:
        """The New instance strip: create the Instance ``name`` of the
        Type (D14). A refused creation shows the Server's error text on
        the instances pane's note."""
        try:
            self.gui.instrument.add_instance(type_name, name)
        except Exception as exc:
            self.gui.typesPane.show_instances_error(str(exc))
        else:
            self.gui.typesPane.reset_instances_note()
            self.gui.typesPane.newInstanceEdit.clear()
            self.refresh_types_pane()

    @QtCore.Slot(str, str)
    def _on_pane_show_instance(self, type_name: str, instance: str) -> None:
        """An instance row's Show button: switch to the Parameters tab,
        clear the filter, expand the tree and select the Instance's first
        parameter row — the first effective entry under it, the submodule
        row as the fallback — scrolled into view."""
        self.gui.tabs.setCurrentIndex(0)
        self.gui.lineEdit.clear()
        self.gui.view.expandAll()
        blueprint = self.gui.state.types.get(type_name)
        candidates = [instance]
        if blueprint is not None and blueprint.effective:
            first = sorted(blueprint.effective, key=lambda entry: entry.split("."))[0]
            candidates.insert(0, f"{instance}.{first}")
        for path in candidates:
            matches = self.gui.model.findItems(
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
            proxy_index = self.gui.proxyModel.mapFromSource(
                self.gui.model.indexFromItem(matches[0])
            )
            if proxy_index.isValid():
                self.gui.view.setCurrentIndex(proxy_index)
                self.gui.view.scrollTo(proxy_index)
            break


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
        # Stretch 1 so the tree takes all spare height and the Add strip
        # stays pinned to the bottom.
        layout.insertWidget(view_index, self.locksSplitter, 1)
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
        # a Lock's Target is being picked (plan task 5.3); the Locks
        # controller keeps what the pick is armed for.
        self.armStrip = LockArmStrip(self.parametersTab)
        parametersLayout = self.parametersTab.layout()
        assert isinstance(parametersLayout, QtWidgets.QVBoxLayout)
        toolbar_index = parametersLayout.indexOf(self.toolbar)
        parametersLayout.insertWidget(toolbar_index + 1, self.armStrip)
        self.armStrip.setVisible(False)
        # Escape over the tree cancels the pick too (harmless when the
        # strip is not armed); the Locks controller connects it
        self.viewEscShortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Escape"), self.view
        )
        self.viewEscShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        # The confirmation dialog for removing a Lock Target (plan task
        # 5.6), kept on the GUI so tests can drive it; ``None`` while no
        # removal that needs one is in flight.
        self.removalDialog: Optional[QtWidgets.QMessageBox] = None
        # The Types tab and tints, and the Lock column, arm strip and Locks
        # panel, each run through a controller that wires its own widgets
        self.typesController = TypesController(self)
        self.locksController = LocksController(self)
        self.connectSignals()
        self.loadProfile()

    def connectSignals(self) -> None:
        super().connectSignals()
        self.view.delegate.removeParameter.connect(self.removeParameter)
        self.addParam.newParamRequested.connect(self.addParameter)
        self.parameterCreationError.connect(self.addParam.setError)
        self.parameterCreated.connect(self.addParam.clear)
        self.profileManager.indexChanged.connect(self.loadProfile)
        # the tints run before the Lock pass on a structural change
        self.typesController.connectSignals()
        self.locksController.connectSignals()
        self.shortcutManager.register("delete_item", self._deleteCurrentItem, self)
        self.shortcutManager.register("clear_add", self.addParam.clear, self)
        self.shortcutManager.register("add_item", self.addParam.nameEdit.setFocus, self)
        self.shortcutManager.register("load_items", self.loadFromFile, self)
        self.shortcutManager.register("save_items", self.saveToFile, self)
        self.shortcutManager.register("show_types", self._toggle_tabs, self)

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
        self.typesController.apply_tints()
        self.locksController.apply_locks()

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
            clicked = box.exec()
            # the box is closed on both paths: the attribute matches its
            # docstring again (the tests' QTimer callbacks read it while
            # the box is open, so they keep working)
            self.removalDialog = None
            if clicked != QtWidgets.QMessageBox.StandardButton.Ok:
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
        self.typesController.apply_tints()
        self.locksController.apply_locks()

    def _toggle_tabs(self) -> None:
        """The show_types shortcut (plan task 5.6): switch between the
        Parameters and Types tabs."""
        self.tabs.setCurrentIndex(1 if self.tabs.currentIndex() == 0 else 0)

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
