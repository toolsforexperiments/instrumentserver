# -*- coding: utf-8 -*-

import logging
from pprint import pprint

from qcodes import Instrument

from instrumentserver.server import *
from instrumentserver.server.core import InstrumentCreationSpec
from instrumentserver.client import *
from instrumentserver import log


# log.setupLogging(addStreamHandler=True, streamHandlerLevel=logging.DEBUG)
# logger = log.logger('instrumentserver')
# logger.setLevel(logging.DEBUG)


#%% shut down the server
with Client() as cli:
    cli.ask('SHUTDOWN')


#%% create vna instrument in server
Instrument.close_all()
with Client() as cli:
    dummy_vna = cli.create_instrument(
        'instrumentserver.testing.dummy_instruments.rf.ResonatorResponse',
        'dummy_vna'
    )


#%% Close an instrument
with Client() as cli:
    cli.close_instrument('dummy_vna')


#%% get instruments from server
with Client() as cli:
    pprint(cli.list_instruments())


#%% get the snapshot from the station
with Client() as cli:
    snap = cli.call('snapshot')
pprint(snap)


#%% multichannel instrument

# with this construction we can keep the connection open.
# probably this is something to run in an init script if we want to keep
# the connection open.
Instrument.close_all()
cli = Client()
dummy_multichan = cli.create_instrument(
    'instrumentserver.testing.dummy_instruments.rf.DummyInstrumentWithSubmodule',
    'dummy_multichan',
)
