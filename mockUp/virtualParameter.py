# -*- coding: utf-8 -*-
"""
Created on Mon May 18 15:50:11 2020

@author: rkauf
"""

from qcodes.instrument.parameter import Parameter

class instrumentSetting(Parameter): 
    
    def __init__(self, name, defVal = 0): 
        super().__init__(name)
        self._setting = defVal
        self._name = name
        
    def get_raw(self): 
        return self._setting
    
    def set_raw(self, val): 
        self._setting = val
        print("{} set to {}".format(self._name, self._setting))
        