"""
instrumentserver.log : logging tools and defaults for instrumentserver.
"""

import sys
import logging
from enum import Enum, auto, unique

from . import QtGui, QtWidgets


@unique
class LogLevels(Enum):
    error = auto()
    warn = auto()
    info = auto()
    debug = auto()


class QLogHandler(logging.Handler):
    """A simple log handler that supports logging in TextEdit"""

    COLORS = {
        logging.ERROR: QtGui.QColor('red'),
        logging.WARNING: QtGui.QColor('orange'),
        logging.INFO: QtGui.QColor('green'),
        logging.DEBUG: QtGui.QColor('gray'),
    }

    def __init__(self, parent):
        super().__init__()
        self.widget = QtWidgets.QTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        msg = self.format(record)
        clr = self.COLORS.get(record.levelno, QtGui.QColor('black'))
        self.widget.setTextColor(clr)
        self.widget.append(msg)
        self.widget.verticalScrollBar().setValue(
            self.widget.verticalScrollBar().maximum()
        )


class LogWidget(QtWidgets.QWidget):
    """
    A simple logger widget. Uses QLogHandler as handler.
    The handler has the actual widget that is used to display the logs.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        # set up the graphical handler
        fmt = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s\n" +
                "    %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            )
        logTextBox = QLogHandler(self)
        logTextBox.setFormatter(fmt)

        # make the widget
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(logTextBox.widget)
        self.setLayout(layout)

        # configure the logger. delete pre-existing graphical handler.
        self.logger = logging.getLogger('instrumentserver')
        for h in self.logger.handlers:
            if isinstance(h, QLogHandler):
                self.logger.removeHandler(h)
                h.widget.deleteLater()
                del h

        self.logger.addHandler(logTextBox)


def setupLogging(level=logging.INFO, addStreamHandler=True,
                  name='instrumentserver'):
    """Setting up logging, incl adding a custom handler"""

    print(f'Setting up logging for {name} ...')
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if addStreamHandler:
        for h in logger.handlers:
            if isinstance(h, logging.StreamHandler):
                logger.removeHandler(h)
                del h

        fmt = logging.Formatter(
            "[%(asctime)s] [%(name)s: %(levelname)s] %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        streamHandler = logging.StreamHandler(sys.stderr)
        streamHandler.setFormatter(fmt)
        logger.addHandler(streamHandler)


def logger(name='instrumentserver'):
    """get the (root) logger for the package"""
    return logging.getLogger(name)


def log(logger, message, level):
    """simple wrapper to log messages.

    useful when the log level is a variable.
    """
    logFuncs = {
        LogLevels.error: logger.error,
        LogLevels.warn: logger.warning,
        LogLevels.info: logger.info,
        LogLevels.debug: logger.debug,
    }
    logFuncs[level](message)
