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
import inspect

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
from qcodes.tests.instrument_mocks import DummyInstrument, DummyChannelInstrument
from qcodes.utils.validators import Validator, Numbers, Anything, Strings, Arrays
from qcodes.instrument import parameter

from instrumentserver.interpreters import instructionDict_to_instrumentCall 
from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse

#  Create a dummy station with a dummy instruemnt 'yoko'
start_all_logging()

station = qc.Station()
yoko = DummyInstrument('yoko')


# a function added using the old style 'add_function' method
def multiply_addfunc( a : int, b : int, c:int=3):
    print (a*b*c)
    return a*b*c
yoko.add_function(
    'multiply_addfunc', 
    call_cmd = multiply_addfunc, 
    args = [Numbers(), Numbers(), Numbers()]
    )


# a function added to instrument class as bound methods
def multiply_method(self,  a : int, b : int, c:int=3, *args, **kwargs):
    '''
    multiply_method
    '''
    print (a*b*c*self.current())
    return a*b*c*self.current()
yoko.multiply_method = MethodType(multiply_method, yoko)


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
mydummy = DummyChannelInstrument('mydummy')
dummy_vna = ResonatorResponse('dummy_vna')


station.add_component(mydummy)
station.add_component(yoko)
station.add_component(dummy_vna)
station.add_component(test_param)

yoko_ss = station.snapshot()['instruments']['yoko']
current_ss = yoko_ss['parameters']['current']

inspect.getmembers(yoko)

def get_instrument_functions(instrument):
    methods = set(dir(instrument))
    base_methods = (dir(base) for base in instrument.__class__.__bases__)
    unique_methods = methods.difference(*base_methods)
    functions = [method for method in unique_methods if callable(getattr(instrument, method))]
    return list(functions)

print(get_instrument_functions(yoko))

inspect.getfullargspec(yoko.multiply_addfunc)
inspect.getfullargspec(yoko.multiply_method)