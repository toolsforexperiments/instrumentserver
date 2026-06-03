"""Tests for KeyboardShortcutManager and ShortcutEditorWidget."""

from pathlib import Path

import pytest
import yaml

from instrumentserver import QtCore, QtGui, QtWidgets
from instrumentserver.gui.shortcuts import KeyboardShortcutManager, ShortcutEditorWidget


def _write_yaml(tmp_path: Path, content: dict) -> Path:
    p = tmp_path / "config.yml"
    p.write_text(yaml.dump(content))
    return p


# ---------------------------------------------------------------------------
# KeyboardShortcutManager tests
# ---------------------------------------------------------------------------


def test_rebind_updates_mapping():
    manager = KeyboardShortcutManager()
    original = manager.mapping["jump_filter"]
    manager.rebind("jump_filter", "Ctrl+G")
    assert manager.mapping["jump_filter"] == "Ctrl+G"
    assert manager.mapping["jump_filter"] != original


def test_save_writes_diffs_to_file(tmp_path):
    cfg = _write_yaml(tmp_path, {"port": 8000})
    manager = KeyboardShortcutManager()
    manager.rebind("jump_filter", "Ctrl+G")
    manager.save(str(cfg))

    with open(cfg) as f:
        data = yaml.safe_load(f)

    assert "shortcuts" in data
    assert data["shortcuts"] == {"jump_filter": "Ctrl+G"}
    # only the diff, not the full registry
    assert "collapse_all" not in data["shortcuts"]


def test_save_removes_shortcuts_section_when_all_defaults(tmp_path):
    cfg = _write_yaml(tmp_path, {"port": 8000, "shortcuts": {"jump_filter": "Ctrl+G"}})
    manager = KeyboardShortcutManager()
    # mapping is at defaults — no diffs
    manager.save(str(cfg))

    with open(cfg) as f:
        data = yaml.safe_load(f)

    assert "shortcuts" not in data
    assert data["port"] == 8000


def test_load_from_dict_overrides_defaults():
    manager = KeyboardShortcutManager()
    default = manager.mapping["jump_filter"]
    manager.load_from_dict({"jump_filter": "Ctrl+G"})
    assert manager.mapping["jump_filter"] == "Ctrl+G"
    assert manager.mapping["jump_filter"] != default


# ---------------------------------------------------------------------------
# ShortcutEditorWidget button-state tests
# ---------------------------------------------------------------------------


@pytest.fixture
def manager():
    return KeyboardShortcutManager()


@pytest.fixture
def widget_no_path(qtbot, manager):
    w = ShortcutEditorWidget(manager, configPath="")
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def widget_with_path(qtbot, manager, tmp_path):
    cfg = _write_yaml(tmp_path, {"port": 8000})
    w = ShortcutEditorWidget(manager, configPath=str(cfg))
    qtbot.addWidget(w)
    w.show()
    return w, cfg


def test_apply_cancel_disabled_at_init(widget_no_path):
    w = widget_no_path
    assert not w._btnApply.isEnabled()
    assert not w._btnCancel.isEnabled()


def test_apply_cancel_enabled_after_edit(qtbot, widget_no_path, manager):
    w = widget_no_path
    # Find the QKeySequenceEdit for row 0 and simulate an edit
    key_edit = w._table.cellWidget(0, 2)
    assert isinstance(key_edit, QtWidgets.QKeySequenceEdit)
    key_edit.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    assert w._btnApply.isEnabled()
    assert w._btnCancel.isEnabled()


def test_apply_disables_apply_cancel(qtbot, widget_no_path):
    w = widget_no_path
    key_edit = w._table.cellWidget(0, 2)
    key_edit.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    assert w._btnApply.isEnabled()
    qtbot.mouseClick(w._btnApply, QtCore.Qt.LeftButton)

    assert not w._btnApply.isEnabled()
    assert not w._btnCancel.isEnabled()


def test_cancel_reverts_table_and_disables(qtbot, widget_no_path, manager):
    w = widget_no_path
    action_id = list(manager.REGISTRY.keys())[0]
    original_key = manager.mapping[action_id]

    key_edit = w._table.cellWidget(0, 2)
    key_edit.setKeySequence(QtGui.QKeySequence("Ctrl+G"))
    assert w._btnCancel.isEnabled()

    qtbot.mouseClick(w._btnCancel, QtCore.Qt.LeftButton)

    assert key_edit.keySequence().toString() == original_key
    assert not w._btnApply.isEnabled()
    assert not w._btnCancel.isEnabled()
    # manager mapping must NOT have changed
    assert manager.mapping[action_id] == original_key


def test_save_disabled_without_config_path(widget_no_path):
    w = widget_no_path
    assert not w._btnSaveFile.isEnabled()
    assert "config file" in w._btnSaveFile.toolTip().lower()


def test_apply_save_disabled_on_conflict(qtbot, widget_with_path):
    w, _ = widget_with_path
    # Set rows 0 and 1 to the same key — creates a conflict
    key_edit_0 = w._table.cellWidget(0, 2)
    key_edit_1 = w._table.cellWidget(1, 2)
    key_edit_0.setKeySequence(QtGui.QKeySequence("Ctrl+G"))
    key_edit_1.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    assert not w._btnApply.isEnabled()
    assert not w._btnSaveFile.isEnabled()
    # Cancel should still be available so the user can undo the conflict
    assert w._btnCancel.isEnabled()


