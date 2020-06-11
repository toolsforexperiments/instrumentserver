# -*- coding: utf-8 -*-
"""
Created on Wed Jun  3 11:48:02 2020

@author: Ryan
"""

from instrumentserver.client.proxy import Client
import sys
import os
from instrumentserver.client.core import sendRequest

import argparse
import logging


from instrumentserver import QtWidgets, QtCore
from instrumentserver.log import setupLogging, log, LogLevels
from instrumentserver.server import startServer
from instrumentserver.server.application import startServerGuiApplication

                                #path to wherever we would store hatlab-specific modules
sys.path.append(os.path.abspath(r'C:\Users\Ryan\Documents\GitHub\instrumentserver\mockUp'))
#%%
# def createInstrumentsFromDict(cli, Inst_Info): 
#     for key, val in Inst_Info.items(): 
#         #TODO: Is there a better way to do this without global variables or exec?
#         comm = "global %s \n%s = cli.create_instrument(val,key)" % (key, key)
#         print(comm)
#         exec(comm)
# def startExistingInstruments(cli):
#     server_dict = cli.list_instruments()
#     dict_out = {}
#     #convert the output of list_instruments into the input of create_instrument
#     for key, val in server_dict.items(): 
#         dict_out[key] = str(val).split("'")[1]
        
#     for key, val in dict_out.items(): 
#         #TODO: Is there a better way to do this without global variables or exec?
#         comm = "global %s \n%s = cli.create_instrument(val,key)" % (key, key)
#         print(comm)
#         exec(comm)
#%%
cli = Client()
try: 
    sendRequest('')
except: 
    print('Existing server not found, start instrumentserver/server.py')
finally: 
    server_dict = cli.list_instruments()
    dict_out = {}
    #convert the output of list_instruments into the input of create_instrument
    for key, val in server_dict.items(): 
        dict_out[key] = str(val).split("'")[1]
        
    for key, val in dict_out.items(): 
        #TODO: Is there a better way to do this without global variables or exec?
        comm = "global %s \n%s = cli.create_instrument(val,key)" % (key, key)
        exec(comm)
    
    vna = cli.create_instrument("instrumentserver.testing.dummy_instruments.noiseVNA.fakeVNA", "vna")
    cs = cli.create_instrument("instrumentserver.testing.dummy_instruments.CS.fakeCS", "cs")
    pm = cli.create_instrument("instrumentserver.params.ParameterManager", "pm")
    
    cwd = os.getcwd()
