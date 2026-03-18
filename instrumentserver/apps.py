import os
import argparse
import logging
import signal
from pathlib import Path

from . import QtWidgets, QtCore
from .log import setupLogging
from .config import loadConfig
from .server.application import startServerGuiApplication
from .server.core import startServer

from .client import Client, ClientStation
from .client.application import ClientStationGui
from .gui import widgetMainWindow
from .gui.instruments import ParameterManagerGui
from .server.pollingWorker import PollingWorker

from instrumentserver.server.application import DetachedServerGui


setupLogging(addStreamHandler=True,
             logFile=os.path.abspath('instrumentserver.log'))
logger = logging.getLogger('instrumentserver')
logger.setLevel(logging.INFO)


def server(**kwargs):
    app = QtCore.QCoreApplication([])

    # this allows us to kill the server by KeyboardInterrupt
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    server, thread = startServer(**kwargs)
    thread.finished.connect(app.quit)
    return app.exec_()


def serverWithGui(**kwargs):
    app = QtWidgets.QApplication([])
    window = startServerGuiApplication(**kwargs)
    return app.exec_()


def serverScript() -> None:
    parser = argparse.ArgumentParser(description='Starting the instrumentserver')
    parser.add_argument("-p", "--port", default=5555)
    parser.add_argument("--gui", default=True)
    parser.add_argument("--allow_user_shutdown", default=False)
    parser.add_argument("-a", "--listen_at", type=str, nargs="*",
                        help="On which network addresses we listen.")
    parser.add_argument("-i", "--init_script", default='',
                        type=str)
    parser.add_argument("-c", "--config", type=str, default='')
    args = parser.parse_args()

    # Load and process the config file if any.
    configPath = args.config

    stationConfig, serverConfig, guiConfig, tempFile, pollingRates, pollingThread, ipAddresses = None, None, None, None, None, None, None
    if configPath != '':
        # Separates the corresponding settings into the 5 necessary parts
        stationConfig, serverConfig, guiConfig, tempFile, pollingRates, ipAddresses = loadConfig(configPath)
    if pollingRates is not None and pollingRates != {}:
        pollingThread = QtCore.QThread()
        pollWorker = PollingWorker(pollingRates=pollingRates)
        pollWorker.moveToThread(pollingThread)
        pollingThread.started.connect(pollWorker.run)
        pollingThread.start()

    if args.gui == 'False':
        server(port=args.port,
               allowUserShutdown=args.allow_user_shutdown,
               addresses=args.listen_at,
               initScript=args.init_script,
               serverConfig=serverConfig,
               stationConfig=stationConfig,
               guiConfig=guiConfig,
               pollingThread=pollingThread,
               ipAddresses=ipAddresses)
    else:
        serverWithGui(port=args.port,
                      addresses=args.listen_at,
                      initScript=args.init_script,
                      serverConfig=serverConfig,
                      stationConfig=stationConfig,
                      guiConfig=guiConfig,
                      pollingThread=pollingThread,
                      ipAddresses=ipAddresses)

    # Close and delete the temporary files
    if tempFile is not None:
        tempFile.close()
        if stationConfig is not None:
            Path(stationConfig).unlink(missing_ok=True)


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
        pm = cli.find_or_create_instrument(
            args.name, 'instrumentserver.params.ParameterManager')
        pm.fromFile()
        pm.update()

    _ = widgetMainWindow(ParameterManagerGui(pm), 'Parameter Manager')
    app.exec_()


def detachedServerScript() -> None:

    parser = argparse.ArgumentParser(description='Starting a detached instance of the GUI for the server')
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=5555)
    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    window = DetachedServerGui(host=args.host, port=args.port)
    window.show()
    app.exec_()


def clientStationScript() -> None:
    parser = argparse.ArgumentParser(description='Starting a client station GUI')
    parser.add_argument("--host", default="localhost", help="Server host address")
    parser.add_argument("--port", default=5555, type=int, help="Server port")
    parser.add_argument("-c", "--config", type=str, default='', help="Path to client station config file (YAML)")
    args = parser.parse_args()

    app = QtWidgets.QApplication([])

    config_path = args.config if args.config else None
    station = ClientStation(host=args.host, port=args.port, config_path=config_path)
    window = ClientStationGui(station)
    window.show()
    app.exec_()


