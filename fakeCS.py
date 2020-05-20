# -*- coding: utf-8 -*-
"""
Created on Wed May 20 05:20:35 2020

@author: Ryan K
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

class fakeCS(Instrument): 
    
    def __init__(self, name: str, **kwargs) -> None:
        
        super().__init__(name, **kwargs)
        
        self.add_parameter("current", 
                           set_cmd = None,
                           get_cmd = None,
                           unit = 'A'
                           )
        self.current.set(0)
