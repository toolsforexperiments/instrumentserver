# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""

from types import MethodType
import typing
from typing import Dict, List, Any, Union, Type, Optional, Callable
from functools import partial
import logging
import inspect
import warnings
from dataclasses import dataclass, asdict

# import qcodes as qc
from qcodes.instrument.parameter import Parameter
from qcodes import Instrument, Function

from instrumentserver.server.core import (ServerInstruction,
                                          InstrumentModuleBluePrint,
                                          ParameterBluePrint,
                                          MethodBluePrint,
                                          CallSpec,
                                          Operation,
                                          InstrumentCreationSpec)

from client import sendRequest

logger = logging.getLogger(__name__)


class ProxyBase:
    """ A simple base class for proxy objects
    :param bp: The blue print to construct the proxy object
    :param host: the name of the host where the server lives
    :param port: the port number of the server
    """

    def __init__(self,
                 bp: Union[None, InstrumentModuleBluePrint,
                           ParameterBluePrint, MethodBluePrint] = None,
                 host='localhost',
                 port=5555):
        self.bp = bp
        self.host = host
        self.port = port
        self.askServer = partial(sendRequest, host=self.host, port=self.port)


class ProxyParameter(Parameter, ProxyBase):
    """ proxy for parameters.
    :param bp: blue print of the parameter
    :param args: positional arguments for  qcodes.Parameter constructor
    :param host: host name of the server where the parameter lives
    :param port: port of the server where the parameter lives
    :param setpoints_instrument: For parameters with setpoints only.
        Instrument that the setpoints parameter belongs to. This allows
        creating parameters whose setpoints are from other instructs.]
    :param kwargs: keyword arguments for qcodes.Parameter constructor
    """

    def __init__(self, bp: ParameterBluePrint, *args,
                 host='localhost', port=5555,
                 setpoints_instrument: Instrument = None, **kwargs):
        self.path = bp.path
        ProxyBase.__init__(self, bp, host, port)
        if bp.settable:
            set_cmd = self._remoteSet
        else:
            set_cmd = False
        if bp.gettable:
            get_cmd = self._remoteGet
        else:
            get_cmd = False

        param_ctor_args = self._paramCtorArgsFromBluePrint()
        param_ctor_args.update(kwargs)  # extra kwargs
        Parameter.__init__(self, *args, set_cmd=set_cmd, get_cmd=get_cmd,
                           **param_ctor_args)

        # add setpoints to parameter who was ParameterWithSetpoints
        if bp.setpoints is not None and setpoints_instrument is not None:
            setpoints = [getattr(setpoints_instrument, setpoint) for
                         setpoint in bp.setpoints]
            setattr(self, 'setpoints', setpoints)

    def _paramCtorArgsFromBluePrint(self) -> Dict[str, Any]:
        """ get the keyword arguments of Parameter constructor from parameter
            blue print.
        """
        constructor_args = asdict(self.bp)
        keys_to_remove = ['path', 'base_class', 'parameter_class',
                          'gettable', 'settable', 'setpoints']
        for key in keys_to_remove:
            del constructor_args[key]  # will not change self.bp
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


