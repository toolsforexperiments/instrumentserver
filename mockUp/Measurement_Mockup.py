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
from instrumentserver import serialize
import os
import argparse
import logging

from instrumentserver import setupLogging, logger, QtWidgets
from instrumentserver.log import LogWidget
from instrumentserver.client import QtClient
from instrumentserver.client.application import InstrumentClientMainWindow
from instrumentserver.gui.instruments import ParameterManagerGui
from instrumentserver import client
from instrumentserver.client.proxy import Client
from qcodes import Instrument
import instrumentserver
import _thread
from time import sleep, time
import numpy as np
import qcodes as qc
from qcodes import (Instrument, VisaInstrument,
                    ManualParameter, MultiParameter,
                    validators as vals)
from qcodes.instrument.channel import InstrumentChannel

from ini

mockup.add_component(VNA)
mockup.add_component(CS)

cwd = "C:/Users/Ryan K/Documents/GitHub/instrumentserver/mockUp/demo_files/"
filename = "demo_5_20_2020"
filepath = cwd+filename

dirInfo = {"cwd": cwd,
           "peopleName": "Pinlei, Ryan",
           "projectName": "SNAIL",
           "msmtName": "FluxSweep"}

#saving previous settings
serialize.saveParamsToFile(mockup, filepath+"_initial_parameters") 

# Configuration
'''
This section takes input (that here is just manually put in the script)
and loads it into the instrument
Questions: 
    - how might we automatically load in options that the user can change? 
    - - serialize gives list of params
'''
par_dict = serialize.toParamDict(mockup)

print("Available Parameters: ")
for key in par_dict.keys():
    print(key)
#This would be the section for a GUI, but here I'll just manually set some

VNA.fstart.set(3e9)
VNA.fstop.set(4e9)
CS.current.set(0)

#TODO: GUI for initial setting of parameters

#saving initial settings
serialize.saveParamsToFile(mockup, filepath+"_initial_set_parameters") 


# Control 
'''
This section takes loose variables and generates sweep variables that are
fed into the instruments to take data
Questions: 
    - should we use ArrayParameters for sweep variables?
'''
def dataLine(curr): 
    CS.current.set(curr)
    data = VNA.get_Trace()
    return data

data = []
curr_arr = np.linspace(0,10e-3,100)
for curr in curr_arr: 
    data.append(dataLine(curr))



# # Storage
'''
This section takes the data which is actively stored in the kernel and 
saves it into a file
Questions: 
    - do we want to save/overwrite as the script is taking data? 
       
Takes: 
    data[NxM array]
    parameters: 
        -dictionary
    cwd
'''

sv = dataProcess(dirInfo, "_data", data, par_dict)
sv.save()

#Cleanup for restarting

mockup.close_all_registered_instruments()











