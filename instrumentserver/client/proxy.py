# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""

from typing import *
import logging
import inspect
from types import MethodType

from qcodes import Instrument, Parameter

from instrumentserver import DEFAULT_PORT
from instrumentserver.server.core import (
    ServerInstruction,
    InstrumentModuleBluePrint,
    ParameterBluePrint,
    MethodBluePrint,
    CallSpec,
    Operation,
    InstrumentCreationSpec
)
from .core import sendRequest, BaseClient


logger = logging.getLogger(__name__)


# TODO: enable creation of instruments through yaml files/station configurator.
# TODO: support for channel lists
# TODO: support for other parameter classes.


class ProxyMixin:
    """ A simple mixin class for proxy objects."""

    def __init__(self, *args,
                 cli: Optional["Client"] = None,
                 host: Optional[str] = 'localhost',
                 port: Optional[int] = DEFAULT_PORT,
                 remotePath: Optional[str] = None,
                 bluePrint: Optional[Union[ParameterBluePrint,
                                           InstrumentModuleBluePrint,
                                           MethodBluePrint]] = None,
                 **kwargs):

        self.cli = cli
        self.host = host
        self.port = port

        if remotePath is not None and bluePrint is None:
            self.remotePath = remotePath
            self.bp = self._getBluePrintFromServer(self.remotePath)
        elif bluePrint is not None:
            self.bp = bluePrint
            self.remotePath = self.bp.path
        else:
            raise ValueError("Either `remotePath` or `bluePrint` must be "
                             "specified.")

        kwargs.update(self.initKwargsFromBluePrint(self.bp))
        super().__init__(*args, **kwargs)
        self.__doc__ = self.bp.docstring

    def initKwargsFromBluePrint(self, bp):
        raise NotImplementedError

    def askServer(self, message: ServerInstruction):
        if self.cli is not None:
            return self.cli.ask(message)
        elif self.host is not None and self.port is not None:
            return sendRequest(message, self.host, self.port)

    def _getBluePrintFromServer(self, path):
        req = ServerInstruction(
            operation=Operation.get_blueprint,
            requested_path=path
        )
        return self.askServer(req)

    def snapshot(self, *args, **kwargs):
        req = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.remotePath+'.snapshot', args=args, kwargs=kwargs
            )
        )
        return self.askServer(req)


class ProxyParameter(ProxyMixin, Parameter):
    """proxy for parameters.

    :param cli: instance of `Client`
    :param name: the parameter name
    :param host: the name of the host where the server lives
    :param port: the port number of the server
    :param remotePath: path of the remote object on the server.
    :param bp: The blue print to construct the proxy parameter.
        if `remotePath` and `bluePrint` are both supplied, the blue print takes
        priority.
    """
    def __init__(self, name: str, *args,
                 cli: Optional["Client"] = None,
                 host: Optional[str] = 'localhost',
                 port: Optional[int] = DEFAULT_PORT,
                 remotePath: Optional[str] = None,
                 bluePrint: Optional[ParameterBluePrint] = None,
                 setpoints_instrument: Optional[Instrument] = None,
                 **kwargs):

        super().__init__(name, *args, cli=cli, host=host, port=port,
                         remotePath=remotePath, bluePrint=bluePrint,
                         **kwargs)

        # add setpoints to parameter if we deal with ParameterWithSetpoints
        if self.bp.setpoints is not None and setpoints_instrument is not None:
            setpoints = [getattr(setpoints_instrument, setpoint) for
                         setpoint in self.bp.setpoints]
            setattr(self, 'setpoints', setpoints)

    def initKwargsFromBluePrint(self, bp):
        kwargs = {}
        if bp.settable:
            kwargs['set_cmd'] = self._remoteSet
        else:
            kwargs['set_cmd'] = False
        if bp.gettable:
            kwargs['get_cmd'] = self._remoteGet
        else:
            kwargs['get_cmd'] = False
        kwargs['unit'] = bp.unit
        kwargs['vals'] = bp.vals
        kwargs['docstring'] = bp.docstring
        return kwargs

    def _remoteSet(self, value: Any):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.remotePath,
                args=(value,)
            )
        )
        return self.askServer(msg)

    def _remoteGet(self):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=self.remotePath,
            )
        )
        return self.askServer(msg)


