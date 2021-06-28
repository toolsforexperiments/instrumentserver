import os
import argparse
import logging
import importlib.util


from . import QtWidgets, QtCore
from .log import setupLogging
from .server.application import startServerGuiApplication
from .server.core import startServer
from bokeh.server.server import Server as BokehServer
from .dashboard.dashboard import DashboardClass
from .dashboard.logger import ParameterLogger
from typing import Dict


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


def bokehDashboard(config_dict: Dict = None) -> None:
    # Check if the dashboard is being open by itself or with the logger
    if config_dict is None:
        parser = argparse.ArgumentParser(description='Starting the instrumentserver-dashboard')

        parser.add_argument("--config_location", default=os.path.abspath("instrumentserver-dashboard-cfg.py"))

        args = parser.parse_args()

        spec = importlib.util.spec_from_file_location("instrumentserver-dashboard-cfg", args.config_location)
        foo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(foo)

        # loading the global variables and getting the list of allowed addresses
        dashboard = DashboardClass(foo.config)
    else:
        dashboard = DashboardClass(config_dict)

    # loading a bokeh Server object and starting it
    dashboard_server = BokehServer(dashboard.dashboard, allow_websocket_origin=dashboard.ips)
    dashboard_server.start()

    # actually starting the process
    dashboard_server.io_loop.add_callback(dashboard_server.show, "/")
    dashboard_server.io_loop.start()


def parameterLogger() -> None:
    parser = argparse.ArgumentParser(description='Starting the instrumentserver-logger')

    parser.add_argument("--config_location", default=os.path.abspath("instrumentserver-dashboard-cfg.py"))

    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("instrumentserver-dashboard-cfg", args.config_location)
    foo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(foo)

    # create the logger
    parameter_logger = ParameterLogger(foo.config)

    # run the logger
    parameter_logger.run_logger()


def loggerAndDashboard() -> None:
    parser = argparse.ArgumentParser(description='Starting the instrumentserver-logger and instrumentserver-dashboard')

    parser.add_argument("--config_location", default=os.path.abspath("instrumentserver-dashboard-cfg.py"))

    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("instrumentserver-dashboard-cfg", args.config_location)
    foo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(foo)

    # create the separate thread
    thread = QtCore.QThread()

    # create the logger
    parameter_logger = ParameterLogger(foo.config)

    # move the logger into the new thread
    parameter_logger.moveToThread(thread)

    # start the thread
    thread.started.connect(parameter_logger.run_logger)
    thread.start()

    bokehDashboard(foo.config)

