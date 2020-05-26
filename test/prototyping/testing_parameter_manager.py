# -*- coding: utf-8 -*-

import numpy as np
from qcodes import Station, Instrument
from qcodes.utils import validators

from instrumentserver import QtWidgets
from instrumentserver.serialize import saveParamsToFile, loadParamsFromFile
from instrumentserver.gui import widgetDialog
from instrumentserver.params import ParameterManager
from instrumentserver.gui.instruments import ParameterManagerGui


#%% instantiate PM
Instrument.close_all()
pm = ParameterManager('pm')
dialog = widgetDialog(ParameterManagerGui(pm))


#%% add some parameters
pm.add('readout.pulse_length', 1000, unit='ns', vals=validators.Ints())
pm.add('readout.envelope', 'envelope_file.npz', vals=validators.Strings())
pm.add('readout.n_repetitions', 1000, vals=validators.Ints())
pm.add('readout.use_envelope', True, vals=validators.Bool())

pm.add('qubit.frequency', 5.678e9, unit='Hz', vals=validators.Numbers())
pm.add('qubit.pi_pulse.len', 20, unit='ns', vals=validators.Ints())
pm.add('qubit.pi_pulse.amp', 126, unit='DAC units', vals=validators.Ints())

#%% save the state
saveParamsToFile([pm], './parameters.json')


#%% load pm settings from file
pm.fromFile('./parameters.json')
