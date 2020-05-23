# -*- coding: utf-8 -*-

import logging
from pprint import pprint

from qcodes import Station, Instrument

from instrumentserver.server.core import (
    Operation, ServerInstruction, InstrumentCreationSpec)

from instrumentserver.client import sendRequest
from instrumentserver import log


log.setupLogging(addStreamHandler=True, streamHandlerLevel=logging.DEBUG)
logger = log.logger('instrumentserver')
logger.setLevel(logging.DEBUG)


#%% set up a simple station
Instrument.close_all()
from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse, FluxControl
vna = ResonatorResponse('vna')
flux = FluxControl('flux', vna)

station = Station(vna, flux)

#%% get instruments from server
req = ServerInstruction(
    operation=Operation.get_existing_instruments,
    )
sendRequest(req)


#%% create vna instrument in server
req = ServerInstruction(
    operation=Operation.create_instrument,
    create_instrument_spec=InstrumentCreationSpec(
            instrument_class='instrumentserver.testing.dummy_instruments.rf.ResonatorResponse',
            args=('dummy_vna',)
        )
    )
sendRequest(req)