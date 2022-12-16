# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 22:12:05 2020

@author: Chao
"""

# TODO: This script seems outdated, should probably update it. or delete it and have tests that do this instead of scripts

from instrumentserver.client.proxy import create_instrument

test_src = create_instrument(instrument_class = 'instrumentserver.testing.dummy_instruments.rf.Generator',                          
                            name = 'test_src')

dummy_vna = create_instrument(instrument_class = 'instrumentserver.testing.dummy_instruments.rf.ResonatorResponse',
                            name = 'dummy_vna')
print(dummy_vna.data.setpoints[0])

dummy_channels = create_instrument(instrument_class = 'instrumentserver.testing.dummy_instruments.rf.DummyInstrumentWithSubmodule',
                            name = 'dummy_channels')

dummy_channels.test_func(1,2,3,4,c=4,d=5)

def dummy_multiply(self,a,b):
    return a*b*self.ch0()
dummy_channels.ChanA.add_function(dummy_multiply,override=1)
dummy_channels.ChanA.ch0(0.5)
dummy_channels.ChanA.dummy_multiply(1,2)


# -------------Error cases-------------------------------
# ProxyInstrument("instrument_that_doesn't_exit") # no instrument
# test_src.frequency(10) # invalid set value