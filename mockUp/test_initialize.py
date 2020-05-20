# -*- coding: utf-8 -*-
"""
Ryan Kaufman

05/18/2020

Goal: to lay out needed function calls, classes, 
and structures needed to perform a measurement in a way that is
compatible with the instrumentserver
"""


# Initialization
'''
This section of a measurement grabs instruments from the instrument server
in the real code, but here it will grab my 2 dummy instruments and load their 
current settings

Questions: 
    -how to get around appending path?
'''

import sys
sys.path.insert(0,'..')
from instrumentserver import serialize
from fakeVNA import fakeVNA
from fakeCS import fakeCS
from processData import dataProcess

from time import sleep, time
import numpy as np
import qcodes as qc
from qcodes import (Instrument, VisaInstrument,
                    ManualParameter, MultiParameter,
                    validators as vals)
from qcodes.instrument.channel import InstrumentChannel


mockup = qc.Station()

VNA = fakeVNA("VNA")
CS = fakeCS("CS")

mockup.add_component(VNA)
mockup.add_component(CS)

cwd = "D://Data//"
filename = "demo_5_20_2020"
filepath = cwd+filename

dirInfo = {"cwd": cwd,
           "peopleName": "Pinlei, Ryan",
           "projectName": "SNAIL",
           "msmtName": "FluxSweep"}

#saving previous settings
serialize.saveParamsToFile(mockup, filepath+"_initial_parameters") 