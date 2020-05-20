# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 15:57:23 2020

@author: Chao
"""

import inspect
import warnings
from types import MethodType
from typing import Dict, Any, Union, Optional
from typing_extensions import Literal, TypedDict

import jsonpickle

import qcodes as qc
from qcodes import (Station,
                    Instrument,
                    ChannelList,
                    Parameter,
                    ParameterWithSetpoints,
                    Function)
from qcodes.instrument import parameter
from qcodes.utils.validators import Validator, Arrays

# for now, only these two types of parameter are supported, which should have
# covered most of the cases)
SUPPORTED_PARAMETER_CLASS = Union[Parameter, ParameterWithSetpoints]


# ---------------- dictionary type definition -----------------------------------
class InstrumentCreateDictType(TypedDict):
    instrument_class: str
    args: Optional[tuple]
    kwargs: Optional[Dict]


class ParamDictType(TypedDict):
    name: str
    value: Optional[Any]


class FuncDictType(TypedDict):
    name: str
    args: Optional[tuple]
    kwargs: Optional[Dict]


class InstructionDictType(TypedDict):
    operation: Literal["get_existing_instruments",
                       'instrument_creation',
                       'proxy_construction',
                       'proxy_get_param',
                       'proxy_set_param',
                       'proxy_call_func',
                       'proxy_write_raw',
                       'proxy_ask_raw',
                       'instrument_snapshot']

    instrument_name: Optional[str]  # not needed for 'get_existing_instruments'
    submodule_name: Optional[
        Union[str, None]]  # not needed for 'get_existing_instruments'
    instrument_create: Optional[
        InstrumentCreateDictType]  # for instrument creation
    parameter: Optional[ParamDictType]  # for get/set_param
    function: Optional[FuncDictType]  # for function call
    cmd: Optional[str]  # for function call


# ------------------------- interpreter function --------------------------------
def instructionDict_to_instrumentCall(station: Station,
                                      instructionDict:
                                      InstructionDictType) -> Any:
    """
    This is the interpreter function that the server will call to translate the
    dictionary received from the proxy to instrument calls.
    
    :param station: qcodes.station object, the station that contains the 
        instrument to call.
    :param instructionDict:  The dictionary passed from the instrument proxy
        that contains the information needed for the operation. 

    :returns: the results returned from the instrument call
    """
    response = {'return_value': None,
                'error': None}
    try:
        returns = _instructionProcessor(station, instructionDict)
        response['return_value'] = returns
    except Exception as err:
        response['error'] = err
        warnings.simplefilter('always', UserWarning)  # since this runs in loop
        warnings.warn(str(err))

    return response


# ------------------ helper functions -------------------------------------------
def _instructionProcessor(station: Station,
                          instructionDict: InstructionDictType):
    """
    process the operation instruction from the client and execute the operation.
    
    :param station: qcodes.station object, the station that contains the 
        instrument to call.
    :param instructionDict:  The dictionary passed from the instrument proxy
        that contains the information needed for the operation. 

    :returns: the results returned from the instrument call

    """
    operation = instructionDict['operation']
    returns = None
    if operation == 'get_existing_instruments':
        # usually this operation will be called before all the others to check
        # if the instrument already exists ont the server.
        returns = _getExistingInstruments(station)
    elif operation == 'instrument_creation':
        _instrumentCreation(station, instructionDict)
    else:  # doing operation on an existing instrument
        instrument = station[instructionDict['instrument_name']]
        if 'submodule_name' in instructionDict:
            submodule_name = instructionDict['submodule_name']
            if submodule_name is not None:
                # do operation on an instrument submodule
                instrument = getattr(instrument, submodule_name)

        if operation == 'proxy_construction':
            returns = _proxyConstruction(instrument)
        elif operation == 'proxy_get_param':
            returns = _proxyGetParam(instrument, instructionDict['parameter'])
        elif operation == 'proxy_set_param':
            _proxySetParam(instrument, instructionDict['parameter'])
        elif operation == 'proxy_call_func':
            returns = _proxyCallFunc(instrument, instructionDict['function'])
        elif operation == 'proxy_write_raw':
            returns = _proxyWriteRaw(instrument, instructionDict['cmd'])
        elif operation == 'proxy_ask_raw':
            returns = _proxyAskRaw(instrument, instructionDict['cmd'])
        elif operation == 'instrument_snapshot':
            returns = instrument.snapshot()
        else:
            # the instructionDict will be checked in the proxy before sent to
            # here, so in principle this error should not happen.
            raise TypeError('operation type not supported')
    return returns


def _getExistingInstruments(station: Station) -> Dict:
    """
    Get the existing instruments in the station,
    
    :returns : a dictionary that contains the instrument name and its identity
    """
    instrument_info = {}
    list_instruments = list(station.snapshot()['instruments'].keys())
    for instrument_name in list_instruments:
        instrument_info[instrument_name] = {}
        instrument_info[instrument_name]['name'] = instrument_name
        instrument_IDN = station[instrument_name].IDN()
        instrument_info[instrument_name]['IDN'] = instrument_IDN
    return instrument_info


def _instrumentCreation(station: Station, instructionDict: Dict) -> None:
    """Create a new instrument on the server
    """
    # TODO: Use the YAML configuration file for finding the correct package
    instrument_name = instructionDict['instrument_name']
    instrument_create_dict = instructionDict['instrument_create']
    instrument_class = instrument_create_dict['instrument_class']
    instrument_args = instrument_create_dict['args']
    instrument_kwargs = instrument_create_dict['kwargs']

    try:
        instrument_class = eval(instrument_class)
    except NameError:  # instrument class not imported yet
        separate_point = instrument_class.rfind('.')
        package_str = instrument_class[:separate_point]
        instrument_class = instrument_class[separate_point + 1:]
        exec(f'from {package_str} import {instrument_class}')
        instrument_class = eval(instrument_class)

    new_instrument = qc.find_or_create_instrument(instrument_class,
                                                  instrument_name,
                                                  *instrument_args,
                                                  recreate=False,
                                                  **instrument_kwargs)
    print(new_instrument)
    if instrument_name not in station.components:
        station.add_component(new_instrument)


def _proxyConstruction(instrument: Instrument) -> Dict:
    """
    Get the dictionary that describes the instrument.
    This parameter part is similar to the qcodes snapshot of the instrument,
    but with less information, also the string that describes the validator of
    each parameter/argument is replaced with a jsonpickle encoded form so that
    it is easier to reproduce the validator object in the proxy.
    The functions are directly extracted from the instrument class.

    :returns : a dictionary that describes the instrument

    """
    # get functions and parameters belong to the top instrument
    construct_dict = _get_module_info(instrument)
    # get functions and parameters belong to the submodule
    try:
        submodules = list(instrument.submodules.keys())
    except AttributeError:
        submodules = []

    submodule_dict = {}
    for module_name in submodules:
        submodule = getattr(instrument, module_name)
        # the ChannelList is not supported yet
        if submodule.__class__ != ChannelList:
            submodule_dict[module_name] = _get_module_info(submodule)

    construct_dict['submodule_dict'] = submodule_dict
    return construct_dict


def _encodeArrayVals(param_vals: Arrays) -> Dict:
    """ encode the array validators to a serializable format. This function is
    necessary when the shape of the array validator contains a callable (another
    parameter or a function) who belongs to an instrument class, which should
    not be directly pickled.

    :param param_vals: array validator of a parameter

    :returns: A dictionary contains the encoded validator
    """
    encode_val = {"min_value": param_vals._min_value,
                  "max_value": param_vals._max_value,
                  "valid_types": param_vals.valid_types
                  }
    encode_val_shape = []
    for dim in param_vals._shape:
        # some possible ways of defining array validator shape in drivers.
        # only parameters or functions of the same instrument are supported
        if type(dim) is int:
            encode_val_shape.append(dim)
        elif isinstance(dim, Parameter) or isinstance(dim, parameter.GetLatest):
            encode_val_shape.append(dim.name)
        elif isinstance(dim, parameter._Cache):
            encode_val_shape.append(dim._parameter.name)
        elif type(dim) is MethodType:  # instrument function
            encode_val_shape.append(dim.__name__)
        else:
            raise TypeError('Unsupported way of defining the shape of array '
                            'validator, try to use one of the followings:\n'
                            '1) a constant int\n'
                            '2) a parameter in the same instrument\n'
                            '   2a) self.parameter\n'
                            '   2b) self.parameter.get_latest\n'
                            '   2c) self.parameter.cache\n'
                            '3) a function in the same instrument\n'
                            )
        encode_val['shape'] = encode_val_shape
    return encode_val


def _get_module_info(module: Instrument) -> Dict:
    """ Get the parameters and functions of an instrument (sub)module and put
    them a dictionary.
    """
    # get parameters
    param_names = list(module.__dict__['parameters'].keys())
    module_param_dict = {}
    for param_name in param_names:
        param: SUPPORTED_PARAMETER_CLASS = module[param_name]
        param_dict_temp = {'name': param_name}
        param_class = param.__class__
        if param_class not in SUPPORTED_PARAMETER_CLASS.__args__:
            raise TypeError(f"{param} is not supported yet, the current "
                            f"supported parameter classes are "
                            f"{SUPPORTED_PARAMETER_CLASS.__args__}")

        if param_class is ParameterWithSetpoints:
            param_dict_temp['setpoints'] = [setpoint.name for setpoint in
                                            param.setpoints]

        param_vals: Union[Validator, Arrays] = param.vals
        try:  # directly pickle
            param_dict_temp['vals'] = jsonpickle.encode(param_vals)
        except RuntimeError:  # contains instrument class which cannot be pickled
            if type(param_vals) is Arrays:
                # Array validator is necessary for ParameterWithSetpoints
                param_dict_temp['vals'] = _encodeArrayVals(param_vals)
            else:  # otherwise, give up validation on proxy parameters
                param_dict_temp['vals'] = jsonpickle.encode(None)

        # some extra items are added here to support the snapshot in the proxy
        # instrument class
        param_dict_temp['class'] = param_class
        param_dict_temp['unit'] = param.unit
        param_dict_temp['snapshot_value'] = param._snapshot_value
        param_dict_temp['snapshot_exclude'] = param.snapshot_exclude
        param_dict_temp['max_val_age'] = param.cache._max_val_age
        param_dict_temp['docstring'] = param.__doc__
        module_param_dict[param_name] = param_dict_temp

    # get functions
    methods = set(dir(module))
    base_methods = (dir(base) for base in module.__class__.__bases__)
    unique_methods = methods.difference(*base_methods)
    func_names = []
    for method in unique_methods:
        if callable(
                getattr(module, method)) and method not in module_param_dict:
            func_names.append(method)

    module_func_dict = {}
    for func_name in func_names:
        func_dict_temp = {'name': func_name}
        func = getattr(module, func_name)
        func_dict_temp['docstring'] = func.__doc__

        if func.__class__ == Function:
            # for functions added using the old 'instrument.add_function'
            # method, (the functions only have positional arguments, and each
            # argument has a validator). In this case, the list of validators
            # is pickled
            func_dict_temp['arg_vals'] = jsonpickle.encode(func._args)
        else:
            # for functions added directly to instrument class as bound
            # methods, the fullargspec and signature is stored in the
            # dictionary(will be pickled when sending to proxy)(
            # jsonpickle.en/decode has some bugs that don't worked for some
            # function signatures)
            jp_fullargspec = inspect.getfullargspec(func)
            jp_signature = inspect.signature(func)
            func_dict_temp['fullargspec'] = jp_fullargspec
            func_dict_temp['signature'] = jp_signature
        module_func_dict[func_name] = func_dict_temp
    module_construct_dict = {'functions': module_func_dict,
                             'parameters': module_param_dict}

    return module_construct_dict


def _proxyGetParam(instrument: Instrument, paramDict: ParamDictType) -> Any:
    """
    Get a parameter from the instrument.

    :param paramDict: the dictionary that contains the parameter to change, the
        'value' item will be omitted.
    :returns : value of the parameter returned from instrument

    """
    paramName = paramDict['name']
    return instrument[paramName]()


def _proxySetParam(instrument: Instrument, paramDict: ParamDictType) -> None:
    """
    Set a parameter in the instrument.

    :param paramDict:  the dictionary that contains the parameter to change, the
        'value' item will be the set value.
        e.g. {'ch1': {'value' : 10} }
    """
    paramName = paramDict['name']
    instrument[paramName](paramDict['value'])


def _proxyCallFunc(instrument: Instrument, funcDict: FuncDictType) -> Any:
    """
    Call an instrument function.

    :param funcDict:  the dictionary that contains the name of the function to
        call and the argument values

    :returns : result returned from the instrument function
    """
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


def _proxyWriteRaw(instrument: Instrument, cmd: str) -> Union[str, None]:
    return instrument.write_raw(cmd)


def _proxyAskRaw(instrument: Instrument, cmd: str) -> Union[str, None]:
    return instrument.ask_raw(cmd)