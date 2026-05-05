import json
import logging
from typing import Callable, Optional

from instrumentserver import QtCore, QtGui, QtWidgets

from .misc import BaseDialog

logger = logging.getLogger(__name__)

class KeyboardShortcutManager:
    """
    Manages keyboard shortcut mappings for the instrument GUI.

    Holds a registry of named actions with default key sequences and descriptions.
    The active mapping starts from defaults and can be customized by the user and
    persisted to a JSON file.

    Qt does not poll for key presses — instead, register() and apply_to_action()
    hand each mapping entry to Qt's event system (QShortcut / QAction.setShortcut),
    which fires the associated callback when the key is pressed.
    """

    REGISTRY: dict[str, tuple[str, str]] = {
        # action_id: (default_key_sequence, description)
        "refresh_all":  ("Ctrl+R",       "Refresh all parameters from instrument"),
        "expand_all":   ("Ctrl+E",       "Expand all tree nodes"),
        "collapse_all": ("Ctrl+Shift+E", "Collapse all tree nodes"),
        "toggle_star":  ("Ctrl+Shift+S", "Toggle star filter"),
        "toggle_trash": ("Ctrl+Shift+T", "Toggle trash filter"),
        "focus_filter": ("Ctrl+F",       "Focus the filter search bar"),
        "star_item":    ("Ctrl+S",       "Star/un-star the selected parameter"),
        "trash_item":   ("Ctrl+T",       "Trash/un-trash the selected parameter"),
    }

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {k: v[0] for k, v in self.REGISTRY.items()}
        self._shortcut_map: dict[str, QtWidgets.QShortcut] = {}
        self._action_map: dict[str, QtWidgets.QAction] = {}

    def load(self, path: str) -> None:
        """Override the current mapping with entries read from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        self.mapping.update(data)

    def save(self, path: str) -> None:
        """Write the current mapping to a JSON file."""
        with open(path, "w") as f:
            json.dump(self.mapping, f, indent=2)

    def apply_to_action(self, action_id: str, qaction: QtWidgets.QAction) -> None:
        """Set the shortcut from the current mapping on an existing QAction and retain a reference for live rebinding."""
        key = self.mapping.get(action_id)
        if key:
            qaction.setShortcut(QtGui.QKeySequence(key))
            self._action_map[action_id] = qaction

    def register(
        self, action_id: str, callback: Callable, widget: QtWidgets.QWidget
    ) -> None:
        """
        Create a QShortcut for action_id on widget and connect it to callback.

        The shortcut fires when widget or any of its children has focus.
        The QShortcut object is retained internally so it is not garbage-collected
        and can be updated live via rebind().
        """
        key = self.mapping.get(action_id)
        if key:
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), widget)
            sc.activated.connect(callback)
            self._shortcut_map[action_id] = sc

    def rebind(self, action_id: str, new_key: str) -> None:
        """Update a shortcut immediately. Updates the mapping and the live Qt objects."""
        self.mapping[action_id] = new_key
        if action_id in self._shortcut_map:
            self._shortcut_map[action_id].setKey(QtGui.QKeySequence(new_key))
        if action_id in self._action_map:
            self._action_map[action_id].setShortcut(QtGui.QKeySequence(new_key))
        logger.debug(f"Rebound '{action_id}' to '{new_key}'")


class ShortcutEditorDialog(BaseDialog):
    """
    Dialog for viewing and editing keyboard shortcuts.

    Displays all registered actions in a table. The Shortcut column is editable.
    Use 'Save to file' to persist changes; 'Load from file' to restore a saved mapping.
    Changes take effect on the next application start.
    """

    def __init__(
        self,
        manager: KeyboardShortcutManager,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Keyboard Shortcuts")

        self._table = QtWidgets.QTableWidget(len(manager.REGISTRY), 3, self)
        self._table.setHorizontalHeaderLabels(["Action", "Description", "Shortcut"])
        self._table.horizontalHeader().setStretchLastSection(True)  # type: ignore[union-attr]
        self._table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._populateTable()

        btnLoad = QtWidgets.QPushButton("Load from file")
        btnLoad.clicked.connect(self._loadFromFile)
        btnSave = QtWidgets.QPushButton("Save to file")
        btnSave.clicked.connect(self._saveToFile)
        btnReset = QtWidgets.QPushButton("Reset to defaults")
        btnReset.clicked.connect(self._resetDefaults)
        btnClose = QtWidgets.QPushButton("Close")
        btnClose.clicked.connect(self.accept)

        btnRow = QtWidgets.QHBoxLayout()
        btnRow.addWidget(btnLoad)
        btnRow.addWidget(btnSave)
        btnRow.addStretch()
        btnRow.addWidget(btnReset)
        btnRow.addWidget(btnClose)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._table)
        layout.addLayout(btnRow)
        self.setLayout(layout)
        self.resize(600, 300)

    def _populateTable(self) -> None:
        self._table.clearContents()
        for row, (action_id, (_, description)) in enumerate(
            self.manager.REGISTRY.items()
        ):
            current = self.manager.mapping.get(action_id, "")
            id_item = QtWidgets.QTableWidgetItem(action_id)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            desc_item = QtWidgets.QTableWidgetItem(description)
            desc_item.setFlags(desc_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, id_item)
            self._table.setItem(row, 1, desc_item)
            key_edit = QtWidgets.QKeySequenceEdit(
                QtGui.QKeySequence(current), self._table
            )
            self._table.setCellWidget(row, 2, key_edit)
        self._table.resizeColumnsToContents()

    def _commitTableToManager(self) -> None:
        for row, action_id in enumerate(self.manager.REGISTRY):
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                self.manager.rebind(action_id, widget.keySequence().toString())

    @QtCore.Slot()
    def _loadFromFile(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Shortcuts", ".", "JSON Files (*.json);;All Files (*)"
        )
        if path:
            try:
                self.manager.load(path)
                self._populateTable()
                logger.info(f"Loaded shortcuts from {path}")
            except Exception as e:
                logger.warning(f"Failed to load shortcuts from {path} : {e}")

    @QtCore.Slot()
    def _saveToFile(self) -> None:
        self._commitTableToManager()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Shortcuts", "shortcuts.json", "JSON Files (*.json);;All Files (*)"
        )
        if path:
            try:
                self.manager.save(path)
                logger.info(f"Saved shortcuts to {path}")
            except Exception as e:
                logger.warning(f"Failed to save shortcuts to {path} : {e}")

    @QtCore.Slot()
    def _resetDefaults(self) -> None:
        for row, (action_id, (default_key, _)) in enumerate(
            self.manager.REGISTRY.items()
        ):
            self.manager.rebind(action_id, default_key)
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                widget.setKeySequence(QtGui.QKeySequence(default_key))
