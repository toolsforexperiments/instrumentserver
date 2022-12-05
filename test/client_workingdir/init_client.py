# -*- coding: utf-8 -*-

#%% Imports
import os

from qcodes import Instrument
from instrumentserver.client import Client
from instrumentserver.serialize import saveParamsToFile
from instrumentserver.client import ProxyInstrument


#%% Create all my instruments
Instrument.close_all()
ins_cli = Client()
dummy_vna = ins_cli.find_or_create_instrument(
    'instrumentserver.testing.dummy_instruments.rf.ResonatorResponse',
    'dummy_vna'
)

dummy_multichan = ins_cli.find_or_create_instrument(
    'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule',
    'dummy_multichan',
)

pm = ins_cli.find_or_create_instrument(
    'instrumentserver.params.ParameterManager',
    'pm',
)


#%% save the state
saveParamsToFile([pm], os.path.abspath('./parameters.json'))


#%% load pm settings from file
pm.fromFile(os.path.abspath('./parameters.json'))