def test_apply_save_reenabled_when_conflict_resolved(qtbot, widget_with_path):
    w, _ = widget_with_path
    key_edit_0 = w._table.cellWidget(0, 2)
    key_edit_1 = w._table.cellWidget(1, 2)
    key_edit_0.setKeySequence(QtGui.QKeySequence("Ctrl+G"))
    key_edit_1.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    assert not w._btnApply.isEnabled()

    # Resolve the conflict by giving row 1 a unique key
    key_edit_1.setKeySequence(QtGui.QKeySequence("Ctrl+H"))

    assert w._btnApply.isEnabled()
    assert w._btnSaveFile.isEnabled()


def test_conflict_indicator_is_red(qtbot, widget_with_path):
    """Indicator dots must turn red when a duplicate key exists in the table."""
    w, _ = widget_with_path
    key_edit_0 = w._table.cellWidget(0, 2)
    key_edit_1 = w._table.cellWidget(1, 2)
    key_edit_1.setKeySequence(key_edit_0.keySequence())

    dot_0 = w._indicators[0]
    dot_1 = w._indicators[1]
    assert "Duplicate" in dot_0.toolTip()
    assert "Duplicate" in dot_1.toolTip()


def test_indicator_yellow_after_apply_not_saved(qtbot, widget_with_path, manager):
    """After Apply, indicator must be yellow (applied to session, not yet on disk)."""
    w, _ = widget_with_path
    key_edit = w._table.cellWidget(0, 2)
    key_edit.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    qtbot.mouseClick(w._btnApply, QtCore.Qt.LeftButton)

    assert "applied" in w._indicators[0].toolTip().lower()
    assert "not saved" in w._indicators[0].toolTip().lower()


def test_indicator_green_after_save(qtbot, widget_with_path):
    """After Save, indicator must be green (file matches live state)."""
    w, _ = widget_with_path
    key_edit = w._table.cellWidget(0, 2)
    key_edit.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    qtbot.mouseClick(w._btnSaveFile, QtCore.Qt.LeftButton)

    assert w._indicators[0].toolTip() == ""


def test_restoreAfterRevert_refreshes_indicators_after_spurious_clear(
    qtbot, widget_with_path
):
    """
    _restoreAfterRevert must call _updateAllIndicators after unblocking signals.

    Real keyboard flow: user types a duplicate key → indicator goes red → the
    QKeySequenceEdit's finishing timeout fires a spurious keySequenceChanged("")
    BEFORE editingFinished → _onUnsavedChange clears the red indicator (no
    duplicate found for "") → editingFinished fires → blockSignals(True) →
    _restoreAfterRevert puts the key back (signals blocked) → blockSignals(False).

    Without an explicit refresh inside _restoreAfterRevert, the indicator stays
    orange/green even though the widget again shows the duplicate key.
    """
    w, _ = widget_with_path
    key_edit_0 = w._table.cellWidget(0, 2)
    key_edit_1 = w._table.cellWidget(1, 2)
    intended_key = key_edit_0.keySequence().toString()

    # Step 1: user types the duplicate key — indicator goes red
    key_edit_1.setKeySequence(QtGui.QKeySequence(intended_key))
    assert "Duplicate" in w._indicators[1].toolTip()

    # Step 2: spurious keySequenceChanged("") fires *before* editingFinished,
    # incorrectly clearing the indicator back to orange/green
    key_edit_1.setKeySequence(QtGui.QKeySequence(""))
    assert "Duplicate" not in w._indicators[1].toolTip()  # confirm indicator cleared

    # Step 3: editingFinished fires → blockSignals(True)
    key_edit_1.blockSignals(True)

    # Step 4: _restoreAfterRevert runs (value was cleared internally, restores it)
    w._restoreAfterRevert(intended_key, key_edit_1)

    # Widget must show the intended key
    assert key_edit_1.keySequence().toString() == intended_key
    # Indicator must be red again — not stay orange from the spurious clear
    assert "Duplicate" in w._indicators[1].toolTip()


def test_apply_uses_intended_value_when_signals_blocked(qtbot, widget_no_path, manager):
    """
    _applyToManager must use the stashed intended value for widgets whose signals
    are blocked (mid _onEditingFinished / _restoreAfterRevert cycle).

    Simulates the race: editingFinished fires → signals blocked → widget internally
    resets to "" → Apply/Save reads the widget before _restoreAfterRevert runs.
    Without the fix, the empty string gets applied to the manager.
    """
    w = widget_no_path
    action_id = list(manager.REGISTRY.keys())[0]
    key_edit = w._table.cellWidget(0, 2)

    # Simulate the state after _onEditingFinished ran but before _restoreAfterRevert:
    # widget has been cleared internally and signals are blocked.
    intended = "Ctrl+G"
    w._pending_restores[key_edit] = intended
    key_edit.blockSignals(True)
    key_edit.setKeySequence(QtGui.QKeySequence(""))  # simulate internal clear

    # Apply reads the widget — without the fix this applies "" to the manager
    w._applyToManager()

    assert manager.mapping[action_id] == intended


def test_save_applies_and_writes_file(qtbot, widget_with_path, manager):
    w, cfg = widget_with_path
    action_id = list(manager.REGISTRY.keys())[0]

    key_edit = w._table.cellWidget(0, 2)
    key_edit.setKeySequence(QtGui.QKeySequence("Ctrl+G"))

    assert w._btnSaveFile.isEnabled()
    qtbot.mouseClick(w._btnSaveFile, QtCore.Qt.LeftButton)

    # Apply/Cancel disabled after save
    assert not w._btnApply.isEnabled()
    assert not w._btnCancel.isEnabled()

    # File was written with the diff
    with open(cfg) as f:
        data = yaml.safe_load(f)
    assert data.get("shortcuts", {}).get(action_id) == "Ctrl+G"

    # Manager mapping updated
    assert manager.mapping[action_id] == "Ctrl+G"
