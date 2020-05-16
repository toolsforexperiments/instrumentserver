# -*- coding: utf-8 -*-
'''
a dummy generator driver for testing the instruemnt server
'''
from qcodes import Instrument
from qcodes.utils.validators import Numbers, Bool
import numpy as np

class DumGen(Instrument):
    """
    This is a dummy generator driver for testing the instruemnt server
    """

    def __init__(self, name, address, **kwargs):
        self._address = address
        super().__init__(name, **kwargs)
        self.add_parameter('power',
                           label='Power',
                           unit='dBm',
                           vals=Numbers(min_value=-20,max_value=20))

        self.add_parameter('frequency',
                           label='Frequency',
                           unit='Hz',
                           vals=Numbers(min_value=0,max_value=20e9))   
        
        self.add_parameter('phase',
                           label='phase',
                           unit='rad'
                           )

        self.add_parameter('output',
                           vals=Bool()
                            )
        self.connect_message()
        

    def sweep_freq(self,  start : float, stop : float, step:float):
        '''
        sweep frequency
        '''
        return np.arange(start, stop, step)
        

    def get_idn(self):
        IDN = {'vendor': 'dummy_vendor', 'model': 'dummy_model',
               'address': self._address, 'firmware': 'dummy_firmware'}
        return IDN

