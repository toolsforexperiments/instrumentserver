from qcodes import Station, Instrument
from qcodes.utils import validators

from instrumentserver import QtWidgets

from instrumentserver.gui import widgetDialog
from instrumentserver.param_manager import ParameterManager
from instrumentserver.gui.instruments import ParameterManagerGui


def make_station():
    Instrument.close_all()

    pm = ParameterManager('pm')
    station = Station(pm)

    pm.add('sample_name', 'qubit_test-5')
    pm.add('readout.pulse_length', 1000, unit='ns', vals=validators.Ints())
    pm.add('readout.envelope', 'envelope_file.npz')
    pm.add('readout.n_repetitions', 1000)
    pm.add('qubit.frequency', 5.678e9, unit='Hz')
    pm.add('qubit.pi_pulse.len', 20, unit='ns')
    pm.add('qubit.pi_pulse.amp', 126, unit='DAC units')

    return station

def main():
    station = make_station()
    app = QtWidgets.QApplication([])

    dialog = widgetDialog(
        ParameterManagerGui(station.pm)
    )

    return app.exec_()


if __name__ == '__main__':
    main()
