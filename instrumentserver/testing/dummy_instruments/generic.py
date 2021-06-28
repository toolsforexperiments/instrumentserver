from typing import List

from qcodes import Instrument
from qcodes.utils import validators
import numpy as np


class DummyChannel(Instrument):
    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.add_parameter('ch0',
                           set_cmd=None,
                           vals=validators.Numbers(0, 1),
                           initial_value=0)

        self.add_parameter('ch1', unit='v',
                           set_cmd=None,
                           vals=validators.Numbers(-1, 1),
                           initial_value=1)


class DummyInstrumentWithSubmodule(Instrument):
    """A dummy instrument with submodules"""

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self.add_parameter('param0',
                           set_cmd=None,
                           vals=validators.Numbers(0, 1),
                           initial_value=0)

        self.add_parameter('param1', unit='v',
                           set_cmd=None,
                           vals=validators.Numbers(-1, 1),
                           initial_value=1)
        for chan_name in ('A', 'B', 'C'):
            channel = DummyChannel('Chan{}'.format(chan_name))
            self.add_submodule(chan_name, channel)

    def test_func(self, a, b, *args, c: List[int] = [10, 11], **kwargs):
        return a, b, args[0], c, kwargs['d'], self.param0()

class DummyInstrumentRandomNumber(Instrument):
    """A dummy instrument with a few parameters that have random numbers generated on demand"""

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self.add_parameter('param0',
                           set_cmd=None,
                           vals=validators.Numbers(1, 10),
                           initial_value=1)

        self.add_parameter('param1',
                           set_cmd=None,
                           vals=validators.Numbers(10, 20),
                           initial_value=10)

        self.add_parameter('param2',
                           set_cmd=None,
                           vals=validators.Numbers(20, 30),
                           initial_value=20)

        self.add_parameter('param3',
                           set_cmd=None,
                           vals=validators.Numbers(30, 40),
                           initial_value=30)

        self.add_parameter('param4',
                           set_cmd=None,
                           vals=validators.Numbers(40, 50),
                           initial_value=40)

    def generate_data(self, name: str):

        if name == 'param0':
            self.parameters[name].set(np.random.randint(1, 10))
        if name == 'param1':
            self.parameters[name].set(np.random.randint(10, 20))
        if name == 'param2':
            self.parameters[name].set(np.random.randint(20, 30))
        if name == 'param3':
            self.parameters[name].set(np.random.randint(30, 40))
        if name == 'param4':
            self.parameters[name].set(np.random.randint(40, 50))

    def get(self, param_name):
        self.generate_data(param_name)
        super.get(param_name)