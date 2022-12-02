
# import stuff here

from instrumentserver.testing.dummy_instruments.generic import DummyInstrumentRandomNumber
import qcodes

global station




dummy_instrumet = qcodes.find_or_create_instrument(
    instrument_class=DummyInstrumentRandomNumber,
    name='test'
)
station.add_component(dummy_instrumet)
