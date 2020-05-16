# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 22:12:05 2020

@author: Chao
"""

from instrumentserver.proxy import InstrumentProxy, create_instrument, get_existing_instruments
import qcodes
import json 
import jsonpickle

yoko = InstrumentProxy('yoko')

print(yoko.current(10))
print(yoko.current())

yoko.dac1()
yoko.multiply_addfunc(1,2,3)

yoko.multiply_method(1,2,3)
yoko.reset_method()

yoko.multiply_method(1,2,c=5)


# yoko2 = create_instrument(instrument_class = 'qc.tests.instrument_mocks.DummyInstrument',                          
                          # name = 'yoko2')
                          
                          
mydummy = InstrumentProxy('mydummy')                          
mydummy.A.snapshot()


gen = InstrumentProxy('gen')
# some dictionaries that can be used to construct the GUI 
all_instruemnts = get_existing_instruments()
gen_param_ss = gen.snapshot()['parameters']
gen_func_dict = gen.simple_func_dict

# outpur_dir = r'C:\Users\zctid.LAPTOP-150KME16\Desktop\Qcodes_test\GUI_JSON\\'
# with open(outpur_dir + 'instrument_list.json', 'w') as outfile:
#     json.dump(all_instruemnts, outfile)
# with open(outpur_dir + 'gen_param.json', 'w') as outfile:
#     json.dump(gen_param_ss, outfile)
# with open(outpur_dir + 'gen_func.json', 'w') as outfile:
#     json.dump(jsonpickle.encode(gen_func_dict), outfile)