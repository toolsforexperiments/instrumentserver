from instrumentserver.client import Client as InstrumentClient

cli = InstrumentClient()


instrument = cli.get_instrument('test_name')

cli.setParameters({'test_name.param3': {'value': 31}})
