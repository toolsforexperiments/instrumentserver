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
import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
from qcodes import Instrument
import ctypes
import easygui


from hatdrivers.Agilent_ENA_5071C import Agilent_ENA_5071C
from hatdrivers.Keysight_N5183B import Keysight_N5183B
from hatdrivers.Yokogawa_GS200 import YOKO
from hatdrivers.SignalCore_sc5511a import SignalCore_sc5511a
from hatdrivers.MiniCircuits_Switch import MiniCircuits_Switch
from hatdrivers.switch_control import SWT as SWTCTRL

#%%

cli = Client()
try: 
    sendRequest('')
except: 
    raise Exception('Existing server not found, start instrumentserver/server.py')
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
        
    Instrument.close_all()
    #vna = cli.create_instrument('hatdrivers.Agilent_ENA_5071C.Agilent_ENA_5071C',"vna", address = "TCPIP0::169.254.152.68::inst0::INSTR")
    #SigGen = cli.create_instrument('hatdrivers.Keysight_N5183B.Keysight_N5183B',"SigGen", address = "TCPIP0::169.254.29.44::inst0::INSTR")
    QGen = cli.create_instrument('hatdrivers.Keysight_N5183B.Keysight_N5183B',"QGen", address = "TCPIP0::169.254.161.164::inst0::INSTR")
    #%%
    #yoko2 = cli.create_instrument(YOKO, 'yoko2', "TCPIP::169.254.47.131::inst0::INSTR")
    
    dll_path = r'C:\Users\Hatlab_3\Desktop\RK_Scripts\New_Drivers\HatDrivers\DLL\sc5511a.dll' #TODO: Build into SC driver?
    SigCore5 = cli.create_instrument('hatdrivers.SignalCore_sc5511a.SignalCore_sc5511a','SigCore5', dll = ctypes.CDLL(dll_path), serial_number = b'10001852')
    
    #cwd = easygui.diropenbox('Select where you are working:')
    

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
