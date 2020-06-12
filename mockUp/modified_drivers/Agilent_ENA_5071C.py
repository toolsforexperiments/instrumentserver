
# MJH 2015_10_15.. Maybe this will work??
#Additions by Alex
#average method by Erick Brindock  7/15/16
#driver rewritten by Ryan Kaufman 06/11/20 for Qcodes

from qcodes import VisaInstrument 
import visa
import types
import logging
import numpy as np
import time
#from pyvisa.visa_exceptions import VisaIOError
triggered=[False]*159 

class Agilent_ENA_5071C(VisaInstrument):
    '''
    This is the driver for the Agilent E5071C Vector Netowrk Analyzer

    Usage:
    Initialize with
    <name> = instruments.create('<name>', 'Agilent_E5071C', 
    address='<GBIP address>, reset=<bool>')
    '''
    
    def __init__(self, name, address, **kwargs):
        '''
        Initializes the Agilent_E5071C, and communicates with the wrapper.

        Input:
          name (string)    : name of the instrument
          address (string) : GPIB address
          reset (bool)     : resets to default values, default=False
        '''
        logging.info(__name__ + ' : Initializing instrument Agilent_E5071C')
        super().__init__(name, address, terminator = '\n', **kwargs)

        # Add in parameters
        self.add_parameter('power', 
                           get_cmd = ":SOUR1:POW?", 
                           set_cmd = ":SOUR1:POW {:f}", 
                           unit = 'dBm', 
                           get_parser = float)
        self.add_parameter('power_start',
                           get_cmd = ':SOUR1:POW:STAR?'
                           set_cmd = ':SOUR1:POW:STAR {:s}'
                           unit = 'dBm'
                           )
        self.add_parameter('averaging', 
                           get_cmd = ':SENS1:AVER?'
                           set_cmd = ':SENS1:AVER {:s}')
        self.add_parameter('phase_offset', 
                           get_cmd = ':CALC1:CORR:OFFS:PHAS?', 
                           set_cmd = ':CALC1:CORR:OFFS:PHAS {:s}')