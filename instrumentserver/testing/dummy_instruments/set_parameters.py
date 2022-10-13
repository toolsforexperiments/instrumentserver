from instrumentserver.client import Client as InstrumentClient
from time import sleep as sleep
cli = InstrumentClient()
from numpy.random import randint

instrument = cli.get_instrument('test')

for i in range(30):
    val = randint(30, 40)
    cli.setParameters({'test.param3': {'value': val}})
    sleep(3.0)
