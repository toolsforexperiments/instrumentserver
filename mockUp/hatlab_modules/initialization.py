# -*- coding: utf-8 -*-
"""
Created on Wed May 27 13:18:12 2020

@author: Ryan
"""

from instrumentserver.proxy import InstrumentProxy, create_instrument, get_existing_instruments
import os


def initialize(instList, filename, directory = os.getcwd()): 
    
    