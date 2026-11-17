"""
instrumentserver.log : Logging tools and defaults for instrumentserver.
"""

import logging
import re
import sys
from enum import Enum, auto, unique
from html import escape
from typing import Callable, Optional

from . import QtCore, QtGui, QtWidgets


@unique
class LogLevels(Enum):
    error = auto()
    warn = auto()
    info = auto()
    debug = auto()


class _LogBridge(QtCore.QObject):
    """The Qt side of :class:`QLogHandler`: the text widget, and the signal
    that carries each html line into the GUI thread, where the slot
    appends it to the widget.

    The bridge has no Qt parent, so Qt never deletes it together with the
    widget. Records are emitted on it from any thread (the server logs
    from its own), and a parent deleting it in the GUI thread while
    another thread emits on it crashes or deadlocks. The handler deletes
    the bridge itself (:meth:`QLogHandler.detach`), only after no thread
    can emit on it any more."""

    #: Signal(str) : Emitted with the html-formatted log record to append to the widget
    new_html = QtCore.Signal(str)

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        on_widget_destroyed: Callable[[], None],
    ) -> None:
        super().__init__()
        self.widget = QtWidgets.QTextEdit(parent)
        self.widget.setReadOnly(True)
        self._widget_alive = True
        self._on_widget_destroyed_cb = on_widget_destroyed
        # connect signal to slot that actually touches the widget (GUI thread)
        self.new_html.connect(self._append_html)
        # the widget dies with its parent (the LogWidget); both run in the
        # GUI thread, so this slot runs right inside the deletion
        self.widget.destroyed.connect(self._on_widget_destroyed)

    @QtCore.Slot()
    def _on_widget_destroyed(self) -> None:
        self._widget_alive = False
        self._on_widget_destroyed_cb()

    @QtCore.Slot(str)
    def _append_html(self, html: str) -> None:
        """Append HTML to the text widget in the GUI thread."""
        # a line posted before the widget was deleted can arrive after it
        if not self._widget_alive:
            return
        self.widget.append(html)
        # reset char format so bold/italics don’t bleed into the next line
        self.widget.setCurrentCharFormat(QtGui.QTextCharFormat())
        # keep view scrolled to bottom
        self.widget.verticalScrollBar().setValue(  # type: ignore[union-attr]
            self.widget.verticalScrollBar().maximum()  # type: ignore[union-attr]
        )


class QLogHandler(logging.Handler):
    """A simple log handler that supports logging in TextEdit.

    The handler itself is a plain :class:`logging.Handler`, not a
    ``QObject``: :func:`logging.shutdown` visits every handler at
    interpreter exit, after Qt has deleted the widgets, and touching a
    deleted ``QObject`` there raises. The Qt objects live in a
    :class:`_LogBridge`; the text widget is parented to ``parent``.

    When the text widget is deleted the handler detaches itself from every
    logger, so windows that come and go (each server window has a
    LogWidget) leave no handlers behind on the shared logger."""

    COLORS = {
        logging.ERROR: QtGui.QColor("red"),
        logging.WARNING: QtGui.QColor("orange"),
        logging.INFO: QtGui.QColor("green"),
        logging.DEBUG: QtGui.QColor("gray"),
    }

    def __init__(self, parent: Optional[QtWidgets.QWidget]) -> None:
        super().__init__()
        self._closed = False
        self._bridge = _LogBridge(parent, self.detach)
        self.widget = self._bridge.widget
        self._transform: Optional[Callable[[logging.LogRecord, str], Optional[str]]] = (
            None
        )

    def set_transform(
        self, fn: Callable[[logging.LogRecord, str], Optional[str]]
    ) -> None:
        """fn(record, msg) -> str | {'html': str} | None"""
        self._transform = fn

    def emit(self, record: logging.LogRecord) -> None:
        # logging.Handler.handle holds self.lock around emit, and detach
        # sets _closed under the same lock: once detach has returned, no
        # thread is inside emit or can enter the bridge again
        if self._closed:
            return
        try:
            formatted = self.format(record)  # prefix + message
            raw_msg = record.getMessage()  # message only

            # Color for prefix (log level)
            clr = self.COLORS.get(record.levelno, QtGui.QColor("black")).name()

            if self._transform is not None:
                html_fragment = self._transform(record, raw_msg)
                if html_fragment:
                    i = formatted.rfind(raw_msg)
                    if i >= 0:
                        prefix = formatted[:i]
                        suffix = formatted[i + len(raw_msg) :]
                    else:
                        prefix, suffix = "", ""

                    # Build HTML line
                    html = (
                        f"<span style='color:{clr}'>{escape(prefix)}</span>"
                        f"{html_fragment}"
                        f"{escape(suffix)}"
                    )

                    # send to GUI thread
                    self._bridge.new_html.emit(html)
                    return

            # fallback: original plain text path
            msg = formatted
            clr_q = self.COLORS.get(record.levelno, QtGui.QColor("black")).name()
            html = f"<span style='color:{clr_q}'>{escape(msg)}</span>"

            self._bridge.new_html.emit(html)
        except RuntimeError:
            # the bridge is gone (e.g. at interpreter exit): stop receiving
            # records so Python can collect us
            self._remove_from_loggers()

    def detach(self) -> None:
        """Stop handling records and delete the bridge.

        Called in the GUI thread when the text widget is deleted. Waits for
        a record another thread is emitting right now, then removes the
        handler from every logger and schedules the bridge for deletion."""
        with self.lock:  # type: ignore[union-attr]
            if self._closed:
                return
            self._closed = True
        self._remove_from_loggers()
        try:
            self._bridge.deleteLater()
        except RuntimeError:
            pass

    def _remove_from_loggers(self) -> None:
        # Assign a new list rather than removeHandler: another thread (or
        # this one) may be iterating over the logger's handlers right now,
        # and removing from the list in place would skip the next handler.
        for lg in list(logging.Logger.manager.loggerDict.values()) + [
            logging.getLogger()
        ]:
            if isinstance(lg, logging.Logger) and self in lg.handlers:
                lg.handlers = [h for h in lg.handlers if h is not self]


