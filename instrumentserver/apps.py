import os
import argparse
import logging

from . import QtWidgets, QtCore
from .log import setupLogging
from .server.application import startServerGuiApplication
from .server.core import startServer
from .client import Client
from .gui import widgetDialog
from .gui.instruments import ParameterManagerGui

setupLogging(addStreamHandler=True,
             logFile=os.path.abspath('instrumentserver.log'))
logger = logging.getLogger('instrumentserver')
logger.setLevel(logging.DEBUG)


def server(port, user_shutdown):
    app = QtCore.QCoreApplication([])
    server, thread = startServer(port, user_shutdown)
    thread.finished.connect(app.quit)
    return app.exec_()


def serverWithGui(port):
    app = QtWidgets.QApplication([])
    window = startServerGuiApplication(port)
    return app.exec_()


def serverScript() -> None:
    parser = argparse.ArgumentParser(description='Starting the instrumentserver')
    parser.add_argument("--port", default=5555)
    parser.add_argument("--gui", default=True)
    parser.add_argument("--allow_user_shutdown", default=False)
    args = parser.parse_args()

    if args.gui:
        serverWithGui(args.port)
    else:
        server(args.port, args.allow_user_shutdown)

def parameterManagerScript() -> None:
    parser = argparse.ArgumentParser(description='Starting a parameter manager instrument GUI')
    parser.add_argument("--name", default="parameter_manager")
    parser.add_argument("--port", default=5555)
    args = parser.parse_args()

    app = QtWidgets.QApplication([])

    # open a client to a server using default address (localhost) and port.
    cli = Client(port=args.port)

    if args.name in cli.list_instruments():
        pm = cli.get_instrument(args.name)
    else:
        pm = cli.create_instrument(
            'instrumentserver.params.ParameterManager', args.name)
        pm.fromFile()

    _ = widgetDialog(ParameterManagerGui(pm))
    app.exec_()
