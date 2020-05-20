import numpy as np
from qcodes import Station, Instrument
from qcodes.utils import validators

from instrumentserver import QtWidgets
from instrumentserver.gui import widgetDialog
from instrumentserver.params import ParameterManager
from instrumentserver.gui.instruments import ParameterManagerGui


def make_station():
    Instrument.close_all()

    pm = ParameterManager('pm')
    station = Station(pm)

    pm.add('sample_name', 'qubit_test-5', vals=validators.Strings())

    pm.add('readout.pulse_length', 1000, unit='ns', vals=validators.Ints())
    pm.add('readout.envelope', 'envelope_file.npz', vals=validators.Strings())
    pm.add('readout.n_repetitions', 1000, vals=validators.Ints())
    pm.add('readout.use_envelope', True, vals=validators.Bool())

    pm.add('qubit.frequency', 5.678e9, unit='Hz', vals=validators.Numbers())
    pm.add('qubit.pi_pulse.len', 20, unit='ns', vals=validators.Ints())
    pm.add('qubit.pi_pulse.amp', 126, unit='DAC units', vals=validators.Ints())

    pm.add('morestuff.a_sequence', [])
    pm.add('morestuff.a_complex_number', 0+0j, vals=validators.ComplexNumbers())

    return station

def main():
    station = make_station()
    app = QtWidgets.QApplication([])

    dialog = widgetDialog(
        ParameterManagerGui(station.pm,
                            makeAvailable=[('np', np)])
    )

    return app.exec_()


if __name__ == '__main__':
    main()
