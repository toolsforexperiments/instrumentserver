# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
import os
from types import MethodType
import json
import inspect
import typing
from typing import Dict, List, Any, Union, Tuple, Type, Optional
from functools import partial

import zmq
from zmq.sugar.socket import Socket
import jsonpickle
from jsonschema import validate as jsvalidate

import qcodes as qc
from qcodes.instrument import parameter
from qcodes import Instrument
from qcodes.utils.validators import Validator
from . import getInstrumentserverPath
from .base import send, recv

PARAMS_SCHEMA_PATH = os.path.join(getInstrumentserverPath('schemas'),
                                  'instruction_dict.json')


class ModuleProxy():
    """Prototype for a module proxy object. Each proxy instantiation 
    represents a virtual module (instrument of submodule of instrument).     
    """
    
    def __init__(self, 
                 instrument_name: str,                 
                 construct_dict: Dict, 
                 submodule_name : Optional[Union[str, None]] = None,
                 server_address : str = '5555'):
        """ Initialize a proxy. Create a zmq.REQ socket that connectes to the
        server, get all the parameters and functions belong to this module and
        add them to this virtual module class.
    
        :param instruemnt_name: The name of the instrument that the proxy will 
        represnt. The name must match the instrument name in the server.
        
        :param construct_dict: The dictionary that contains the information of 
        the module memebr functions and parameters
        
        :param submodule_name: The name of the instrument submodule (is this 
         a proxy for submodule)
        
        :param server_address: the last 4 digits of the local host tcp address
        """     
        
        self.instrument_name = instrument_name
        self.submodule_name = submodule_name        
        self._construct_dict = construct_dict
        
        
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:" + server_address)

        self._constructProxyParameters()
        self._constructProxyFunctions()
               
           
    def _constructProxyParameters(self):
        """Based on the parameter dictionary replied from server, add the 
        instrument parameters to the proxy instrument class
        """     
        construct_param_dict = self._construct_dict['parameters']
        self.simple_param_dict = {} # for GUI use
        for param_name in construct_param_dict:  
            param_dict_temp = construct_param_dict[param_name] 
            unit = param_dict_temp['unit']
            param_temp = parameter.Parameter(
                            name = param_name, 
                            unit = unit,
                            set_cmd = partial(self._setParam, param_name),
                            get_cmd = partial(self._getParam, param_name),
                            vals =  jsonpickle.decode(param_dict_temp['vals'])                      
                            )
            self.simple_param_dict[param_name] = {
                'name' : param_name,                                                 
                'unit' : unit
                }
            setattr(self, param_name, param_temp) 
            
            
    def _constructProxyFunctions(self):
        """Based on the function dictionary replied from server, add the 
        instrument functions to the proxy instrument class
        """                   
        construct_func_dict = self._construct_dict['functions']
        self.simple_func_dict = {} # for GUI use
        for func_name in construct_func_dict :
            func_dic = construct_func_dict[func_name]
            if 'arg_vals' in func_dic: # old style added functions
                vals = jsonpickle.decode(func_dic['arg_vals'])
                func_temp = partial(self._validateAndCallFunc, func_name, vals) 
                func_temp.__doc__ = func_dic['docstring'] 
            elif 'fullargspec' in func_dic:
                func_temp = self._buildFacadeFunc(func_dic)   
            
            self.simple_func_dict[func_name] = {
                'name' : func_name,                                                
                'signature' : inspect.signature(func_temp)
                }                           
            setattr(self, func_name, func_temp )



    def _getParam(self, para_name: str) -> Any:
        """ send requet to the server and get the value of the parameter. 
        
        :param para_name: The name of the parameter to get.
        
        :returns: the parameter value replied from the server
        """
        instructionDict = {
            'operation' : 'proxy_get_param',
            'instrument_name' : self.instrument_name,
            'submodule_name' : self.submodule_name,
            'parameter' : {'name' : para_name}
            }
        param_value = _requestFromServer(self.socket, instructionDict)
        return param_value
        
    def _setParam(self, para_name: str, value: any) -> None: 
        """ send requet to the server and set the value of the parameter 
    
        :param value: the value to set
        """
        instructionDict = {
            'operation' : 'proxy_set_param',
            'instrument_name' : self.instrument_name,
            'submodule_name' : self.submodule_name,
            'parameter' : {'name' : para_name, 'value' : value}
            }
        _requestFromServer(self.socket, instructionDict)    


    def _buildFacadeFunc(self, func_dic):
        """Build a facade function, matching the signature of the origional
        instrument function.
        """
        name = func_dic['name']
        docstring = func_dic['docstring']
        spec = func_dic['fullargspec']
        sig = func_dic['signature']
        
        if spec.args[0]=='self':
            spec.args.remove('self')
        args, default_values = spec[0], spec[3]
        arglen = len(args)
        
        if default_values is not None:
            defaults = args[arglen - len(default_values):]                       
            arglen -= len(list(defaults))
    
        def _proxy(*pargs, **pkw):       
            # Reconstruct keyword arguments
            if default_values is not None:            
                pargs, kwparams = pargs[:arglen], pargs[arglen:]
                for positional, key in zip(kwparams, defaults):
                        pkw[key] = positional
            return self._callFunc(name, *pargs, **pkw)
        print ('name:',name,'sig: ',sig)                
        args_str = str(sig)
        callargs = str(tuple(sig.parameters.keys())).replace("'",  '')
                
        facade = 'def {}{}:\n    """{}"""\n    return _proxy{}'.format(
            name, args_str, docstring, callargs)
        # facade_globs = {'_proxy': _proxy}
        facade_globs = _argument_hints()
        facade_globs['_proxy'] = _proxy
        # facade_globs['typing'] = typing
        exec (facade,  facade_globs)
        return facade_globs[name]   
     
    
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
            raise TypeError(func_name + ' is missing or got extra arguments, ' +\
                            str(len(validators)) + ' required')
        for i in range(len(args)):
            validators[i].validate(args[i])
        instructionDict = {
            'operation' : 'proxy_call_func',
            'instrument_name' : self.instrument_name,
            'submodule_name' : self.submodule_name,
            'function' : {'name' : func_name, 'args' : args}
            }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value


    def _callFunc(self, func_name: str, 
              *args: Any, 
              **kwargs: Dict) -> Any: 
        """ call functions that are bound methods to the instruemnt class.
        
        :param funcName: The name of the function to call
        :param fullargspec: Signiture of the origional instruemnt function on
            the server.
        :param args: A tuple that contains the value of the function arguments
        :returns: the return value of the function replied from the server
        """            
        instructionDict = {
            'operation' : 'proxy_call_func',
            'instrument_name' : self.instrument_name,
            'submodule_name' : self.submodule_name,
            'function' : {'name' : func_name, 'args' : args, 'kwargs' : kwargs}
            }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value    
    

    def snapshot(self) -> Dict:
        """ send requet to the server for a snapshot of the instruemnt.
        """
        instructionDict = {
            'operation' : 'instrument_snapshot',
            'instrument_name' : self.instrument_name,
            'submodule_name' : self.submodule_name,
            }
        snapshot_ = _requestFromServer(self.socket, instructionDict)
        return snapshot_
        
        
    def __delete__(self): 
        """ delete class objects and disconnect from server.   
        (Also remove the instrument from the server?)
        """


