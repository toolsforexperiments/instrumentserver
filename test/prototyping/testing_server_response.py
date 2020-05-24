# -*- coding: utf-8 -*-

import logging
from pprint import pprint
import dataclasses

from qcodes import Station, Instrument

from instrumentserver.server.core import (
    Operation, ServerInstruction, InstrumentCreationSpec, CallSpec,
    ParameterBluePrint, bluePrintFromParameter,
    InstrumentModuleBluePrint, bluePrintFromInstrumentModule)

from instrumentserver.client import sendRequest
from instrumentserver import log


log.setupLogging(addStreamHandler=True, streamHandlerLevel=logging.DEBUG)
logger = log.logger('instrumentserver')
logger.setLevel(logging.DEBUG)


#%% TEST: set up a simple station
Instrument.close_all()
from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse, FluxControl
vna = ResonatorResponse('vna')
flux = FluxControl('flux', vna)

station = Station(vna, flux)

#%% TEST: get the blueprint of a local instrument
bp = bluePrintFromInstrumentModule('vna', vna)
print(bp)


#%% shut down the server
sendRequest('SHUTDOWN')


#%% get instruments from server
req = ServerInstruction(
    operation=Operation.get_existing_instruments,
    )
ret = sendRequest(req)


#%% create vna instrument in server
req = ServerInstruction(
    operation=Operation.create_instrument,
    create_instrument_spec=InstrumentCreationSpec(
            instrument_class='instrumentserver.testing.dummy_instruments.rf.ResonatorResponse',
            args=('dummy_vna',)
        )
    )
ret = sendRequest(req)


#%% set an instrument parameter
req = ServerInstruction(
    operation=Operation.call,
    call_spec=CallSpec(
            target="dummy_vna.start_frequency",
            args=(4e9,)
        )
    )
ret = sendRequest(req)


#%% get an instrument parameter
req = ServerInstruction(
    operation=Operation.call,
    call_spec=CallSpec(
            target="dummy_vna.start_frequency",
        )
    )
ret = sendRequest(req)

#%% get the snapshot from the station
req = ServerInstruction(
    operation=Operation.call,
    call_spec=CallSpec(
            target="snapshot",
        )
    )
ret = sendRequest(req)
