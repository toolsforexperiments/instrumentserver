# -*- coding: utf-8 -*-
"""
Created on Fri Apr 10 21:52:09 2020

@author: Chao
"""

from types import MethodType

import numpy as np
import zmq
import qcodes as qc
from instrument_mocker.dummy_gennerator import DumGen

from qcodes.logger.logger import start_all_logging
from qcodes.tests.instrument_mocks import DummyInstrument, DummyChannelInstrument
from qcodes.utils.validators import Validator, Numbers, Anything, Strings
from qcodes.instrument import parameter

from instrumentserver.interpreters import instructionDict_to_instrumentCall
from instrumentserver.base import send, recv
from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse
#  Create a dummy station with a dummy instrument 'yoko'
start_all_logging()

station = qc.Station()
yoko = DummyInstrument('yoko')


# a function added using the old style 'add_function' method
def multiply_addfunc(a: int, b: int, c: int = 3):
    """
    multiply_addfunc docs
    """
    print(a * b * c)
    return a * b * c


yoko.add_function(
    'multiply_addfunc',
    call_cmd=multiply_addfunc,
    args=[Numbers(1, 5), Numbers(), Numbers()],
    docstring=multiply_addfunc.__doc__
)


# functions added to instrument class as bound methods
def multiply_method(self, a: int, b: int, c: int = 3):
    """
    multiply_method docs
    """
    print(a * b * c * self.current())
    return a * b * c * self.current()


yoko.multiply_method = MethodType(multiply_method, yoko)


def sum_method(self, a: int, b: int, c: int = 3):
    """
    sum_method docs
    """
    print(a + b + c + self.current())
    return a + b + c + self.current()


yoko.sum_method = MethodType(sum_method, yoko)


def reset_method(self):
    """
    reset_method docs
    """
    print('reset')
    self.current(0)


yoko.reset_method = MethodType(reset_method, yoko)

# add parameters
yoko.add_parameter(
    'operation_mode',
    vals=Strings()
)
yoko.add_parameter(
    'current',
    unit='mA',
    set_cmd=None,
    get_cmd=None,
    initial_value=1,
    # step = 0.1,
    vals=Numbers(-20, 20)
)

test_param = parameter.Parameter(
    name='test_param',
    get_cmd=None,
    set_cmd=None
)

mydummy = DummyChannelInstrument('mydummy')
gen = DumGen('gen', 'dum_address')
dummy_vna = ResonatorResponse('dummy_vna')

station.add_component(yoko)
station.add_component(test_param)
station.add_component(mydummy)
station.add_component(gen)
station.add_component(dummy_vna)

# setup a zmq server
context = zmq.Context()
socket = context.socket(zmq.REP)
socket.bind("tcp://*:5555")

while True:
    #  Wait for request from client
    received_dict = recv(socket)
    print("Received instruction: " + received_dict['operation'])
    response = instructionDict_to_instrumentCall(station, received_dict)
    #  Send reply back to client
    send(socket, response)
