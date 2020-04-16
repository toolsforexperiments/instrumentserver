import argparse
import logging

from qcodes import Parameter, Station, validators

from instrumentserver import QtGui, QtCore, QtWidgets
from instrumentserver import setupLogging, logger
from instrumentserver.server import StationServer, ServerGui, servergui

setupLogging(addStreamHandler=False)
log = logger()
log.setLevel(logging.DEBUG)


def init():
    a_property = Parameter('a_property', set_cmd=None, get_cmd=None,
                           initial_value=0)

    another_property = Parameter('another_property', set_cmd=None, get_cmd=None,
                                 initial_value='abc', vals=validators.Strings())

    station = Station(a_property, another_property)
    return station


def main(station):
    app = QtWidgets.QApplication([])
    win = servergui(station)
    return app.exec_()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Testing the server')
    parser.add_argument("--delay", help="how long to wait before reply (s)",
                        default=0)
    args = parser.parse_args()

    station = init()
    main(station)







