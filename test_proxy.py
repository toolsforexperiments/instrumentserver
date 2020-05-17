# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 22:12:05 2020

@author: Chao
"""

from instrumentserver.proxy import InstrumentProxy, create_instrument, get_existing_instruments
import qcodes
import json 
import jsonpickle

rf_src = InstrumentProxy('rf_src')
dummy_vna = InstrumentProxy('dummy_vna')

test_src = create_instrument(instrument_class = 'instrumentserver.testing.dummy_instruments.rf.Generator',                          
                            name = 'test_src')


# InstrumentProxy("instrument_that_doesn't_exit")
# rf_src.frequency(10)

                          
