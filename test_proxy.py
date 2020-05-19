# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 22:12:05 2020

@author: Chao
"""

from instrumentserver.proxy import (InstrumentProxy,
                                    create_instrument,
                                    get_existing_instruments
                                    )

'''
rf_src = InstrumentProxy('rf_src')
dummy_vna = InstrumentProxy('dummy_vna')
test_src = create_instrument(instrument_class = 
                    'instrumentserver.testing.dummy_instruments.rf.Generator',                          
                            name = 'test_src')
InstrumentProxy("instrument_that_doesnt_exit")
rf_src.frequency(10)
'''

yoko = InstrumentProxy('yoko')

print(yoko.current(10))
print(yoko.current())

yoko.dac1()
yoko.multiply_addfunc(1, 2, 3)

yoko.multiply_method(1, 2, 3)
yoko.reset_method()

yoko.multiply_method(1, 2, c=5)

# yoko2 = create_instrument(
#           instrument_class = 'qc.tests.instrument_mocks.DummyInstrument',
#                           name = 'yoko2')


# mydummy = InstrumentProxy('mydummy')
# mydummy.A.snapshot()

dummy_vna = InstrumentProxy('dummy_vna')
# gen = InstrumentProxy('gen')
# # some dictionaries that can be used to construct the GUI 
# all_instruments = get_existing_instruments()
# gen_param_ss = gen.snapshot()['parameters']
# gen_func_dict = gen.simple_func_dict
# 1