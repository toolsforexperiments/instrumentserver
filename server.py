import os
import argparse
import logging

from instrumentserver import QtWidgets, QtCore
from instrumentserver.log import setupLogging, log, LogLevels
from instrumentserver.server import startServer
# from instrumentserver.server.application import startServerGuiApplication


setupLogging(addStreamHandler=True,
             logFile=os.path.abspath('instrumentserver.log'))
logger = logging.getLogger('instrumentserver')
logger.setLevel(logging.DEBUG)

#
# def showLogMessage(msg, level=LogLevels.info):
#     log(logger, msg, level)


def server(port, user_shutdown):
    app = QtCore.QCoreApplication([])
    server, thread = startServer(port, user_shutdown)
    thread.finished.connect(app.quit)
    return app.exec_()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Starting the instrumentserver')
    parser.add_argument("--port", default=5555)
    parser.add_argument("--gui", default=False)
    parser.add_argument("--allow_user_shutdown", default=False)
    args = parser.parse_args()

    if args.gui:
        raise NotImplementedError
    else:
        server(args.port, args.allow_user_shutdown)


