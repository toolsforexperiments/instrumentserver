# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 22:12:05 2020

@author: Chao
"""

from instrumentserver.proxy import InstrumentProxy

dac = InstrumentProxy('dac')

print (dac.ch1(), dac.ch2())
dac.ch1(2)
dac.ch2(3)
print (dac.ch1(), dac.ch2())

print (dac.multiply(1,2))

dac.reset()
print (dac.ch1(),dac.ch2())

