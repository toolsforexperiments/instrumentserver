# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
import os
import warnings
from types import MethodType
import json
import inspect
import typing
from typing import Dict, List, Any, Union, Type, Optional, Callable
from functools import partial

import zmq
from zmq.sugar.socket import Socket
import jsonpickle
from jsonschema import validate as jsvalidate

# import qcodes as qc
from qcodes.instrument.parameter import Parameter, ParameterWithSetpoints
from qcodes import Instrument, Function
from qcodes.utils.validators import Validator, Arrays
from . import getInstrumentserverPath
from .base import send, recv

PARAMS_SCHEMA_PATH = os.path.join(getInstrumentserverPath('schemas'),
                                  'instruction_dict.json')


class ModuleProxy(Instrument):
    """Prototype for a module proxy object. Each proxy instantiation 
    represents a virtual module (instrument of submodule of instrument).     
    """

    def __init__(self,
                 instrument_name: str,
                 construct_dict: Dict,
                 submodule_name: Optional[Union[str, None]] = None,
                 server_address: str = '5555'):
        """ Initialize a proxy. Create a zmq.REQ socket that connects to the
        server, get all the parameters and functions belong to this module and
        add them to this virtual module class.
    
        :param instrument_name: The name of the instrument that the proxy will
        represent. The name must match the instrument name in the server.
        
        :param construct_dict: The dictionary that contains the information of 
        the module member functions and parameters
        
        :param submodule_name: The name of the instrument submodule (is this 
         a proxy for submodule)
        
        :param server_address: the last 4 digits of the local host tcp address
        """
        super().__init__(instrument_name)
        self.parameters.pop('IDN')  # we will redefine this later
        self.submodule_name = submodule_name
        self._construct_dict = construct_dict

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:" + server_address)

        self._constructProxyFunctions()
        self._constructProxyParameters()

    # --------- helper functions for constructing proxy module ------------------
    def _constructProxyParameters(self) -> None:
        """Based on the parameter dictionary replied from server, add the 
        instrument parameters to the proxy instrument class
        """
        construct_param_dict = self._construct_dict['parameters']
        normal_params = {k: v for k, v in construct_param_dict.items()
                         if v['class'] is Parameter}
        params_with_setpoints = {k: v for k, v in construct_param_dict.items()
                                 if v['class'] is ParameterWithSetpoints}

        def _constructSingleParam(param_args_: Dict) -> None:
            """ Construct a single parameter and add to the proxy instrument
            class
            """
            try:
                param_args_['vals'] = jsonpickle.decode(param_args_['vals'])
            except TypeError:
                param_args_['vals'] = self._decodeArrayVals(param_args_['vals'])
            param_class = param_args_.pop('class')
            # param_temp = param_class(
            #     set_cmd=partial(self._setParam, param_args_['name']),
            #     get_cmd=partial(self._getParam, param_args_['name']),
            #     **param_args_
            # )
            # setattr(self, param_args_['name'], param_temp)
            self.add_parameter(
                parameter_class=param_class,
                set_cmd=partial(self._setParam, param_args_['name']),
                get_cmd=partial(self._getParam, param_args_['name']),
                **param_args_
            )

        # construct 'Parameter's first
        for param_args in normal_params.values():
            _constructSingleParam(param_args)

        # construct 'ParameterWithSetpoints'
        for param_args in params_with_setpoints.values():
            param_args['setpoints'] = [getattr(self, setpoint) for
                                       setpoint in param_args['setpoints']]
            _constructSingleParam(param_args)

    def _decodeArrayVals(self, encode_val: Dict) -> Arrays:
        """ decode the array validators (mainly the shape part).
        :param encode_val: encoded validator of an array parameter
        :returns: Array validator
        """
        val_shape = ()
        for dim in encode_val['shape']:
            if type(dim) is int:
                val_shape += (dim,)
            elif hasattr(self, dim):
                member = getattr(self, dim)
                if type(member) is Parameter:
                    val_shape += (member.get_latest,)
                else:  # function
                    val_shape += (member,)
            else:
                raise TypeError('Unsupported Array validator shape definition')
        encode_val['shape'] = val_shape
        return Arrays(**encode_val)

    def _constructProxyFunctions(self):
        """Based on the function dictionary replied from server, add the 
        instrument functions to the proxy instrument class
        """
        construct_func_dict = self._construct_dict['functions']
        self.simple_func_dict = {}  # for GUI use
        for func_name in construct_func_dict:
            func_dic = construct_func_dict[func_name]
            if 'arg_vals' in func_dic:  # old style added functions
                vals = jsonpickle.decode(func_dic['arg_vals'])
                func_temp = partial(self._validateAndCallFunc, func_name, vals)
                func_temp.__doc__ = func_dic['docstring']
            elif 'fullargspec' in func_dic:
                func_temp = self._buildFacadeFunc(func_dic)
            else:
                raise KeyError('Invalid function construction dictionary')

            self.simple_func_dict[func_name] = {
                'name': func_name,
                'signature': inspect.signature(func_temp)
            }
            setattr(self, func_name, func_temp)
            self.functions[func_name] = func_temp

    def _buildFacadeFunc(self, func_dic):
        """Build a facade function, matching the signature of the original
        instrument function.
        """
        name = func_dic['name']
        docstring = func_dic['docstring']
        spec = func_dic['fullargspec']
        sig = func_dic['signature']

        if spec.args[0] == 'self':
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
        call_args = str(tuple(sig.parameters.keys())).replace("'", '')

        facade = 'def {}{}:\n    """{}"""\n    return _proxy{}'.format(
            name, args_str, docstring, call_args)
        facade_globs = _argument_hints()
        facade_globs['_proxy'] = _proxy
        exec(facade, facade_globs)
        return facade_globs[name]

    def _getParam(self, para_name: str) -> Any:
        """ send request to the server and get the value of the parameter.
        
        :param para_name: The name of the parameter to get.
        
        :returns: the parameter value replied from the server
        """
        instructionDict = {
            'operation': 'proxy_get_param',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
            'parameter': {'name': para_name}
        }
        param_value = _requestFromServer(self.socket, instructionDict)
        return param_value

    def _setParam(self, para_name: str, value: any) -> None:
        """ send request to the server and set the value of the parameter
    
        :param value: the value to set
        """
        instructionDict = {
            'operation': 'proxy_set_param',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
            'parameter': {'name': para_name, 'value': value}
        }
        _requestFromServer(self.socket, instructionDict)

    def _validateAndCallFunc(self, func_name: str,
                             validators: List[Validator],
                             *args: Any) -> Any:
        """ validate the arguments with the provided validators first, then send
        request to the server for function call. Only used for the functions
        that are in the qcodes.instrument.function.Function class.
        
        :param funcName: The name of the function to call
        :param validators: List of validators for each argument
        :param args: A tuple that contains the value of the function arguments
        :returns: the return value of the function replied from the server
        """
        if len(args) != len(validators):
            raise TypeError(func_name + ' is missing or got extra arguments, ' +
                            str(len(validators)) + ' required')
        for i in range(len(args)):
            validators[i].validate(args[i])
        instructionDict = {
            'operation': 'proxy_call_func',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
            'function': {'name': func_name, 'args': args}
        }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value

    def _callFunc(self, func_name: str,
                  *args: Any,
                  **kwargs: Dict) -> Any:
        """ call functions that are bound methods to the instrument class.
        
        :param funcName: The name of the function to call
        :param fullargspec: Signature of the original instrument function on
            the server.
        :param args: A tuple that contains the value of the function arguments
        :returns: the return value of the function replied from the server
        """
        instructionDict = {
            'operation': 'proxy_call_func',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
            'function': {'name': func_name, 'args': args, 'kwargs': kwargs}
        }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value

    # ------------- override of the Instrument class methods --------------------
    def add_function(self, func: Optional[Callable] = None, name: str = None,
                     override: bool = False, **kwargs: Any) -> None:
        """ Bind a function to this proxy module. Can bind a function
        directly to this proxy instrument ('self' argument is also supported,
        which will point to the current proxy instrument ). The old way of
        adding a  Function class (qcodes.instrument.base.Instrument.add_function)
        is still supported, but deprecated.

        : param func: the function to be added
        : param name: name of the function, default name is the same as the
            function provided
        : param override: when set to True, the function with the same name will
            be overridden
        : param **kwargs: constructor kwargs for ``Function``

        """
        if name is None:
            if func is not None:
                name = func.__name__

        if name in self.functions and not override:
            raise KeyError('Duplicate function name {}'.format(name))

        if func is not None:  # bind function to proxy module class
            func_sig = inspect.signature(func)
            if 'self' in func_sig.parameters:
                bound_func = MethodType(func, self)
            else:
                bound_func = func
            setattr(self, name, bound_func)
            self.functions[name] = bound_func
        else:  # construct ``Function``
            warnings.warn('The qcodes Function class is deprecated, try to '
                          'bind a function directly')
            function = Function(name=name, instrument=self, **kwargs)
            self.functions[name] = function

    def get_idn(self) -> Dict[str, Optional[str]]:
        """override the get_idn function of the Instrument class
        """
        return self.IDN()

    def write_raw(self, cmd: str) -> str:
        """ override the write_raw method of the Instrument class, pass cmd to
        server

        : param cmd: The string to send to the instrument.
        """
        instructionDict = {
            'operation': 'proxy_write_raw',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
            'cmd': cmd
        }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value

    def ask_raw(self, cmd: str) -> None:
        """ override the ask_raw method of the Instrument class, pass cmd to
        server

        : param cmd: The string to send to the instrument.
        """
        instructionDict = {
            'operation': 'proxy_ask_raw',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
            'cmd': cmd
        }
        return_value = _requestFromServer(self.socket, instructionDict)
        return return_value

    # ------------- extra methods for the proxy module --------------------------
    def snapshot_from_server(self) -> Dict:
        """ send request to the server for a snapshot of the instrument.
        """
        instructionDict = {
            'operation': 'instrument_snapshot',
            'instrument_name': self.name,
            'submodule_name': self.submodule_name,
        }
        snapshot_ = _requestFromServer(self.socket, instructionDict)
        return snapshot_


