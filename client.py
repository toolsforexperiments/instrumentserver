import os
import argparse
import logging

from instrumentserver import setupLogging, logger, QtWidgets
from instrumentserver.log import LogWidget
from instrumentserver.client import QtClient
from instrumentserver.client.application import InstrumentClientMainWindow
from instrumentserver.gui.instruments import ParameterManagerGui


setupLogging(addStreamHandler=True,
             logFile=os.path.abspath('instrumentclient.log'))
log = logger()
log.setLevel(logging.DEBUG)


def setup_log(win: InstrumentClientMainWindow):
    w = LogWidget()
    win.addWidget(w, 'Log', visible=False)


def setup_pm(win: InstrumentClientMainWindow):
    pm = win.client.find_or_create_instrument(
        'pm',
        'instrumentserver.params.ParameterManager',
    )
    w = ParameterManagerGui(pm)
    win.addWidget(w, name="PM: "+pm.name)


def main():
    app = QtWidgets.QApplication([])
    cli = QtClient()
    mainwindow = InstrumentClientMainWindow(cli)

    setup_pm(mainwindow)
    setup_log(mainwindow)

    mainwindow.show()
    return app.exec_()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Client options')
    args = parser.parse_args()
    main()




