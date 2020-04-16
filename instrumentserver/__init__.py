import sys
import os
import logging
from qtpy import QtGui, QtCore, QtWidgets

from .log import setupLogging, logger
from .server import servergui


def getInstrumentserverPath(*subfolder: str) -> str:
    """get the absolute path of the instrumentserver module

    by specifying a subfolder, get the absolute path of that.

    :example:

        >>> getInstrumentserverPath('foo', 'bar')
        /path/to/instrumentserver/foo/bar
    """
    path = os.path.split(__file__)[0]
    return os.path.join(path, *subfolder)
