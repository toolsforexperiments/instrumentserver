# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
import os
import inspect
import zmq
import json
import jsonpickle
from jsonschema import validate
from typing import Dict, List, Any, Union, Tuple
from qcodes.instrument import parameter
from functools import partial
from qcodes.utils.validators import Validator
from . import getInstrumentserverPath

PARAMS_SCHEMA_PATH = os.path.join(getInstrumentserverPath('schemas'),
                                  'instruction_dict.json')

class InstrumentProxy():
    """Prototype for an instrument proxy object. Each proxy instantiation 
    represents a virtual instrument. 
    
    """
    
    def __init__(self, instruemnt_name: str, server_address : str = '5555'):
        """ Initialize a proxy. Create a zmq.REQ socket that connectes to the
        server, and get a snapshot from the server. The snapshot will be 
        stroed in a private dictionary.
    
        :param instruemnt_name: The name of the instrument that the proxy will 
        represnt. The name must match the instrument name in the server.
        :param server_address: the last 4 digits of the local host tcp address
        """
        # This does not include create instrument from client yet
        
        self.name = instruemnt_name
        self.context = zmq.Context()
        
        print("Connecting to server...")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:" + server_address)
        
        # check if instrument exits on the server or not 
        print("Checking instruments on the server..." )        
        instructionDict = {'operation' : 'get_existing_instruments'}
        existing_instruemnts = self._requestFromServer(instructionDict)
        print 

        if self.name in existing_instruemnts:
            print ('Found '+ instruemnt_name + ' on server')
        else:
            raise KeyError('Can\'t find ' + self.name + ' on server. Avilable '+\
                           'instruemnts are: ' + str(existing_instruemnts) +\
                           '. Check spelling or create instrument first')
                
        # Get all the parameters and functions from the server and add them to 
        # this virtual instrument class
        print("Setting up virtual instrument "+ self.name + "..." )
        instructionDict = {
            'operation' : 'proxy_construction',
            'instrument_name' : self.name
            }
        construct_dict = self._requestFromServer(instructionDict)
        self._construct_param_dict = construct_dict['parameters']
        self._construct_func_dict = construct_dict['functions']

        self._constructProxyParameters()
        self._constructProxyFunctions()
        
    def _requestFromServer(self, instructionDict: Dict) -> Any:
        """ send commend to the server in instructionDict format, return the 
        respond from server.
        """        
        with open(PARAMS_SCHEMA_PATH) as f:
            schema = json.load(f)
        try:
            validate(instructionDict, schema)
        except:
            raise
            
        self.socket.send_json(instructionDict)
        return self.socket.recv_json()         
           
    def _constructProxyParameters(self):
        """Based on the parameter dictionary replied from server, add the 
        instrument parameters to the proxy instrument class
        """     
        for param in self._construct_param_dict :  
            param_dict_temp = self._construct_param_dict[param]        
            param_temp = parameter.Parameter(
                            name = param, 
                            unit = param_dict_temp['unit'],
                            set_cmd = partial(self._setParam, param),
                            get_cmd = partial(self._getParam, param),
                            vals =  jsonpickle.decode(param_dict_temp['vals'])                      
                            )
            setattr(self, param, param_temp) 
            
    def _constructProxyFunctions(self):
        """Based on the function dictionary replied from server, add the 
            instrument functions to the proxy instrument class
        """   
        for func_name in self._construct_func_dict :
            func_dic = self._construct_func_dict[func_name]
            if len(func_dic) != 3:
                raise KeyError('invalid function construction dictionary')
            if 'arg_vals' in func_dic:
                vals = jsonpickle.decode(func_dic['arg_vals'])
                func_temp = partial(self._validateAndCallFunc, func_name, vals) 
            elif 'fullargspec' in func_dic:
                fullargspec = jsonpickle.decode(func_dic['fullargspec'])
                if 'self' in fullargspec.args:
                    fullargspec.args.remove('self')
                func_temp = partial(self._callFunc, func_name, fullargspec) 
            
            func_temp.__doc__ = func_dic['docstring']       
            setattr(self, func_name, func_temp )
            getattr(self, func_name).__doc__ = func_dic['docstring']

    
    def _getParam(self, para_name: str) -> Any:
        """ send requet to the server and get the value of the parameter. 
        
        :param para_name: The name of the parameter to get
        :returns: the parameter value replied from the server
        """
        instructionDict = {
            'operation' : 'proxy_get_param',
            'instrument_name' : self.name,
            'parameter' : {'name' : para_name}
            }
        param_value = self._requestFromServer(instructionDict)
        return param_value
        
    def _setParam(self, para_name: str, value: any) -> None: 
        """ send requet to the server and set the value of the parameter 
    
        :param paraName: The name of the parameter to set
        """
        instructionDict = {
            'operation' : 'proxy_set_param',
            'instrument_name' : self.name,
            'parameter' : {'name' : para_name, 'value' : value}
            }
        self._requestFromServer(instructionDict)
        
    
    def _validateAndCallFunc(self, func_name: str, 
                             validators : List[Validator], 
                             *args: Any) -> Any: 
        """ validate the arguments with the provided validators first, then 
        send requet to the server for function call. Only used for the functions
        that are in the qcodes.instrument.function.Function class.
        
        :param funcName: The name of the function to call
        :param validators: List of validators for each argument
        :param args: A tuple that contains the value of the function arguments
        :returns: the return value of the function replied from the server
        """
        if len(args) != len(validators):
            raise TypeError(func_name + ' missing arguments')
        for i in range(len(args)):
            validators[i].validate(args[i])
        instructionDict = {
            'operation' : 'proxy_call_func',
            'instrument_name' : self.name,
            'function' : {'name' : func_name, 'args' : args}
            }
        return_value = self._requestFromServer(instructionDict)
        return return_value


    def _callFunc(self, func_name: str, 
              fullargspec: inspect.FullArgSpec,
              *args: Any, 
              **kwargs: Dict) -> Any: 
        """ call functions that are bound methods to the instruemnt class.
        
        :param funcName: The name of the function to call
        :param fullargspec: Signiture of the origional instruemnt function on
            the server.
        :param args: A tuple that contains the value of the function arguments
        :returns: the return value of the function replied from the server
        """
        def len_(foo):
            if foo ==None:
                return 0
            else:
                return len(foo)
        required_vlue_number = len_(fullargspec.args) - len_(fullargspec.defaults) 
        max_provided_value_number = len_(args) + len_(kwargs)
        if required_vlue_number > max_provided_value_number:
            raise TypeError(func_name + ' missing arguments')
            
        instructionDict = {
            'operation' : 'proxy_call_func',
            'instrument_name' : self.name,
            'function' : {'name' : func_name, 'args' : args, 'kwargs' : kwargs}
            }
        return_value = self._requestFromServer(instructionDict)
        return return_value    
    

    def snapshot(self) -> Dict:
        """ send requet to the server for a snapshot of the instruemnt.
        """
        instructionDict = {
            'operation' : 'instrument_snapshot',
            'instrument_name' : self.name,
            }
        snapshot_ = self._requestFromServer(instructionDict)
        return snapshot_
        
        
    def __delete__(self): 
        """ delete class objects and disconnect from server.        
        """
        