class ProxyModule(Instrument, ProxyBase):
    """Construct a proxy module using the given blue print. Each proxy
    instantiation represents a virtual module (instrument of submodule of
    instrument).
    :param module_blue_print: The blue print that the describes the module
    :param host: the name of the host where the server lives
    :param port: the port number of the server
    """

    def __init__(self,
                 module_blue_print: InstrumentModuleBluePrint,
                 host='localhost',
                 port=5555):
        self.module_name = module_blue_print.name
        Instrument.__init__(self, self.module_name)
        ProxyBase.__init__(self, module_blue_print, host, port)
        self.parameters.pop('IDN')  # we will redefine this later

        self._addProxyParameters()
        self._addProxyMethods()
        self._addProxySubmodules()

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
            func_temp = construct_proxy_method(mbp, self.host, self.port)
            setattr(self, mbp.name, func_temp)
            self.functions[mbp.name] = func_temp

    def _addProxySubmodules(self):
        """Based on the submodule blue print replied from server, add the proxy
        submodules to the proxy module class
        """
        submodule_bps = self.bp.submodules
        if submodule_bps is not None:
            for sbp in submodule_bps.values():
                submodule = ProxyModule(sbp, self.host, self.port)
                self.add_submodule(sbp.name, submodule)

    # ------------- override of the Instrument class methods --------------------
    def add_function(self, func: Optional[Callable] = None, name: str = None,
                     override: bool = False, **kwargs: Any) -> None:
        """ Bind a function to this proxy module. This will not add function
        to the real instrument on server! Can bind a  function directly to this
        proxy instrument ('self' argument is also supported, which will point
        to the current proxy instrument ). The old way of adding a  Function
        class ( qcodes.instrument.base.Instrument.add_function) is still
        supported, but deprecated.

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
            func.snapshot = partial(_func_snapshot, func)
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
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.bp.path + '.write_raw',
                args=cmd
            )
        )
        return self.askServer(msg).message

    def ask_raw(self, cmd: str) -> None:
        """ override the ask_raw method of the Instrument class, pass cmd to
        server

        : param cmd: The string to send to the instrument.
        """
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.bp.path + '.ask_raw',
                args=cmd
            )
        )
        return self.askServer(msg).message


class ProxyInstrument(ProxyModule):
    """Construct a instrument proxy. Each proxy instantiation represents a
    virtual instrument.

    :param instrument_name: The name of the instrument that the proxy will
        represent. The name must match the instrument name in the server.
    :param host: the name of the host where the server lives
    :param port: the port number of the server
    """

    def __init__(self, instrument_name: str,
                 host='localhost',
                 port=5555):
        """
        Find the instrument of the given name from server, get all the blue print
        for all the functions, parameters and submodules of this instrument and
        add them to this virtual instrument class.
        """

        # check if instrument exits on the server
        logger.info("Checking instruments on the server...")
        existing_instruments = list(
            get_existing_instruments(host, port).keys())
        if instrument_name in existing_instruments:
            logger.info('Found ' + instrument_name + ' on server')
        else:
            raise KeyError(
                'Can\'t find ' + instrument_name + ' on server. Available ' +
                'instruments are: ' + str(existing_instruments) +
                '. Check spelling or create instrument first')

        # Get the blue print for the instrument,
        logger.info("Setting up virtual instrument " + instrument_name + "...")
        req = ServerInstruction(
            operation=Operation.get_instrument_blueprint,
            requested_instrument=instrument_name
        )
        instrument_bp = sendRequest(req).message
        # create the instrument module
        super().__init__(instrument_bp, host, port)


def construct_proxy_method(bp: MethodBluePrint,
                           host: str = 'localhost', port=5555) -> Callable:
    """Construct a proxy function, matching the signature given in the blueprint

    :param bp: blue print of the method
    :param host: host name of the server where the method lives
    :param port: port of the server where the method lives

    :returns : proxy function based on the given blueprint
    """

    askServer = partial(sendRequest, host=host, port=port)

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
    call_args = spec[0].copy()  # args
    if 'self' in call_args:
        call_args.remove('self')
    if spec[1] is not None:  # varargs
        call_args.append(f'*{spec[1]}')
    if spec[4] is not None:  # kwonlyargs
        call_args += [f'{kwonly}={kwonly}' for kwonly in spec[4]]
    if spec[2] is not None:  # varkw
        call_args.append(f'**{spec[2]}')

    call_args = str(tuple(call_args)).replace("'", '')

    facade = 'def {}{}:\n    """{}"""\n    return _remoteFuncCall{}'.format(
        name, args_str, docstring, call_args)
    facade_globs = _argument_hints()
    facade_globs['_remoteFuncCall'] = _remoteFuncCall
    exec(facade, facade_globs)
    proxy_func = facade_globs[name]
    proxy_func.snapshot = partial(_func_snapshot, proxy_func)
    return proxy_func


def get_existing_instruments(host='localhost', port=5555):
    """ Get the existing instruments on the server
    """
    msg = ServerInstruction(operation=Operation.get_existing_instruments)
    existing_instruments = sendRequest(msg, host, port).message
    return existing_instruments


def create_instrument(instrument_class: str,
                      name: str,
                      *args: Any,
                      host='localhost',
                      port=5555,
                      **kwargs: Any,
                      ) -> ProxyInstrument:
    """ create a new instrument on the server and return a proxy for the new
    instrument.

    :param instrument_class: Class of the instrument to create or a string of 
        of the class
    :param name: Name of the new instrument
    :param args: Positional arguments for new instrument instantiation
    :param host: host name of the server where the method lives
    :param port: port of the server where the method lives
    :param kwargs: Keyword arguments for new instrument instantiation

    :returns: a new virtual instrument
    """
    req = ServerInstruction(
        operation=Operation.create_instrument,
        create_instrument_spec=InstrumentCreationSpec(
            instrument_class=instrument_class,
            name=name,
            args=args,
            kwargs=kwargs
        )
    )
    sendRequest(req, host, port)
    return ProxyInstrument(name, host, port)


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


def _func_snapshot(func: Callable, **kwargs: Any) -> Dict:
    """ get the snapshot of a function. For now, this will return the signature

    :param kwargs:
    :return:
    """
    sig = inspect.signature(func)
    snap = {"signature": str(sig)}
    return snap
