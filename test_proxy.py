# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 22:12:05 2020

@author: Chao
"""

from instrumentserver.proxy import InstrumentProxy

yoko = InstrumentProxy('yoko')

print(yoko.current(10))
print(yoko.current())

yoko.dac1()