class LogWidget(QtWidgets.QWidget):
    """
    A simple logger widget. Uses QLogHandler as handler.
    The handler has the actual widget that is used to display the logs.
    """

    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, level: int = logging.INFO
    ) -> None:
        super().__init__(parent)

        # set up the graphical handler
        fmt = logging.Formatter(
            "[%(asctime)s] [%(name)s: %(levelname)s] %(message)s",
            datefmt="%m-%d %H:%M:%S",
        )
        logTextBox = QLogHandler(self)
        logTextBox.setFormatter(fmt)
        logTextBox.setLevel(level)
        self.handler = logTextBox

        # make the widget
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(logTextBox.widget)
        self.setLayout(layout)

        # configure the logger
        self.logger = logging.getLogger("instrumentserver")

        # delete old graphical handler. however, that would allow only one
        # graphical handler per kernel. not sure i want that...?
        # for h in self.logger.handlers:
        #     if isinstance(h, QLogHandler):
        #         self.logger.removeHandler(h)
        #         h.widget.deleteLater()
        #         del h

        self.logger.addHandler(logTextBox)
        self.handler.set_transform(_param_update_formatter)


def _param_update_formatter(record: logging.LogRecord, raw_msg: str) -> Optional[str]:
    """
    A formater that makes parameter updates more prominent in the gui log window.
    """
    # Pattern 1: "parameter-update" from the broadcaster, for client station
    pattern_update = re.compile(r"parameter-update:\s*([A-Za-z0-9_.]+):\s*(.+)", re.S)

    # Pattern 2: normal log message from the server. i.e. `Parameter {name} set to: {value}`
    pattern_info = re.compile(
        r"Parameter\s+'([A-Za-z0-9_.]+)'\s+set\s+to:\s*(.+)", re.S
    )

    match = pattern_update.search(raw_msg) or pattern_info.search(raw_msg)
    if not match:
        return None

    name, value = match.groups()

    # Escape HTML but keep \n literal (QTextEdit.append will render them)
    return (
        f"<b>{escape(name)}</b> set to: "
        f"<span style='color:#7e5bef; font-weight:bold'>{escape(value)}</span>"
    )


def setupLogging(
    addStreamHandler: bool = True,
    logFile: Optional[str] = None,
    name: str = "instrumentserver",
    streamHandlerLevel: int = logging.INFO,
) -> None:
    """Setting up logging, including adding a custom handler."""

    logger = logging.getLogger(name)

    for h in logger.handlers:
        logger.removeHandler(h)
        del h

    if logFile is not None:
        fmt = logging.Formatter(
            "%(asctime)s\t: %(name)s\t: %(levelname)s\t: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = logging.FileHandler(logFile)
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)

    if addStreamHandler:
        fmt = logging.Formatter(
            "[%(asctime)s] [%(name)s: %(levelname)s] %(message)s",
            datefmt="%m/%d %H:%M",
        )
        streamHandler = logging.StreamHandler(sys.stderr)
        streamHandler.setFormatter(fmt)
        streamHandler.setLevel(streamHandlerLevel)
        logger.addHandler(streamHandler)

    logger.info(f"Logging set up for {name}.")


def logger(name: str = "instrumentserver") -> logging.Logger:
    """Get the (root) logger for the package."""
    return logging.getLogger(name)


def log(logger: logging.Logger, message: str, level: LogLevels) -> None:
    """Simple wrapper to log messages.

    Useful when the log level is a variable.
    """
    logFuncs = {
        LogLevels.error: logger.error,
        LogLevels.warn: logger.warning,
        LogLevels.info: logger.info,
        LogLevels.debug: logger.debug,
    }
    logFuncs[level](message)
