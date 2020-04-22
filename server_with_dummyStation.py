# -*- coding: utf-8 -*-
"""
Created on Fri Apr 10 21:52:09 2020

@author: Chao
"""

import os
import json
from functools import partial
from time import sleep

import matplotlib.pyplot as plt
import numpy as np
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

start_all_logging()


station = qc.Station()
# station.snapshot()
yoko = DummyInstrument('yoko')


def dum_multiply( a, b ):
    print (a*b)
    return a*b
yoko.add_function(
    'dum_multiply', 
    call_cmd = dum_multiply, 
    args = [Numbers(), Numbers()]
    )

yoko.add_parameter(
    'operation_mode', 
    vals =  Strings() 
    )
yoko.add_parameter(
    'current', 
    unit = 'mA',
    set_cmd = None,
    get_cmd = None,
    step = 0.1,
    vals =  Numbers(-20,20)  
    )

station.add_component(yoko)

yoko_ss = station.snapshot()['instruments']['yoko']
current_ss = yoko_ss['parameters']['current']


with open('dummyYoko.json', 'w') as json_file:
  json.dump(yoko_ss, json_file)

yoko.current.vals.valid_values
