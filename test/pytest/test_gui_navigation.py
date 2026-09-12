"""Keyboard navigation in the instrument parameter tree (PR #145)."""

from instrumentserver import QtCore, QtWidgets
from instrumentserver.server.application import startServerGuiApplication


def _shutdown_server_window(qtbot, window):
    """Trigger closeEvent and wait for the server thread to exit so the next
    test can bind the same port again.

    The server's ``finished`` signal is delivered to ``QThread.quit`` through the
    main-thread event loop, so we must keep processing events while waiting
    instead of blocking in ``QThread.wait``.
    """
    try:
        window.close()
    except Exception:
        pass
    thread = getattr(window, "stationServerThread", None)
    if thread is not None:
        qtbot.waitUntil(lambda: not thread.isRunning(), timeout=10000)


# Use a spare port so these tests never talk to a developer's live server on 5555.
TEST_PORT = 5599

TIMEOUT_INS = (
    "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout"
)


def _start_window(qtbot):
    """Create the server window and wait until its embedded client points at the
    test server.

    The embedded client connects to the default port when it is constructed and
    only re-targets the real server port once the event loop delivers the
    server-started signal, so the first request must not be sent before then.
    """
    window = startServerGuiApplication(port=TEST_PORT)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window.client.addr.endswith(f":{TEST_PORT}"), timeout=10000)
    return window


def _open_instrument_tab(window, name, cls):
    window.client.find_or_create_instrument(name, cls)
    window.refreshStationAction.trigger()
    item = window.stationList.findItems(
        name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0
    )
    window.addInstrumentTab(item[0], 0)
    return window.instrumentTabsOpen[name]


def _find_row(view, text):
    model = view.model()
    matches = model.match(
        model.index(0, 0), QtCore.Qt.DisplayRole, text, 1, QtCore.Qt.MatchRecursive
    )
    assert matches, f"row {text!r} not found"
    return matches[0]


def test_backspace_does_not_blank_read_only_parameter(qtbot):
    window = _start_window(qtbot)
    try:
        tab = _open_instrument_tab(window, "timeout", TIMEOUT_INS)
        params = tab.parametersList
        view = params.view

        widget = params.view.delegate.parameters["random_int"]
        label = widget.paramWidget
        assert isinstance(label, QtWidgets.QLabel)
        before = label.text()
        assert before != ""

        view.setCurrentIndex(_find_row(view, "random_int"))
        # Drive the slot the Backspace shortcut is wired to.
        view.clearCurrentParameter.emit()

        assert label.text() == before
    finally:
        _shutdown_server_window(qtbot, window)


def test_backspace_clears_editable_parameter(qtbot):
    window = _start_window(qtbot)
    try:
        tab = _open_instrument_tab(window, "timeout", TIMEOUT_INS)
        params = tab.parametersList
        view = params.view

        widget = params.view.delegate.parameters["param1"]
        # param1 has no validator, so it is shown in an AnyInput wrapping a QLineEdit
        line_edit = widget.paramWidget.input
        assert line_edit.text() != ""

        view.setCurrentIndex(_find_row(view, "param1"))
        view.clearCurrentParameter.emit()

        assert line_edit.text() == ""
    finally:
        _shutdown_server_window(qtbot, window)


SUBMODULE_INS = (
    "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule"
)


def test_enter_toggles_node_with_children(qtbot):
    window = _start_window(qtbot)
    try:
        tab = _open_instrument_tab(window, "dummy", SUBMODULE_INS)
        view = tab.parametersList.view

        node = _find_row(view, "A")
        assert view.model().hasChildren(node)
        assert view.isExpanded(node)  # trees start fully expanded

        view.setCurrentIndex(node)
        edits = []
        view.editCurrentParameter.connect(lambda: edits.append(1))

        view.onEditKeyPressed()
        assert not view.isExpanded(node)
        view.onEditKeyPressed()
        assert view.isExpanded(node)
        assert edits == []  # a node never asks to edit a value
    finally:
        _shutdown_server_window(qtbot, window)


def test_right_expands_node_then_moves_to_first_child(qtbot):
    window = _start_window(qtbot)
    try:
        tab = _open_instrument_tab(window, "dummy", SUBMODULE_INS)
        view = tab.parametersList.view

        node = _find_row(view, "A")
        view.collapse(node)
        view.setCurrentIndex(node)

        view.onRightKeyPressed()
        assert view.isExpanded(node)
        assert view.currentIndex() == node

        view.onRightKeyPressed()
        assert view.currentIndex() == view.model().index(0, 0, node)
    finally:
        _shutdown_server_window(qtbot, window)


def test_enter_on_parameter_requests_edit(qtbot):
    window = _start_window(qtbot)
    try:
        tab = _open_instrument_tab(window, "dummy", SUBMODULE_INS)
        view = tab.parametersList.view

        view.setCurrentIndex(_find_row(view, "param1"))
        with qtbot.waitSignal(view.editCurrentParameter, timeout=1000):
            view.onEditKeyPressed()
    finally:
        _shutdown_server_window(qtbot, window)
