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
    'dummy_vna',
    'instrumentserver.testing.dummy_instruments.rf.ResonatorResponse',

)

dummy_multichan = ins_cli.find_or_create_instrument(
    'dummy_multichan',
    'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule',

)

pm = ins_cli.find_or_create_instrument(
    'pm',
    'instrumentserver.params.ParameterManager',
)


#%% save the state
saveParamsToFile([pm], os.path.abspath('./parameters.json'))


#%% load pm settings from file
pm.fromFile(os.path.abspath('./parameters.json'))
