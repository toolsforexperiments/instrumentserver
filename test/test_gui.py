import qcodes as qc
from qcodes import Parameter, Station, validators, Instrument, find_or_create_instrument

from instrumentserver import setupLogging, servergui, QtWidgets
from instrumentserver.serialize import (
    toParamDict, fromParamDict, toDataFrame,
    saveParamsToFile, loadParamsFromFile
)


def make_station():
    from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse
    dummy_vna = ResonatorResponse('dummy_vna')
    dummy_vna.start_frequency(4.9e9)
    dummy_vna.stop_frequency(5.1e9)
    current_sample = Parameter('current_sample', set_cmd=None,
                               initial_value='testsample')
    station = Station(dummy_vna, current_sample)
    return station


def main():
    station = make_station()
    app = QtWidgets.QApplication([])
    server = servergui(station)
    return app.exec_()


if __name__ == '__main__':
    main()