class ProxyInstrumentModule(ProxyMixin, Instrument):
    """Construct a proxy module using the given blue print. Each proxy
    instantiation represents a virtual module (instrument of submodule of
    instrument).

    :param module_blue_print: The blue print that the describes the module
    :param host: the name of the host where the server lives
    :param port: the port number of the server
    """

    def __init__(self, name: str, *args,
                 cli: Optional["Client"] = None,
                 host: Optional[str] = 'localhost',
                 port: Optional[int] = DEFAULT_PORT,
                 remotePath: Optional[str] = None,
                 bluePrint: Optional[InstrumentModuleBluePrint] = None,
                 **kwargs):

        super().__init__(name, *args, cli=cli, host=host, port=port,
                         remotePath=remotePath, bluePrint=bluePrint, **kwargs)

        self.parameters.pop('IDN')  # we will redefine this later
        self._addProxyParameters()
        self._addProxyMethods()
        self._addProxySubmodules()

    def initKwargsFromBluePrint(self, bp):
        return {}

    def _addProxyParameters(self) -> None:
        """Based on the parameter blueprint replied from server, add the
        instrument parameters to the proxy instrument class"""

        # note: we can always provide setpoints_instruments, because in case
        # the parameter doesn't, `setpoints` will just be `None`.
        for pn, p in self.bp.parameters.items():
            self.parameters[pn] = ProxyParameter(
                pn, cli=self.cli, host=self.host, port=self.port,
                bluePrint=p, setpoints_instrument=self)

    def _addProxyMethods(self):
        """Based on the method blue print replied from server, add the
        instrument functions to the proxy instrument class
        """
        for n, m in self.bp.methods.items():
            fun = self._makeProxyMethod(m)
            setattr(self, n, MethodType(fun, self))
            self.functions[n] = getattr(self, n)

    def _makeProxyMethod(self, bp: MethodBluePrint):
        def wrap(*a, **k):
            msg = ServerInstruction(
                operation=Operation.call,
                call_spec=CallSpec(target=bp.path, args=a, kwargs=k)
            )
            return self.askServer(msg)

        sig = bp.call_signature
        args = []
        for pn in sig.parameters:
            if sig.parameters[pn].kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                              inspect.Parameter.POSITIONAL_ONLY]:
                args.append(f'{pn}')
            elif sig.parameters[pn].kind is inspect.Parameter.VAR_POSITIONAL:
                args.append(f"*{pn}")
            elif sig.parameters[pn].kind is inspect.Parameter.KEYWORD_ONLY:
                args.append(f"{pn}={pn}")
            elif sig.parameters[pn].kind is inspect.Parameter.VAR_KEYWORD:
                args.append(f"**{pn}")

        # we need to add a `self` argument because we want this to be a bound
        # method of the instrument instance.
        sig_str = str(sig)
        sig_str = sig_str[0] + 'self, ' + sig_str[1:]
        new_func_str = f"""def {bp.name}{sig_str}:
        return wrap({', '.join(args)})"""

        # make sure the method knows the wrap function.
        globs = {'wrap': wrap}
        exec(new_func_str, globs)
        fun = globs[bp.name]
        fun.__doc__ = bp.docstring
        return globs[bp.name]

    def _addProxySubmodules(self):
        """Based on the submodule blue print replied from server, add the proxy
        submodules to the proxy module class
        """
        if self.bp.submodules is not None:
            for sn, s in self.bp.submodules.items():
                submodule = ProxyInstrumentModule(
                    s.name, cli=self.cli, host=self.host, port=self.port, bluePrint=s)
                self.add_submodule(sn, submodule)

ProxyInstrument = ProxyInstrumentModule


class Client(BaseClient):
    """Client with common server requests as convenience functions."""

    def list_instruments(self):
        """ Get the existing instruments on the server
        """
        msg = ServerInstruction(operation=Operation.get_existing_instruments)
        return self.ask(msg)

    def create_instrument(self, instrument_class: str, name: str,
                          *args: Any, **kwargs: Any) -> ProxyInstrumentModule:
        """ create a new instrument on the server and return a proxy for the new
        instrument.

        :param instrument_class: Class of the instrument to create or a string of
            of the class
        :param name: Name of the new instrument
        :param args: Positional arguments for new instrument instantiation
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
        _ = self.ask(req)
        return ProxyInstrumentModule(name=name, cli=self, remotePath=name)

    def close_instrument(self, instrument_name: str):
        self.call('close_and_remove_instrument', instrument_name)

    def call(self, target, *args, **kwargs):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target=target,
                args=args,
                kwargs=kwargs,
            )
        )
        return self.ask(msg)

    def get_instrument(self, name):
        return ProxyInstrumentModule(name=name, cli=self, remotePath=name)
