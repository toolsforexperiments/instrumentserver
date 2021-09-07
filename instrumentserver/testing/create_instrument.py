from instrumentserver.client import Client as InstrumentClient
"""
Script used to create an instrument in the instrument server used for developing the dashboard/logger.
"""


# used for testing, the instruments should be already created for the dashboard to work
cli = InstrumentClient()

if 'test' in cli.list_instruments():
    instrument = cli.get_instrument('test')
else:
    instrument = cli.create_instrument(
        'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentRandomNumber',
        'test')

