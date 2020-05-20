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

from virtualParameter import instrumentSetting

class fakeVNA(Instrument): 
    
    def __init__(self, name: str, **kwargs) -> None:
        
        super().__init__(name, **kwargs)
        
        self.add_parameter("fstart", 
                           set_cmd = None,
                           get_cmd = None,
                           unit = 'Hz'
                           )
        self.add_parameter("fstop", 
                           set_cmd = None,
                           get_cmd = None,
                           unit = 'Hz'
                           )
        self.add_parameter("IFBW", 
                           set_cmd = None,
                           get_cmd = None,
                           unit = 'Hz'
                           )
        self.fstart.set(6e9)
        self.fstop.set(8e9)
        self.IFBW.set(3e3)
    
    def get_Trace(self): 
        num_points = 100
        return(np.random.random(100))
        
