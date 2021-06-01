import os
import argparse
import logging

from . import QtWidgets, QtCore
from .log import setupLogging
from .server.application import startServerGuiApplication
from .server.core import startServer
from bokeh.server.server import Server as BokehServer
from .dashboard.core import dashboard as dash

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
    parser.add_argument("--gui", default=False)
    parser.add_argument("--allow_user_shutdown", default=False)
    args = parser.parse_args()

    if args.gui:
        serverWithGui(args.port)
    else:
        server(args.port, args.allow_user_shutdown)


def bokehDashboard() -> None:
    dashboard_server = BokehServer(dash)
    dashboard_server.start()

    dashboard_server.io_loop.add_callback(dashboard_server.show, "/")
    dashboard_server.io_loop.start()
