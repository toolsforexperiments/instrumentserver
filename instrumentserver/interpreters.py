# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 15:57:23 2020

@author: Chao
"""

import re
import inspect
import jsonpickle
from typing import Dict, List, Any, Union, List, Optional
from typing_extensions import Literal, TypedDict
import qcodes as qc
from qcodes import Station, Instrument
from qcodes.utils.validators import Validator, range_str




# dictionary type defination 

class InstrumentDictType(TypedDict):
    instrument_type : str
    address : Optional[str]
    serial_number : Optional[str]
    
class ParamDictType(TypedDict):
    name :  str
    value : Optional[Any] 
    
class FuncDictType(TypedDict):
    name :  str
    args : Optional[tuple]

class InstructionDictType(TypedDict):
    operation: Literal['get_existing_instruments',
                        'instrument_creation',
                        'proxy_construction', 
                        'proxy_get_param', 
                        'proxy_set_param',
                        'proxy_call_func'
                        'instrument_snapshot'
                        ] 
    
    instrument_name: Optional[str]  # not needed for 'get_existing_instruments'
    instrumnet : Optional[InstrumentDictType]  # for instrument creation
    parameter : Optional[ParamDictType] # for get/set_param
    function : Optional[FuncDictType] # for function call
    
    
    
    
def instructionDict_to_instrumentCall(station: Station, instructionDict : InstructionDictType) -> Any:
    """
    This is the interpreter function that the server will call to translate the
    dictionary received from the proxy to instrument calls.
    
    :param station: qcodes.station object, the station that contains the 
        instrument to call.
    :param instructionDict:  The dicitonary passed from the instrument proxy
        that contains the information needed for the operation. 

    :returns: the results returned from the instrument call
    """
    
    operation = instructionDict['operation']
    
    if operation == 'get_existing_instruments': 
        # usually this operation will be called before all the others to check
        # if the instrument already exists ont the server.
        returns = _getExistingInstruments(station)
    elif operation == 'instrument_creation':
        returns = _instrumentCreation(station, instructionDict)
    else: # doing operation on an existing instrument
        instrument = station[instructionDict['instrument_name']]     
        if operation == 'proxy_construction':
            returns = _proxyConstruction(instrument)
        elif operation == 'proxy_get_param':
            returns = _proxyGetParam(instrument, instructionDict['parameter'])       
        elif operation == 'proxy_set_param':
            returns = _proxySetParam(instrument, instructionDict['parameter'])  
        elif operation == 'proxy_call_func':
            returns = _proxyCallFunc(instrument, instructionDict['function'])    
        elif operation == 'instrument_snapshot':
            returns = instrument.snapshot()          
        else :
            # the instructionDict will be ckecked in the proxy before sent to 
            # here, so in principle this error should not happen.
            raise TypeError('operation type not supported')
    return  returns


# Some private tool functions
def _getExistingInstruments(station: Station) -> List:
    """
    Get the existing instruments in the station,
    
    :returns : list of the existing instruemnt names in the station
    """
    return list(station.snapshot()['instruments'].keys())

def _instrumentCreation(station: Station, instructionDict : Dict) -> None:
    # not implemented yet
    pass

def _proxyConstruction(instrument: Instrument) -> Dict:
    '''
    Get the dictionary that describes the instrument.
    This parameter part is similar to the qcodes snapshot of the instrument,
    but with less information, also the string that describes the validator of 
    each parameter/argument is replaced with a jsonpickle encoded form so that 
    it is easier to reproduce the validator object in the proxy.
    The functions are directly extracted from the instrument class.
    
    :returns : a dictionary that dercribes the instrument

    '''
    param_names = list(instrument.__dict__['parameters'].keys())
    construct_param_dict = {}    
    for param_name in param_names:
        param_dict_temp = {}
        param_dict_temp['name'] = param_name
        param_dict_temp['unit'] = instrument[param_name].unit        
        jp_vals = jsonpickle.encode(instrument[param_name].vals)
        param_dict_temp['vals'] = jp_vals    
        construct_param_dict[param_name] = param_dict_temp
    
    # get the fucntions belong to the instrument
    methods = set(dir(instrument))
    base_methods = (dir(base) for base in instrument.__class__.__bases__)
    unique_methods = methods.difference(*base_methods)
    func_names = []
    for method in unique_methods :
        if callable(getattr(instrument, method)) and method not in construct_param_dict:
            func_names.append(method)
    # create the dictionary that contains the info needed for creating virtual 
    # instrument.    
    construct_func_dict = {}
    for func_name in func_names:
        func_dict_temp = {}
        func_dict_temp['name'] = func_name
        func = getattr(instrument , func_name)
        func_dict_temp['docstring'] = func.__doc__

        if func.__class__ == qc.instrument.function.Function:
        # for functions added using the old 'instruemnt.add_function' method,
        # (the functions only have positional arguments, and each argument has
        # a validator). In this case, the list of validators is pickled            
            jp_argvals = jsonpickle.encode(func._args)
            func_dict_temp['arg_vals'] = jp_argvals            
        else:
        # for functions added directly to instrument class as bound methods,
        # the fullargspec is pickled             
            fullargspec = inspect.getfullargspec(func)
            jp_fullargspec = jsonpickle.encode(fullargspec)
            func_dict_temp['fullargspec'] = jp_fullargspec                      
        construct_func_dict[func_name] = func_dict_temp        
    construct_dict = {'functions' : construct_func_dict,
                      'parameters' : construct_param_dict}
        
    return construct_dict
    
    
def _proxyGetParam(instrument: Instrument, paramDict : ParamDictType) -> Any:
    '''
    Get a parameter from the instrument.
    
    :param paramDict: the dictionary that contains the parameter to change, the 
        'value' item will be omited.
    :returns : value of the parameter returned from instrument

    '''
    paramName = paramDict['name']   
    return instrument[paramName]()

def _proxySetParam(instrument: Instrument, paramDict : ParamDictType) -> None:
    '''
    Set a parameter in the instrument.
    
    :param paramDict:  the dictionary that contains the parameter to change, the 
        'value' item will be the set value.
        e.g. {'ch1': {'value' : 10} }
    '''
    paramName = paramDict['name']     
    instrument[paramName](paramDict['value'])

def _proxyCallFunc(instrument: Instrument, funcDict : FuncDictType) -> Any:  
    '''
    Call an instrument function.
    
    :param funcDict:  the dictionary that contains the name of the function to
        call and the argument values
        
    :returns : result returned from the instrument function
    '''
    funcName = funcDict['name']
    
    if ('kwargs' in funcDict) and ('args' in funcDict):
        args = funcDict['args']
        kwargs = funcDict['kwargs']
        return getattr(instrument, funcName)(*args, **kwargs)
    elif 'args' in funcDict:
        args = funcDict['args']
        return getattr(instrument, funcName)(*args)
    elif 'kwargs' in funcDict:
        kwargs = funcDict['kwargs']
        return getattr(instrument, funcName)(**kwargs)
    else:
        return getattr(instrument, funcName)()

    


    