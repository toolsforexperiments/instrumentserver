from typing import List

from qcodes import Instrument
from qcodes.utils import validators
import numpy as np
import time


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
    """A dummy instrument with submodules."""

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


class DummyInstrumentTimeout(Instrument):
    """A dummy instrument to test timeout situations."""
    def __init__(self, name: str, *args,  **kwargs):
        super().__init__(name, *args, **kwargs)

        self.random = np.random.randint(10000)

    def get_random(self):
        return self.random

    def get_random_timeout(self):
        time.sleep(10)
        return self.random

