import logging
from collections import defaultdict
from typing import Callable, Optional, Union

import yaml

from instrumentserver import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


class KeyboardShortcutManager:
    """
    Manages keyboard shortcut mappings for the instrument GUI.

    Holds a registry of named actions with default key sequences and descriptions.
    The active mapping starts from defaults and can be customized by the user and
    persisted to a JSON file.

    Qt does not poll for key presses — instead, register() hands each mapping entry
    to Qt's event system via QShortcut, which fires the associated callback when the
    key is pressed. register_tooltip() tracks widgets whose tooltips should display
    the current key hint and be updated live when the user rebinds.
    """

    REGISTRY: dict[str, tuple[str, str]] = {
        # action_id: (default_key_sequence, description)
        "jump_filter": ("Ctrl+F", "Jump cursor to the filter search bar"),
        "collapse_all": ("Ctrl+Shift+E", "Collapse all tree nodes"),
        "expand_all": ("Ctrl+E", "Expand all tree nodes"),
        "toggle_star": ("Ctrl+Shift+A", "Toggle star filter"),
        "star_item": ("Ctrl+A", "Star/un-star the selected parameter"),
        "toggle_trash": ("Ctrl+Shift+T", "Toggle trash filter"),
        "trash_item": ("Ctrl+T", "Trash/un-trash the selected parameter"),
        "refresh_all": ("Ctrl+Shift+R", "Refresh all parameters from instrument"),
        "refresh_item": ("Ctrl+R", "Refresh the selected parameter"),
        "toggle_python": ("Ctrl+P", "Toggle Python eval for selected parameter"),
        "delete_item": ("Ctrl+Backspace", "Delete the selected parameter"),
        "run_method": ("Ctrl+Return", "Runs the selected method"),
        "clear_add": ("Ctrl+Shift+N", "Clear regions of add parameter bar"),
        "add_item": ("Ctrl+N", "Jump cursor to the add parameter bar"),
        "load_items": ("Ctrl+Shift+O", "Load parameters from JSON file"),
        "save_items": ("Ctrl+Shift+S", "Save parameters to JSON file"),
        "fit_column": ("Ctrl+Shift+D", "Fits column width"),
        "sort_column": ("Ctrl+D", "Toggle sorting of selected column"),
        "edit_value": ("Right", "Jump cursor to value field for selected parameter"),
    }

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {k: v[0] for k, v in self.REGISTRY.items()}
        self._shortcut_map: dict[str, list[QtWidgets.QShortcut]] = defaultdict(list)
        self._tooltip_widgets: dict[
            str, list[tuple[Union[QtWidgets.QAction, QtWidgets.QWidget], str]]
        ] = defaultdict(list)

    def load_from_dict(self, config: dict[str, str]) -> None:
        """Override the current mapping with entries read from serverConfig file."""
        self.mapping.update(config)

    def save(self, path: str) -> None:
        """Write the current mapping to the serverConfig file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        diffs = {k: v for k, v in self.mapping.items() if v != self.REGISTRY[k][0]}
        if diffs:
            data["shortcuts"] = diffs
        elif "shortcuts" in data:
            del data["shortcuts"]
        with open(path, "w") as f:
            yaml.dump(data, f, indent=2)

    def register_tooltip(
        self,
        action_id: str,
        widget: Optional[Union[QtWidgets.QAction, QtWidgets.QWidget]],
    ) -> None:
        """Append the current key hint to widget's tooltip and track it for live rebinding."""
        if widget is None:
            return
        key = self.mapping.get(action_id, "")
        if not key:
            return
        base_tip = widget.toolTip()
        widget.setToolTip(f"{base_tip}  [{key}]" if base_tip else f"[{key}]")
        self._tooltip_widgets[action_id].append((widget, base_tip))
        widget.destroyed.connect(
            lambda _, aid=action_id, ref=widget: self._remove_tooltip_widget(aid, ref)
        )

    def _remove_tooltip_widget(
        self, action_id: str, widget: Union[QtWidgets.QAction, QtWidgets.QWidget]
    ) -> None:
        self._tooltip_widgets[action_id] = [
            (w, t) for w, t in self._tooltip_widgets[action_id] if w is not widget
        ]

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
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(callback)
            self._shortcut_map[action_id].append(sc)
            sc.destroyed.connect(
                lambda _, aid=action_id, ref=sc: (
                    self._shortcut_map[aid].remove(ref)
                    if ref in self._shortcut_map[aid]
                    else None
                )
            )

    def rebind(self, action_id: str, new_key: str) -> None:
        """Update a shortcut immediately. Updates the mapping and the live Qt objects."""
        self.mapping[action_id] = new_key
        for sc in self._shortcut_map.get(action_id, []):
            sc.setKey(QtGui.QKeySequence(new_key))
        for widget, base_tip in self._tooltip_widgets.get(action_id, []):
            widget.setToolTip(
                f"{base_tip}  [{new_key}]" if base_tip else f"[{new_key}]"
            )
        logger.debug(f"Rebound '{action_id}' to '{new_key}'")