class InstrumentProxy(ModuleProxy):
    """Prototype for an instrument proxy object. Each proxy instantiation 
    represents a virtual instrument. 
    
    """
    
    def __init__(self, instruemnt_name: str, server_address : str = '5555'):
        """ Initialize a proxy. Create a zmq.REQ socket that connectes to the
        server, get all the functions, parameters, and submodules of this
        instrument from the server and add them to this virtual instrument class.
    
        :param instruemnt_name: The name of the instrument that the proxy will 
        represnt. The name must match the instrument name in the server.
        :param server_address: the last 4 digits of the local host tcp address
        """
        
        self.name = instruemnt_name
        self.context = zmq.Context()
        
        print("Connecting to server...")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:" + server_address)
        
        # check if instrument exits on the server or not 
        print("Checking instruments on the server..." )        
        existing_instruemnts = list(get_existing_instruments(server_address).keys())

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
        self._construct_dict = _requestFromServer(self.socket, instructionDict)
        
        # create the top instrument module
        super().__init__(self.name, self._construct_dict, None, server_address)
        
        # create the instrument submodules if exist
        try:
            submodule_dict = self._construct_dict['submodule_dict']
            self.submodule_list = list(submodule_dict.keys())
        except AttributeError:
            submodule_dict = {}
            self.submodule_list = []
        
        for module_name in self.submodule_list: 
            submodule_construct_dict = submodule_dict[module_name]
            submodule = ModuleProxy(self.name, 
                                    submodule_construct_dict, 
                                    module_name, 
                                    server_address)
            setattr(self, module_name, submodule)
        
        

def get_existing_instruments(server_address : str = '5555') :
    ''' Get the existing instruments on the server
    
    '''
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://localhost:" + server_address)
    instructionDict = {'operation' : 'get_existing_instruments'}
    existing_instruemnts = _requestFromServer(socket, instructionDict)
    return existing_instruemnts       

def create_instrument(instrument_class: Union[Type[Instrument],str],
                      name: str,
                      *args: Any,
                      server_address : str = '5555',
                      **kwargs: Any,                      
                      ) -> InstrumentProxy:     
    """ create a new instrument.
    
    :param instrument_class: Class of the instrument to create or a string of 
        of the class
    :param name: Name of the new instrument
    :returns: a new virtual instrument
    """  
    ########
    # we need some kind of instrument class validator here
    # i.e. check if the driver exists or not, etc
    ########    
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://localhost:" + server_address)
    # look for existing instruments
    existing_instruemnts = list(get_existing_instruments(server_address).keys())
    if name in existing_instruemnts:
        raise NameError(f'Instrument {name} alreadt exists on the server')
    # create new instrument
    instructionDict = {
        'operation' : 'instrument_creation',
        'instrument_name' : name,
        'instrumnet_create' : { 
            'instrument_class' : str(instrument_class),
            'args' : args,
            'kwargs' : kwargs
            }
        }
    _requestFromServer(socket, instructionDict)
    return InstrumentProxy(name, server_address)
    


# ------------------ helper functions ----------------------------------------
def _requestFromServer(socket: Socket, instructionDict: Dict) -> Any:
    """ send commend to the server in instructionDict format, return the 
    respond from server.
    """ 
    # validate instruction dictionary first       
    with open(PARAMS_SCHEMA_PATH) as f:
        schema = json.load(f)
    try:
        jsvalidate(instructionDict, schema)
    except:
        raise
    # sende instruction dictionary to server      
    send(socket, instructionDict)
    # receive response from server and handle error
    response = recv(socket)     
    if response['error'] != None:
        error = response['error']
        print('Error from server:')
        raise error
    return_value = response['return_value']
    return return_value

def _argument_hints(package=None) ->Dict[str, object]:
    ''' generate a dictionary that contains the argument hints for construncting
    the facade functions. By default, all the hint type from typing package will
    be included
    
    :param package: package that contains the customized hint types
    :return : Dictionary that contain the hints.
    '''
    arg_hint_dict = {}
    for obj in typing.__all__:
        if obj[0] >= 'A' and obj[0]<='Z':
            arg_hint_dict[obj] = typing.__dict__[obj]
    return arg_hint_dict