class InstrumentProxy(ModuleProxy):
    """Prototype for an instrument proxy object. Each proxy instantiation 
    represents a virtual instrument. 
    
    """

    def __init__(self, instrument_name: str, server_address: str = '5555'):
        """ Initialize a proxy. Create a zmq.REQ socket that connects to the
        server, get all the functions, parameters and submodules of this
        instrument from the server and add them to this virtual instrument
        class.
    
        :param instrument_name: The name of the instrument that the proxy will
        represent. The name must match the instrument name in the server.
        :param server_address: the last 4 digits of the local host tcp address
        """
        self.context = zmq.Context()

        print("Connecting to server...")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:" + server_address)

        # check if instrument exits on the server or not 
        print("Checking instruments on the server...")
        existing_instruments = list(
            get_existing_instruments(server_address).keys())

        if instrument_name in existing_instruments:
            print('Found ' + instrument_name + ' on server')
        else:
            raise KeyError(
                'Can\'t find ' + instrument_name + ' on server. Available ' +
                'instruments are: ' + str(existing_instruments) +
                '. Check spelling or create instrument first')

        # Get all the parameters and functions from the server and add them to 
        # this virtual instrument class
        print("Setting up virtual instrument " + instrument_name + "...")
        instructionDict = {
            'operation': 'proxy_construction',
            'instrument_name': instrument_name
        }
        self._construct_dict = _requestFromServer(self.socket, instructionDict)

        # create the top instrument module
        super().__init__(instrument_name,
                         self._construct_dict,
                         None,
                         server_address)

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


