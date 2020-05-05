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

class InstrumentCreateDictType(TypedDict):
    instrument_class : str
    args : Optional[tuple]
    kwargs : Optional[Dict]

    
class ParamDictType(TypedDict):
    name :  str
    value : Optional[Any] 
    
class FuncDictType(TypedDict):
    name :  str
    args : Optional[tuple]
    kwargs : Optional[Dict]

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
    submodule_name: Optional[Union[str, None]]  # not needed for 'get_existing_instruments'
    instrumnet_create : Optional[InstrumentCreateDictType]  # for instrument creation
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
        if 'submodule_name' in instructionDict :
            submodule_name = instructionDict['submodule_name']
            if submodule_name is not None:
                # do operation on an instrument submodule
                instrument = getattr(instrument, submodule_name)            
        
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
    """Create a new instrument on the server
    """
    instrument_name = instructionDict['instrument_name']
    instrumnet_create_dict = instructionDict['instrumnet_create']    
    instrument_class = instrumnet_create_dict['instrument_class']
    instrument_args = instrumnet_create_dict['args']
    instrument_kwargs = instrumnet_create_dict['kwargs']
    
    try:
        instrument_class = eval(instrument_class)
    except NameError:
        exec( f'import {instrument_class}' )
        instrument_class = eval(instrument_class)
    

    # print (instrument_class, instrument_name, instrument_args, instrument_recreate, instrument_kwargs)        
    new_instruemnt = qc.find_or_create_instrument(instrument_class,
                                                  instrument_name,
                                                  *instrument_args,
                                                  recreate = False,
                                                  **instrument_kwargs)
    print (new_instruemnt)
    if not instrument_name in station.components:
        station.add_component(new_instruemnt)
    

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
    # get functions and parameters belong to the top instrument
    construct_dict = _get_module_info(instrument)
    # get functions and parameters belong to the submodule
    try:
        submodules = list(instrument.submodules.keys())
    except AttributeError:
        pass
    
    for module_name in submodules: 
        submodule = getattr(instrument, module_name)
        # the ChannelList is not supported yet
        if submodule.__class__ != qc.instrument.channel.ChannelList:
            construct_dict[module_name] = _get_module_info(submodule)
    return construct_dict
    
    
def _get_module_info(module: Instrument) -> Dict:
    ''' Get the parameters and functions of an instrument (sub)module and put 
    them a dictionary.
    '''
    # get paramaters
    param_names = list(module.__dict__['parameters'].keys())
    module_param_dict = {}    
    for param_name in param_names:
        param_dict_temp = {}
        param_dict_temp['name'] = param_name
        try:
            param_dict_temp['unit'] = module[param_name].unit        
        except AttributeError:
            param_dict_temp['unit'] = None
          
        try:
            param_dict_temp['vals'] = jsonpickle.encode(module[param_name].vals) 
        except:
            param_dict_temp['vals'] = None
        module_param_dict[param_name] = param_dict_temp

    # get fucntions 
    methods = set(dir(module))
    base_methods = (dir(base) for base in module.__class__.__bases__)
    unique_methods = methods.difference(*base_methods)
    func_names = []
    for method in unique_methods :
        if callable(getattr(module, method)) and method not in module_param_dict:
            func_names.append(method)
  
    module_func_dict = {}
    for func_name in func_names:
        func_dict_temp = {}
        func_dict_temp['name'] = func_name
        func = getattr(module , func_name)
        func_dict_temp['docstring'] = func.__doc__

        if func.__class__ == qc.instrument.function.Function:
        # for functions added using the old 'instruemnt.add_function' method,
        # (the functions only have positional arguments, and each argument has
        # a validator). In this case, the list of validators is pickled            
            jp_argvals = jsonpickle.encode(func._args)
            func_dict_temp['arg_vals'] = jp_argvals            
        else:
        # for functions added directly to instrument class as bound methods,
        # the fullargspec and signature is pickled             
            jp_fullargspec = jsonpickle.encode(inspect.getfullargspec(func))
            jp_signature = jsonpickle.encode(inspect.signature(func))
            func_dict_temp['fullargspec'] = jp_fullargspec 
            func_dict_temp['signature'] = jp_signature                     
        module_func_dict[func_name] = func_dict_temp        
    module_construct_dict = {'functions' : module_func_dict,
                             'parameters' : module_param_dict}        
    return module_construct_dict
    
    
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

    


    