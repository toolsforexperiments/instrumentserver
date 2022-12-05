# -*- coding: utf-8 -*-

import logging

#%% imports
from qcodes import Instrument
from instrumentserver.server import *
from instrumentserver.client import *

# from instrumentserver import log
# log.setupLogging(addStreamHandler=True, streamHandlerLevel=logging.DEBUG)
# logger = log.logger('instrumentserver')
# logger.setLevel(logging.DEBUG)


#%% shut down the server
with Client() as cli:
    cli.ask('SHUTDOWN')


#%% create vna instrument in server
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


#%% Close an instrument
with Client() as cli:
    cli.close_instrument('dummy_vna')


#%% get instruments from server
with Client() as cli:
    pprint(cli.list_instruments())


#%% get the snapshot from the station
with Client() as cli:
    snap = cli.snapshot()
pprint(snap)
