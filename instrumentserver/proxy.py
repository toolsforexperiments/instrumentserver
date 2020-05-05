# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
import os
from types import MethodType
import inspect
import zmq
from zmq.sugar.socket import Socket
import json
import jsonpickle
from jsonschema import validate as jsvalidate
import qcodes as qc
from typing import Dict, List, Any, Union, Tuple, Type
from qcodes.instrument import parameter
from qcodes import Instrument
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
        
        self.name = instruemnt_name
        self.context = zmq.Context()
        
        print("Connecting to server...")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:" + server_address)
        
        # check if instrument exits on the server or not 
        print("Checking instruments on the server..." )        
        instructionDict = {'operation' : 'get_existing_instruments'}
        existing_instruemnts = _requestFromServer(self.socket, instructionDict)
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
        self._construct_dict = _requestFromServer(self.socket, instructionDict)
        self._construct_param_dict = self._construct_dict['parameters']
        self._construct_func_dict = self._construct_dict['functions']

        self._constructProxyParameters()
        self._constructProxyFunctions()
        
       
           
    def _constructProxyParameters(self):
        """Based on the parameter dictionary replied from server, add the 
        instrument parameters to the proxy instrument class
        """     
        for param in self._construct_param_dict:  
            param_dict_temp = self._construct_param_dict[param]        
            param_temp = parameter.Parameter(
                            name = param, 
                            unit = param_dict_temp['unit'],
                            set_cmd = partial(self._setParam, param),
                            get_cmd = partial(self._getParam, param),
                            vals =  jsonpickle.decode(param_dict_temp['vals'])                      
                            )
            # override the parameter snapshot function
            # def test_func(self):
            #     print ('hello snapshot')
            # param_temp.snapshot = MethodType(test_func, param_temp)
            setattr(self, param, param_temp) 
            
            
    def _constructProxyFunctions(self):
        """Based on the function dictionary replied from server, add the 
        instrument functions to the proxy instrument class
        """   
        def _build_facade(func_dic):
            """Build a facade function, matching the signature of the origional
            instrument function.
            """
            name = func_dic['name']
            docstring = func_dic['docstring']
            spec = jsonpickle.decode(func_dic['fullargspec'])
            sig = jsonpickle.decode(func_dic['signature'])
            
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
                    
            args_str = str(sig)
            callargs = str(tuple(sig.parameters.keys())).replace("'",  '')
                    
            facade = 'def {}{}:\n    """{}"""\n    return _proxy{}'.format(
                name, args_str, docstring, callargs)
            facade_globs = {'_proxy': _proxy}
            exec (facade,  facade_globs)
            return facade_globs[name]

        for func_name in self._construct_func_dict :
            func_dic = self._construct_func_dict[func_name]
            if 'arg_vals' in func_dic: # old style added functions
                vals = jsonpickle.decode(func_dic['arg_vals'])
                func_temp = partial(self._validateAndCallFunc, func_name, vals) 
                func_temp.__doc__ = func_dic['docstring'] 
            elif 'fullargspec' in func_dic:
                func_temp = _build_facade(func_dic)
                              
            setattr(self, func_name, func_temp )

    
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
        param_value = _requestFromServer(self.socket, instructionDict)
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
        _requestFromServer(self.socket, instructionDict)
        
    
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
            'instrument_name' : self.name,
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
            'instrument_name' : self.name,
            'function' : {'name' : func_name, 'args' : args, 'kwargs' : kwargs}
            }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value    
    

    def snapshot(self) -> Dict:
        """ send requet to the server for a snapshot of the instruemnt.
        """
        instructionDict = {
            'operation' : 'instrument_snapshot',
            'instrument_name' : self.name,
            }
        snapshot_ = _requestFromServer(self.socket, instructionDict)
        return snapshot_
        
        
    def __delete__(self): 
        """ delete class objects and disconnect from server.   
        (Also remove the instrument from the server?)
        """


def create_instrument(instrument_class: Union[Type[Instrument],str],
                      name: str,
                      *args: Any,
                      recreate: bool = False,
                      server_address : str = '5555',
                      **kwargs: Any,                      
                      ) -> InstrumentProxy:     
    """ create a new instrument.
    
    :param instrument_class: Class of the instrument to create or a string of 
        of the class
    :param name: Name of the new instrument
    :param recreate: When ``True``, the instruments gets recreated if it is found.
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
    instructionDict = {'operation' : 'get_existing_instruments'}
    socket.send_json(instructionDict)
    existing_instruemnts = socket.recv_json()     
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
    with open(PARAMS_SCHEMA_PATH) as f:
        schema = json.load(f)
    try:
        jsvalidate(instructionDict, schema)
    except:
        raise
        
    socket.send_json(instructionDict)
    return socket.recv_json()  
