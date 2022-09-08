from instrumentserver.client import Client as InstrumentClient

cli = InstrumentClient()


instrument = cli.get_instrument('test')

cli.setParameters({'test.param3': {'value': 31}})
