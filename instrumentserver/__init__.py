import sys
import os
import logging
import json

from qtpy import QtGui, QtCore, QtWidgets


def getInstrumentserverPath(*subfolder: str) -> str:
    """get the absolute path of the instrumentserver module

    by specifying a subfolder, get the absolute path of that.

    :example:

        >>> getInstrumentserverPath('foo', 'bar')
        /path/to/instrumentserver/foo/bar
    """
    path = os.path.split(__file__)[0]
    return os.path.join(path, *subfolder)


PARAMS_SCHEMA_PATH = os.path.join(getInstrumentserverPath('schemas'),
                                  'parameters.json')

DEFAULT_PORT = 5555

with open(PARAMS_SCHEMA_PATH) as f:
    paramDictSchema = json.load(f)

from .log import setupLogging, logger

from .client import Client
InstrumentClient = Client