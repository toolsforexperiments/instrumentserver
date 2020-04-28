# -*- coding: utf-8 -*-
"""
Created on Fri Apr 10 21:52:09 2020

@author: Chao
"""

import os
from types import MethodType
import json
from functools import partial
from time import sleep

import matplotlib.pyplot as plt
import numpy as np
import zmq
import qcodes as qc
from qcodes import (
    Measurement,
    experiments,
    initialise_database,
    initialise_or_create_database_at,
    load_by_guid,
    load_by_run_spec,
    load_experiment,
    load_last_experiment,
    load_or_create_experiment,
    new_experiment,
)
from qcodes.dataset.plotting import plot_dataset
from qcodes.logger.logger import start_all_logging
from qcodes.tests.instrument_mocks import DummyInstrument
from qcodes.utils.validators import Validator, Numbers, Anything, Strings
from qcodes.instrument import parameter

from instrumentserver.interpreters import instructionDict_to_instrumentCall 


#  Create a dummy station with a dummy instruemnt 'yoko'
start_all_logging()

station = qc.Station()
yoko = DummyInstrument('yoko')

# a function added using the old style 'add_function' method
def multiply_addfunc( a : int, b : int, c:int=3):
    '''
    multiply_addfunc docs
    '''
    print (a*b*c)
    return a*b*c
yoko.add_function(
    'multiply_addfunc', 
    call_cmd = multiply_addfunc, 
    args = [Numbers(1,5), Numbers(), Numbers()],
    docstring = multiply_addfunc.__doc__
    )


# functions added to instrument class as bound methods
def multiply_method(self,  a : int, b : int, c:int=3):
    '''
    multiply_method docs
    '''
    print (a*b*c*self.current())
    return a*b*c*self.current()
yoko.multiply_method = MethodType(multiply_method, yoko)

def sum_method(self,  a : int, b : int, c:int=3):
    '''
    sum_method docs
    '''
    print (a+b+c+self.current())
    return a+b+c+self.current()
yoko.sum_method = MethodType(sum_method, yoko)

def reset_method(self):
    '''
    reset_method docs
    '''
    print ('reset')
    self.current(0)
yoko.reset_method = MethodType(reset_method, yoko)



# add parameters
yoko.add_parameter(
    'operation_mode', 
    vals =  Strings() 
    )
yoko.add_parameter(
    'current', 
    unit = 'mA',
    set_cmd = None,
    get_cmd = None,
    initial_value = 1,
    # step = 0.1,
    vals =  Numbers(-20,20)  
    )

test_param = parameter.Parameter(
                                 name = 'test_param',
                                 get_cmd = None,
                                 set_cmd = None
                                )
station.add_component(yoko)
station.add_component(test_param)

yoko_ss = station.snapshot()['instruments']['yoko']
current_ss = yoko_ss['parameters']['current']


# setup a zmq server
context = zmq.Context()
socket = context.socket(zmq.REP)
socket.bind("tcp://*:5555")

while True:
    #  Wait for request from client
    received_dict = socket.recv_json()
    print("Received instruction: "  + received_dict['operation'])
    #  find which instrument client is communicating
    respondes = instructionDict_to_instrumentCall(station, received_dict)    
    #  Send reply back to client
    socket.send_json(respondes)