class ShortcutEditorWidget(QtWidgets.QWidget):
    """
    Permanent widget for viewing and editing keyboard shortcuts.

    Intended to be embedded as a tab in the server window. Changes made in the
    table are applied live to the manager (and therefore all registered shortcuts)
    when 'Save to File' is clicked. Also use 'Save to file' to persist across sessions.

    Each row has a small colored indicator dot in the rightmost column:
      - transparent : saved and unique
      - orange: unsaved change (widget value differs from manager.mapping)
      - yellow: applied to the manager but not yet saved to file
      - red   : duplicate key sequence shared with another action (takes priority)

    QKeySequenceEdit emits a spurious keySequenceChanged after its finishing timeout
    resets the internal recording state. _onEditingFinished blocks that widget's signals
    for one event-loop tick (swallowing the revert signal at the source), then restores
    the display if the widget actually changed its stored sequence during the block.
    """

    def __init__(
        self,
        manager: KeyboardShortcutManager,
        configPath: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self._file_mapping: dict[str, str] = dict(manager.mapping)
        # Widgets currently mid _onEditingFinished / _restoreAfterRevert cycle.
        # Maps widget → intended key so _applyToManager can read the correct value
        # even when the widget's internal state has been temporarily cleared.
        self._pending_restores: dict[QtWidgets.QKeySequenceEdit, str] = {}

        self._table = QtWidgets.QTableWidget(len(manager.REGISTRY), 4, self)
        self._table.setHorizontalHeaderLabels(["Action", "Description", "Shortcut", ""])
        header = self._table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 32)
        self._table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

        self._indicators: list[QtWidgets.QLabel] = []
        self._populateTable()

        btnReset = QtWidgets.QPushButton("Reset to defaults")
        btnReset.clicked.connect(self._resetDefaults)

        self._btnCancel = QtWidgets.QPushButton("Cancel")
        self._btnCancel.setEnabled(False)
        self._btnCancel.clicked.connect(self._cancel)

        self._btnApply = QtWidgets.QPushButton("Apply")
        self._btnApply.setEnabled(False)
        self._btnApply.clicked.connect(self._apply)

        self._btnSaveFile = QtWidgets.QPushButton("Save to file")
        self._btnSaveFile.clicked.connect(self._saveToFile)
        if configPath:
            self._btnSaveFile.setEnabled(True)
        else:
            self._btnSaveFile.setEnabled(False)
            self._btnSaveFile.setToolTip(
                "Start the server with a config file to enable this button"
            )

        btnRow = QtWidgets.QHBoxLayout()
        btnRow.addStretch()
        btnRow.addWidget(btnReset)
        btnRow.addWidget(self._btnCancel)
        btnRow.addWidget(self._btnApply)
        btnRow.addWidget(self._btnSaveFile)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._table)
        layout.addLayout(btnRow)
        self.setLayout(layout)

        self.configPath = configPath

    def _populateTable(self) -> None:
        self._indicators.clear()
        self._table.clearContents()
        for row, (action_id, (_, description)) in enumerate(
            self.manager.REGISTRY.items()
        ):
            current = self.manager.mapping.get(action_id, "")

            id_item = QtWidgets.QTableWidgetItem(action_id)
            id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)  # type: ignore[arg-type]

            desc_item = QtWidgets.QTableWidgetItem(description)
            desc_item.setFlags(desc_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)  # type: ignore[arg-type]

            self._table.setItem(row, 0, id_item)
            self._table.setItem(row, 1, desc_item)

            key_edit = QtWidgets.QKeySequenceEdit(
                QtGui.QKeySequence(current), self._table
            )
            key_edit.keySequenceChanged.connect(self._onUnsavedChange)
            key_edit.editingFinished.connect(
                lambda w=key_edit: self._onEditingFinished(w)
            )
            self._table.setCellWidget(row, 2, key_edit)

            dot = QtWidgets.QLabel()
            dot.setFixedSize(20, 20)
            dot.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet(
                "QToolTip { color: black; background-color: white;"
                " border: 1px solid #cccccc; }"
            )
            container = QtWidgets.QWidget()
            cl = QtWidgets.QHBoxLayout(container)
            cl.addWidget(dot)
            cl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            cl.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 3, container)
            self._indicators.append(dot)

        self._updateAllIndicators()

    def _collectDuplicates(self) -> dict[str, list[str]]:
        """Return {key_sequence: [action_ids]} for every key bound to more than one action."""
        seen: dict[str, list[str]] = defaultdict(list)
        for row, action_id in enumerate(self.manager.REGISTRY):
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                key = widget.keySequence().toString()
                if key:
                    seen[key].append(action_id)
        return {k: v for k, v in seen.items() if len(v) > 1}

    def _updateAllIndicators(self) -> None:
        duplicates = self._collectDuplicates()
        for row, action_id in enumerate(self.manager.REGISTRY):
            if row >= len(self._indicators):
                break
            dot = self._indicators[row]
            widget = self._table.cellWidget(row, 2)
            if not isinstance(widget, QtWidgets.QKeySequenceEdit):
                continue
            current = self._pending_restores.get(widget, widget.keySequence().toString())
            if current in duplicates:
                others = [a for a in duplicates[current] if a != action_id]
                self._applyIndicator(
                    dot, "duplicate", f"Duplicate: also bound to {', '.join(others)}"
                )
            elif current != self.manager.mapping.get(action_id, ""):
                self._applyIndicator(dot, "unsaved", "Unsaved and unapplied changes")
            elif current != self._file_mapping.get(action_id, ""):
                self._applyIndicator(dot, "applied", "Changes applied but not saved to file")
            else:
                self._applyIndicator(dot, "ok", "")

    @staticmethod
    def _applyIndicator(dot: QtWidgets.QLabel, state: str, tooltip: str) -> None:
        dot.setToolTip(tooltip)

        if state == "ok":
            icon = QtGui.QIcon(":/icons/no-alert.svg")
        elif state == "unsaved":
            icon = QtGui.QIcon(":/icons/orange-alert.svg")
        elif state == "applied":
            icon = QtGui.QIcon(":/icons/yellow-alert.svg")
        else:  # duplicate
            icon = QtGui.QIcon(":/icons/red-alert.svg")
        pix = icon.pixmap(20, 20)
        dot.setPixmap(pix)

    def _updateApplyCancelState(self) -> None:
        """Enable Apply/Cancel/Save based on pending changes and conflicts."""
        has_pending = False
        for row, action_id in enumerate(self.manager.REGISTRY):
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                if widget.keySequence().toString() != self.manager.mapping.get(action_id, ""):
                    has_pending = True
                    break
        has_conflicts = bool(self._collectDuplicates())
        self._btnApply.setEnabled(has_pending and not has_conflicts)
        self._btnCancel.setEnabled(has_pending)
        self._btnSaveFile.setEnabled(bool(self.configPath) and not has_conflicts)

    @QtCore.Slot()
    def _onUnsavedChange(self) -> None:
        self._updateAllIndicators()
        self._updateApplyCancelState()

    def _onEditingFinished(self, widget: QtWidgets.QKeySequenceEdit) -> None:
        intended = widget.keySequence().toString()
        self._pending_restores[widget] = intended
        widget.blockSignals(True)
        QtCore.QTimer.singleShot(0, lambda: self._restoreAfterRevert(intended, widget))

    def _restoreAfterRevert(
        self, intended: str, widget: QtWidgets.QKeySequenceEdit
    ) -> None:
        if widget.keySequence().toString() != intended:
            widget.setKeySequence(QtGui.QKeySequence(intended))
        widget.blockSignals(False)
        self._pending_restores.pop(widget, None)
        # No keySequenceChanged fires after unblocking, so refresh state explicitly.
        self._updateAllIndicators()
        self._updateApplyCancelState()

    def _applyToManager(self) -> None:
        """Apply all table values to the live manager."""
        for row, action_id in enumerate(self.manager.REGISTRY):
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                key = self._pending_restores.get(widget, widget.keySequence().toString())
                self.manager.rebind(action_id, key)

    @QtCore.Slot()
    def _apply(self) -> None:
        self._applyToManager()
        self._updateAllIndicators()
        self._updateApplyCancelState()

    @QtCore.Slot()
    def _cancel(self) -> None:
        for row, action_id in enumerate(self.manager.REGISTRY):
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                widget.setKeySequence(
                    QtGui.QKeySequence(self.manager.mapping.get(action_id, ""))
                )
        self._updateAllIndicators()
        self._updateApplyCancelState()

    @QtCore.Slot()
    def _saveToFile(self) -> None:
        self._applyToManager()
        if self.configPath:
            try:
                self.manager.save(self.configPath)
                self._file_mapping = dict(self.manager.mapping)
                logger.info(f"Saved shortcuts to {self.configPath}")
            except Exception as e:
                logger.warning(f"Failed to save shortcuts to {self.configPath}: {e}")
        self._updateAllIndicators()
        self._updateApplyCancelState()

    @QtCore.Slot()
    def _resetDefaults(self) -> None:
        for row, (action_id, (default_key, _)) in enumerate(
            self.manager.REGISTRY.items()
        ):
            self.manager.rebind(action_id, default_key)
            widget = self._table.cellWidget(row, 2)
            if isinstance(widget, QtWidgets.QKeySequenceEdit):
                widget.setKeySequence(QtGui.QKeySequence(default_key))
        self._updateAllIndicators()
        self._updateApplyCancelState()