# ------------ public functions in proxy package --------------------------------
def get_existing_instruments(server_address: str = '5555'):
    """ Get the existing instruments on the server

    """
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://localhost:" + server_address)
    instructionDict = {'operation': 'get_existing_instruments'}
    existing_instruments = _requestFromServer(socket, instructionDict)
    return existing_instruments


def create_instrument(instrument_class: Union[Type[Instrument], str],
                      name: str,
                      *args: Any,
                      server_address: str = '5555',
                      **kwargs: Any,
                      ) -> InstrumentProxy:
    """ create a new instrument.
    
    :param instrument_class: Class of the instrument to create or a string of 
        of the class
    :param server_address: Address of the server to connect to
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
    existing_instruments = list(get_existing_instruments(server_address).keys())
    if name in existing_instruments:
        raise NameError(f'Instrument {name} already exists on the server')
    # create new instrument
    instructionDict = {
        'operation': 'instrument_creation',
        'instrument_name': name,
        'instrument_create': {
            'instrument_class': str(instrument_class),
            'args': args,
            'kwargs': kwargs
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
    except Exception:
        raise
    # send instruction dictionary to server
    send(socket, instructionDict)
    # receive response from server and handle error
    response = recv(socket)
    if response['error'] is not None:
        error = response['error']
        print('Error from server:')
        raise error
    return_value = response['return_value']
    return return_value


def _argument_hints(package=None) -> Dict[str, object]:
    """ generate a dictionary that contains the argument hints for constructing
    the facade functions. By default, all the hint type from typing package will
    be included

    :param package: package that contains the customized hint types, the hint
    types should be stored in a dictionary called arg_hint_dict.

    :return : Dictionary that contain the hints.
    """
    arg_hint_dict = {}
    # noinspection PyUnresolvedReferences
    for obj in typing.__all__:
        if 'A' <= obj[0] <= 'Z':
            arg_hint_dict[obj] = typing.__dict__[obj]
    if package is not None:
        arg_hint_dict.update(package.arg_hint_dict)
    return arg_hint_dict
