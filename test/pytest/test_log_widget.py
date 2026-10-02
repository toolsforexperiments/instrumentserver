"""The GUI log handler: records reach the log widget from any thread, and
nothing it leaves behind raises once Qt has deleted the widget — neither a
later record nor ``logging.shutdown`` at interpreter exit."""

import logging
import os
import subprocess
import sys
import textwrap
import threading

from qtpy import sip

from instrumentserver.log import LogWidget, QLogHandler

LOGGER = "instrumentserver"


def test_a_record_reaches_the_widget(qtbot):
    widget = LogWidget()
    qtbot.addWidget(widget)
    try:
        logging.getLogger(LOGGER).warning("hello from the test")
        qtbot.waitUntil(
            lambda: "hello from the test" in widget.handler.widget.toPlainText()
        )
    finally:
        logging.getLogger(LOGGER).removeHandler(widget.handler)


def test_a_record_from_another_thread_reaches_the_widget(qtbot):
    """The server logs from its own thread; the line must still be
    appended (in the GUI thread, through the bridge's signal)."""
    widget = LogWidget()
    qtbot.addWidget(widget)
    try:
        thread = threading.Thread(
            target=lambda: logging.getLogger(LOGGER).warning("from a thread")
        )
        thread.start()
        thread.join()
        qtbot.waitUntil(
            lambda: "from a thread" in widget.handler.widget.toPlainText()
        )
    finally:
        logging.getLogger(LOGGER).removeHandler(widget.handler)


def test_a_record_after_the_widget_is_deleted_detaches_the_handler(qtbot):
    widget = LogWidget()
    handler = widget.handler
    assert isinstance(handler, QLogHandler)
    sip.delete(widget)
    logger = logging.getLogger(LOGGER)
    with qtbot.captureExceptions() as exceptions:
        logger.warning("nobody is listening")
    assert exceptions == []
    assert handler not in logger.handlers


def test_detaching_a_dead_handler_does_not_skip_the_next_handler(qtbot):
    """A dead handler detaches itself while the logger is looping over its
    handlers; the handler after it must still get the record."""
    logger = logging.getLogger(LOGGER)
    first = LogWidget()
    first_handler = first.handler
    sip.delete(first)
    second = LogWidget()
    second_handler = second.handler
    sip.delete(second)
    with qtbot.captureExceptions() as exceptions:
        logger.warning("both dead handlers should detach")
    assert exceptions == []
    assert first_handler not in logger.handlers
    assert second_handler not in logger.handlers


def test_closing_the_app_leaves_no_traceback_from_the_log_handler():
    """Qt deletes the log widget before the interpreter exits, and
    ``logging.shutdown`` then visits every handler still registered. The
    handler used to be a QObject itself, so the exit printed "wrapped
    C/C++ object of type QLogHandler has been deleted"."""
    script = textwrap.dedent(
        """
        import logging
        from qtpy import sip
        from instrumentserver import QtWidgets
        from instrumentserver.log import LogWidget

        app = QtWidgets.QApplication([])
        widget = LogWidget()
        logging.getLogger("instrumentserver").warning("hello")
        sip.delete(widget)
        """
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "has been deleted" not in result.stderr, result.stderr
