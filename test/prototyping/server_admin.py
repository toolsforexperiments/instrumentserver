# -*- coding: utf-8 -*-


# %% imports
from pprint import pprint

from qcodes import Instrument

from instrumentserver.client import Client
from instrumentserver.server import *  # noqa: F401,F403

# from instrumentserver import log
# log.setupLogging(addStreamHandler=True, streamHandlerLevel=logging.DEBUG)
# logger = log.logger('instrumentserver')
# logger.setLevel(logging.DEBUG)


# %% shut down the server
with Client() as cli:
    cli.ask("SHUTDOWN")


# %% create vna instrument in server
Instrument.close_all()
ins_cli = Client()
dummy_vna = ins_cli.find_or_create_instrument(
    "dummy_vna",
    "instrumentserver.testing.dummy_instruments.rf.ResonatorResponse",
)

dummy_multichan = ins_cli.find_or_create_instrument(
    "dummy_multichan",
    "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule",
)

pm = ins_cli.find_or_create_instrument(
    "pm",
    "instrumentserver.params.ParameterManager",
)


# %% Close an instrument
with Client() as cli:
    cli.close_instrument("dummy_vna")


# %% get instruments from server
with Client() as cli:
    pprint(cli.list_instruments())


# %% get the snapshot from the station
with Client() as cli:
    snap = cli.get_snapshot()
pprint(snap)
