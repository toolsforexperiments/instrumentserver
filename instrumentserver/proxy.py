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
import logging
from dataclasses import dataclass, asdict

import zmq
from zmq.sugar.socket import Socket


# import qcodes as qc
from qcodes.instrument.parameter import Parameter
from qcodes import Instrument
from qcodes.utils.validators import Validator, Arrays
from qcodes.utils.metadata import Metadatable

from instrumentserver.server.core import(ServerInstruction,
                                         InstrumentModuleBluePrint,
                                         ParameterBluePrint,
                                         MethodBluePrint,
                                         CallSpec,
                                         Operation,
                                         InstrumentCreationSpec)


from client import sendRequest

logger = logging.getLogger(__name__)

class ModuleProxy(Instrument):
    """Prototype for a module proxy object. Each proxy instantiation 
    represents a virtual module (instrument of submodule of instrument).     
    """

    def __init__(self,
                 instrument_name: str,
                 module_blue_print: InstrumentModuleBluePrint,
                 submodule_name: Optional[Union[str, None]] = None,
                 host = 'localhost',
                 port = 5555):
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

        self.host = host
        self.port = port

        self.submodule_name = submodule_name
        self.bp = module_blue_print

        self._addProxyMethods()
        self._addProxyParameters()



    # --------- helper functions for constructing proxy module ------------------
    def _addProxyParameters(self) -> None:
        """Based on the parameter blueprint replied from server, add the
        instrument parameters to the proxy instrument class
        """
        param_bps = self.bp.parameters
        normal_params = [pbp for pbp in param_bps.values()
                         if pbp.setpoints is None]
        params_with_setpoints = [pbp for pbp in param_bps.values()
                                 if pbp.setpoints is not None]

        # construct and add normal parameters first
        for pbp in normal_params:
            self.parameters[pbp.name] = ProxyParameter(pbp,
                                                       host=self.host,
                                                       port=self.port)

        # construct and add 'ParameterWithSetpoints'
        for pbp in params_with_setpoints:
            self.parameters[pbp.name] = ProxyParameter(pbp,
                                                       host=self.host,
                                                       port=self.port,
                                                       setpoints_instrument=self)



    def _addProxyMethods(self):
        """Based on the method blue print replied from server, add the
        instrument functions to the proxy instrument class
        """
        method_bps = self.bp.methods
        for mbp in method_bps.values():
            func_temp = constructProxyMethod(mbp, self.host, self.port)
            setattr(self, mbp.name, func_temp)
            self.functions[mbp.name] = func_temp


    # ------------- override of the Instrument class methods --------------------
    '''
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
            func.snapshot = partial(self._funcSnapshot, func)
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

'''
    # ------------- extra methods for the proxy module --------------------------


class InstrumentProxy(ModuleProxy):
    """Prototype for an instrument proxy object. Each proxy instantiation 
    represents a virtual instrument. 
    
    """

    def __init__(self, instrument_name: str,
                 host = 'localhost',
                 port = 5555):
        """ Initialize a proxy. Create a zmq.REQ socket that connects to the
        server, get all the functions, parameters and submodules of this
        instrument from the server and add them to this virtual instrument
        class.
    
        :param instrument_name: The name of the instrument that the proxy will
        represent. The name must match the instrument name in the server.
        :param server_address: the last 4 digits of the local host tcp address
        """


        # check if instrument exits on the server or not 
        print("Checking instruments on the server...")
        existing_instruments = list(
            get_existing_instruments(host,port).keys())

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

        req = ServerInstruction(
            operation=Operation.get_instrument_blueprint,
            requested_instrument=instrument_name
        )
        self.bp = sendRequest(req).message


        # create the top instrument module
        super().__init__(instrument_name,
                         self.bp,
                         )
'''
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
'''


