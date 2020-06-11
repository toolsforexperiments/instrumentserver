# -*- coding: utf-8 -*-
"""
Created on Mon May 18 11:58:28 2020

@author: rkauf
"""

import numpy as np

from time import sleep, time
import numpy as np
import qcodes as qc
from qcodes import (Instrument, VisaInstrument,
                    ManualParameter, MultiParameter,
                    validators as vals)
from qcodes.instrument.channel import InstrumentChannel

class fakeVNA(Instrument): 
    
    def __init__(self, name: str, **kwargs) -> None:
        
        super().__init__(name, **kwargs)
        
        self.add_parameter("fstart", 
                           set_cmd = None,
                           get_cmd = None,
                           initial_value = 6e9,
                           unit = 'Hz'
                           )
        self.add_parameter("fstop", 
                           set_cmd = None,
                           get_cmd = None,
                           initial_value = 8e9,
                           unit = 'Hz'
                           )
        self.add_parameter("IFBW", 
                           set_cmd = None,
                           get_cmd = None,
                           initial_value = 3e3,
                           unit = 'Hz'
                           )
        self.add_parameter("num_points", 
                           set_cmd = None, 
                           get_cmd = None, 
                           initial_value = 1609
                           )
    def frequency(self): 
        return(np.linspace(self.fstart(),self.fstop(),self.num_points()))
    
    def get_trace(self): 
        return(np.random.random(self.num_points()))
        
