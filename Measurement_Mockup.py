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
    
'''


import h5py 
from time import sleep, time
import numpy as np
import qcodes as qc
from qcodes import (Instrument, VisaInstrument,
                    ManualParameter, MultiParameter,
                    validators as vals)
from qcodes.instrument.channel import InstrumentChannel
from fakeVNA import fakeVNA


VNA = fakeVNA("VNA")
fCS = fakeCurrentSource("fCS")
cwd = "C:\\"
# Configuration
'''
This section takes input (that here is just manually put in the script)
and loads it into the instrument
Questions: 
'''
pardict = {
 param1: vals
 .
 .
 .
 
 
 }
loading(pardict)

# Control 
'''
This section takes loose variables and generates sweep variables that are
fed into the instruments to take data
Questions: 
    
'''
def oneVal(curr): 
    CS.set_current()
    data = VNA.get_Trace()
    return data

data = []
for curr in curr_arr: 
    data.append(oneVal(curr))
    
    .
    .
    .
    




# Storage
'''
This section takes the data which is actively stored in the kernel and 
saves it into a file
Questions: 
    - do we want to save/overwrite as the script is taking data? 
    -- yes to avoid losing it if script throws execution or kernel 
       needs to be stopped
       
Takes: 
    data[NxM array]
    parameters: 
        -dictionary
    cwd
'''