class ProxyParameter(Parameter):
    ''' proxy for parameters

    :param bp: blue print of the parameter
    :param args: positional arguments for  qcodes.Parameter constructor
    :param host: host of the server where the parameter lives
    :param port: port of the server where the parameter lives
    :param setpoints_instrument: For parameters with setpoints only.
        Instrument that the setpoints parameter belongs to. This allows
        creating parameters whose setpoints are from other instructs.]
    :param kwargs: keyword arguments for qcodes.Parameter constructor

    '''
    def __init__(self, bp: ParameterBluePrint, *args,
                 host='localhost', port=5555,
                 setpoints_instrument: Instrument = None, **kwargs):
        self.path = bp.path
        self._bp = bp
        self.serverPort = port
        self.serverHost = host
        self.askServer = partial(sendRequest, host=self.serverHost, port=self.serverPort)

        if bp.settable:
            set_cmd = self._remoteSet
        else:
            set_cmd = False
        if bp.gettable:
            get_cmd = self._remoteGet
        else:
            get_cmd = False

        constructor_args = self._constructorArgsFromBluePrint()
        constructor_args.update(kwargs) # extra kwargs
        super().__init__(*args, set_cmd=set_cmd, get_cmd=get_cmd, **constructor_args)
        if bp.setpoints is not None and setpoints_instrument is not None:
            setpoints =[getattr(setpoints_instrument, setpoint) for
                        setpoint in bp.setpoints]
            setattr(self, 'setpoints', setpoints)


    def _constructorArgsFromBluePrint(self) -> Dict[str, Any]:
        ''' get the keyword arguments from parameter blue print for Parameter
        construction.
        '''
        constructor_args = asdict(self._bp)
        keys_to_remove = ['path', 'base_class', 'parameter_class',
                          'gettable', 'settable', 'setpoints']
        for key in keys_to_remove:
            del constructor_args[key]
        return constructor_args

    def _remoteSet(self, value: Any):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.path,
                args=(value,)
            )
        )
        return self.askServer(msg).message

    def _remoteGet(self):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.path,
            )
        )
        return self.askServer(msg).message


def constructProxyMethod( bp: MethodBluePrint,
                            host:str ='localhost', port=5555):
    """Construct a proxy function, matching the signature given in the blueprint

    :param bp: blue print of the method
    :param host: host of the server where the method lives
    :param port: port of the server where the method lives
    """

    askServer = partial(sendRequest, host=host, port=port)

    def func_snapshot(**kwargs: Any) -> Dict:
        snap = {"signature": str(bp.call_signature)}
        return snap

    def _remoteFuncCall(*args: Any, **kwargs: Dict) -> Any:
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=bp.path,
                args=args,
                kwargs=kwargs
            )
        )
        return askServer(msg).message

    name = bp.name
    docstring = bp.doc
    sig = bp.call_signature
    spec = bp.full_arg_spec

    args_str = str(sig)
    call_args = spec[0].copy()
    if 'self' in call_args:
        call_args.remove('self')
    if spec[1] is not None:
        call_args.append(f'*{spec[1]}')
    if spec[4] is not None:
        call_args += [f'{kwonly}={kwonly}' for kwonly in spec[4]]
    if spec[2] is not None:
        call_args.append(f'**{spec[2]}')

    call_args = str(tuple(call_args)).replace("'", '')

    facade = 'def {}{}:\n    """{}"""\n    return _remoteFuncCall{}'.format(
        name, args_str, docstring, call_args)
    facade_globs = _argument_hints()
    facade_globs['_remoteFuncCall'] = _remoteFuncCall
    exec(facade, facade_globs)
    proxy_func = facade_globs[name]
    proxy_func.snapshot = func_snapshot

    return facade_globs[name]


def get_existing_instruments(host='localhost', port=5555):
    """ Get the existing instruments on the server

    """
    msg = ServerInstruction(operation=Operation.get_existing_instruments)
    existing_instruments = sendRequest(msg, host, port).message
    return existing_instruments


def create_instrument(instrument_class:  str,
                      name: str,
                      *args: Any,
                      host='localhost',
                      port=5555,
                      **kwargs: Any,
                      ) -> InstrumentProxy:
    """ create a new instrument.
    
    :param instrument_class: Class of the instrument to create or a string of 
        of the class
    :param server_address: Address of the server to connect to
    :param name: Name of the new instrument
    :returns: a new virtual instrument
    """
    req = ServerInstruction(
        operation=Operation.create_instrument,
        create_instrument_spec=InstrumentCreationSpec(
            instrument_class=instrument_class,
            name=name,
            args=args,
            kwargs = kwargs
        )
    )
    ret = sendRequest(req, host, port).message
    return InstrumentProxy(name, host, port)


# ------------------ helper functions ----------------------------------------
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
