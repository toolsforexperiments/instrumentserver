# -*- coding: utf-8 -*-
"""
Created on Wed Jun  3 11:50:08 2020

@author: Ryan
"""
#%% Setup
from instrumentserver import setupLogging, logger, QtWidgets, client, serialize
from instrumentserver.log import LogWidget
from instrumentserver.client import QtClient
from instrumentserver.client.application import InstrumentClientMainWindow
from instrumentserver.gui.instruments import ParameterManagerGui
from instrumentserver.client.proxy import Client
from qcodes import Instrument

runfile(r'C:\Users\Ryan\Documents\GitHub\instrumentserver\mockUp\hatlab_modules\startup.py')

#%% Beginning the measurement

datadir = 
#import the parameters from ParameterManager?

