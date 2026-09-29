"""The Parameter Manager GUI's panels and delegates: the gutter bands, the
Lock arm strip and Locks panel, and the Types tab."""

import logging
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    cast,
)

from ... import QtCore, QtGui, QtWidgets
from ...blueprints import (
    PMLockBluePrint,
    PMTypeBluePrint,
)
from .. import keepSmallHorizontally
from ..parameters import ParameterWidget
from .logic import (
    GUTTER_ROLE,
    GUTTER_WIDTH,
    LOCK_COLOUR,
    EntryRow,
    LockRow,
    TypePalette,
    also_types,
    instances_of_type,
    lock_button_tooltip,
    lock_root,
    relative_path,
    type_entry_rows,
)

logger = logging.getLogger(__name__)


# ----------------- Tints --------------------------------------------------------------


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


# ----------------- Locks --------------------------------------------------------------


def make_lock_button(
    parent: QtWidgets.QWidget, locked: bool, target: Optional[str] = None
) -> QtWidgets.QPushButton:
    """The lock/relock toggle button shared by the tree's per-row widget
    (plan task 5.3) and the Locks panel (plan task 5.4): the lock icon and
    the purple ``locked`` fill. ``target`` is the Target relative to the
    Parameter Manager for the state tooltip; the tree's delegate passes
    ``None`` and leaves the tooltip to
    :meth:`.LocksController._update_row_lock_widget`."""
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
        """Rebuild every row from ``rows`` (see :func:`.build_lock_rows`).

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


# ----------------- Types tab ----------------------------------------------------------


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
    :class:`.ParameterManagerGui`, which owns the pane, performs it and
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
