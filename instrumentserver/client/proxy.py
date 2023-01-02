# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
import inspect
import json
import logging
import os
from types import MethodType
from typing import Any, Union, Optional, Dict, List

import qcodes as qc
import zmq
from qcodes import Instrument, Parameter
from qcodes.instrument.base import InstrumentBase

from instrumentserver import QtCore, DEFAULT_PORT
from instrumentserver.server.core import (
    ServerInstruction,
    InstrumentModuleBluePrint,
    ParameterBluePrint,
    MethodBluePrint,
    CallSpec,
    Operation,
    InstrumentCreationSpec,
    ParameterSerializeSpec,
)
from .core import sendRequest, BaseClient
from ..base import recvMultipart
from ..blueprints import ParameterBroadcastBluePrint

logger = logging.getLogger(__name__)


# TODO: enable creation of instruments through yaml files/station configurator.
# TODO: support for channel lists
# TODO: support for other parameter classes.
# FIXME: need to generally find the imports we need for type annotations!
# TODO: convenience function to refresh from server.


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
                target=self.remotePath + '.snapshot', args=args, kwargs=kwargs
            )
        )
        return self.askServer(req)


class ProxyParameter(ProxyMixin, Parameter):
    """Proxy for parameters.

    :param cli: Instance of `Client`.
    :param name: The parameter name.
    :param host: The name of the host where the server lives.
    :param port: The port number of the server.
    :param remotePath: Path of the remote object on the server.
    :param bluePrint: The blue print to construct the proxy parameter.
        If `remotePath` and `bluePrint` are both supplied, the blue print takes
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
        # FIXME: uncomment after implementing serializable validators
        # kwargs['vals'] = bp.vals
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


class ProxyInstrumentModule(ProxyMixin, InstrumentBase):
    """Construct a proxy module using the given blue print. Each proxy
    instantiation represents a virtual module (instrument of submodule of
    instrument).

    :param bluePrint: The blue print that the describes the module.
    :param host: The name of the host where the server lives.
    :param port: The port number of the server.
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

        for mn in self.bp.methods.keys():
            if mn == 'remove_parameter':
                def remove_parameter(obj, name: str):
                    obj.cli.call(f'{obj.remotePath}.remove_parameter', name)
                    obj.update()

                self.remove_parameter = MethodType(remove_parameter, self)

        self.parameters.pop('IDN', None)  # we will redefine this later
        self.update()

    def initKwargsFromBluePrint(self, bp):
        return {}

    def update(self):
        self.bp = self.cli.getBluePrint(self.remotePath)
        self._getProxyParameters()
        self._getProxyMethods()
        self._getProxySubmodules()

    def add_parameter(self, name: str, *arg, **kw):
        """Add a parameter to the proxy instrument.

        If a parameter of that name already exists in the server-side instrument,
        we only add the proxy parameter.
        If not, we first add the parameter to the server-side instrument, and
        then the proxy here.
        """

        if name in self.parameters:
            raise ValueError(f'Parameter: {name} already present in the proxy.')

        bp: InstrumentModuleBluePrint
        bp = self.cli.getBluePrint(self.name)
        self.cli.call(self.name + ".add_parameter", name, *arg, **kw)
        self.update()

    def _getProxyParameters(self) -> None:
        """Based on the parameter blueprint replied from server, add the
        instrument parameters to the proxy instrument class."""

        # note: we can always provide setpoints_instruments, because in case
        # the parameter doesn't, `setpoints` will just be `None`.
        for pn, p in self.bp.parameters.items():
            if pn not in self.parameters:
                pbp = self.cli.getBluePrint(f"{self.remotePath}.{pn}")
                super().add_parameter(pbp.name, ProxyParameter, cli=self.cli, host=self.host,
                                      port=self.port, bluePrint=pbp, setpoints_instrument=self)

        delKeys = []
        for pn in self.parameters.keys():
            if pn not in self.bp.parameters:
                delKeys.append(pn)

        # Changing the argument for del self.parameters[pn] to del self.parameters[k]
        for k in delKeys:
            del self.parameters[k]

    def _getProxyMethods(self):
        """Based on the method blue print replied from server, add the
        instrument functions to the proxy instrument class.
        """
        for n, m in self.bp.methods.items():
            if not hasattr(self, n):
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

        sig = bp.call_signature_str
        params = bp.signature_parameters
        args = []
        # FIXME: a better solution to this would probably be to convet kind into the enum object. But it seems that the
        #  parameter kind enum is private.
        for pn, kind in params.items():
            if kind in [str(inspect.Parameter.POSITIONAL_OR_KEYWORD), str(inspect.Parameter.POSITIONAL_ONLY)]:
                args.append(f'{pn}')
            elif kind == str(inspect.Parameter.VAR_POSITIONAL):
                args.append(f"*{pn}")
            elif kind == str(inspect.Parameter.KEYWORD_ONLY):
                args.append(f"{pn}={pn}")
            elif kind == str(inspect.Parameter.VAR_KEYWORD):
                args.append(f"**{pn}")

        # we need to add a `self` argument because we want this to be a bound
        # method of the instrument instance.
        sig = sig[0] + 'self, ' + sig[1:]
        new_func_str = f"""from typing import *\ndef {bp.name}{sig}:
        return wrap({', '.join(args)})"""

        # make sure the method knows the wrap function.
        # TODO: this is not complete!
        globs = {'wrap': wrap, 'qcodes': qc}
        _ret = exec(new_func_str, globs)
        fun = globs[bp.name]
        fun.__doc__ = bp.docstring
        return globs[bp.name]

    def _getProxySubmodules(self):
        """Based on the submodule blue print replied from server, add the proxy
        submodules to the proxy module class.
        """
        for sn, s in self.bp.submodules.items():
            if sn not in self.submodules:
                submodule = ProxyInstrumentModule(
                    s.name, cli=self.cli, host=self.host, port=self.port, bluePrint=s)
                self.add_submodule(sn, submodule)
            else:
                self.submodules[sn].update()

        delKeys = []
        for sn, s in self.submodules.items():
            if sn not in self.bp.submodules:
                delKeys.append(sn)
        for k in delKeys:
            del self.submodules[sn]

    def _refreshProxySubmodules(self):
        delKeys = []
        for sn, s in self.submodules.items():
            if sn in self.bp.submodules:
                delKeys.append(sn)
        for k in delKeys:
            del self.submodules[sn]

        for sn, s in self.bp.submodules.items():
            if sn not in self.submodules:
                submodule = ProxyInstrumentModule(
                    s.name, cli=self.cli, host=self.host, port=self.port, bluePrint=s)
                self.add_submodule(sn, submodule)
            else:
                self.submodules[sn].update()

    def __getattr__(self, item):
        try:
            return super().__getattr__(item)
        except Exception as e:
            current_bp = self.cli.getBluePrint(self.remotePath)
            if item in current_bp.parameters and item not in self.parameters:
                self.bp = current_bp
                self._getProxyParameters()
                return getattr(self, item)
            elif item in current_bp.submodules and item not in self.submodules:
                self.bp = current_bp
                self._getProxySubmodules()
                return getattr(self, item)
            else:
                raise e


ProxyInstrument = ProxyInstrumentModule


class Client(BaseClient):
    """Client with common server requests as convenience functions."""

    def list_instruments(self) -> Dict[str, str]:
        """ Get the existing instruments on the server.
        """
        msg = ServerInstruction(operation=Operation.get_existing_instruments)
        return self.ask(msg)

    def find_or_create_instrument(self, name: str, instrument_class: Optional[str] = None,
                                  *args: Any, **kwargs: Any) -> ProxyInstrumentModule:
        """ Looks for an instrument in the server. If it cannot find it, create a new instrument on the server. Returns
        a proxy for either the found or the new instrument.

        :param name: Name of the new instrument.
        :param instrument_class: Class of the instrument to create or a string of
            of the class.
        :param args: Positional arguments for new instrument instantiation.
        :param kwargs: Keyword arguments for new instrument instantiation.

        :returns: A new virtual instrument.
        """
        if name in self.list_instruments():
            return ProxyInstrumentModule(name=name, cli=self, remotePath=name)

        if instrument_class is None:
            raise ValueError('Need a class to create a new instrument.')

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

    def getBluePrint(self, path):
        msg = ServerInstruction(
            operation=Operation.get_blueprint,
            requested_path=path,
        )
        return self.ask(msg)

    def snapshot(self, instrument: str = None, *args, **kwargs):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target='snapshot' if instrument is None else f"{instrument}.snapshot",
                args=args,
                kwargs=kwargs,
            )
        )
        return self.ask(msg)

    def getParamDict(self, instrument: str = None,
                     attrs: List[str] = ['value'], *args, **kwargs):
        msg = ServerInstruction(
            operation=Operation.get_param_dict,
            serialization_opts=ParameterSerializeSpec(
                path=instrument,
                attrs=attrs,
                args=args,
                kwargs=kwargs,
            )
        )
        return self.ask(msg)

    def paramsToFile(self, filePath: str, *args, **kwargs):
        filePath = os.path.abspath(filePath)
        folder, file = os.path.split(filePath)
        params = self.getParamDict(*args, **kwargs)
        if not os.path.exists(folder):
            os.makedirs(folder)
        with open(filePath, 'w') as f:
            json.dump(params, f, indent=2, sort_keys=True)

    def setParameters(self, parameters: Dict[str, Any]):
        msg = ServerInstruction(
            operation=Operation.set_params,
            set_parameters=parameters,
        )
        return self.ask(msg)

    def paramsFromFile(self, filePath: str):
        params = None
        if os.path.exists(filePath):
            with open(filePath, 'r') as f:
                params = json.load(f)
            self.setParameters(params)
        else:
            logger.warning(f"File {filePath} does not exist. No params loaded.")


class SubClient(QtCore.QObject):
    """
    Specific subscription client used for real-time parameter updates.
    """
    #: Signal(ParameterBroadcastBluePrint) --
    #: emitted when the server broadcast either a new parameter or an update to an existing one.
    update = QtCore.Signal(ParameterBroadcastBluePrint)

    def __init__(self, instruments: List[str] = None, sub_host: str = 'localhost', sub_port: int = DEFAULT_PORT + 1):
        """
        Creates a new subscription client.

        :param instruments: List of instruments the subclient will listen for.
                            If empty it will listen to all broadcasts done by the server.
        :param host: The host location of the updates.
        :param port: Should not be changed. It always is the server normal port +1.
        """
        super().__init__()
        self.host = sub_host
        self.port = sub_port
        self.addr = f"tcp://{self.host}:{self.port}"
        self.instruments = instruments

        self.connected = False

    def connect(self):
        """
        Connects the subscription client with the broadcast
        and runs an infinite loop to check for updates.

        It should always be run on a separate thread or the program will get stuck in the loop.
        """
        logger.info(f"Connecting to {self.addr}")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(self.addr)

        # subscribe to the specified instruments
        if self.instruments is None:
            socket.setsockopt_string(zmq.SUBSCRIBE, '')
        else:
            for ins in self.instruments:
                socket.setsockopt_string(zmq.SUBSCRIBE, ins)

        self.connected = True

        while self.connected:
            message = recvMultipart(socket)
            self.update.emit(message[1])

        self.disconnect()

        return True


class _QtAdapter(QtCore.QObject):
    def __init__(self, parent, *arg, **kw):
        super().__init__(parent)


class QtClient(_QtAdapter, Client):
    def __init__(self, parent=None, host='localhost', port=DEFAULT_PORT, connect=True):
        super().__init__(parent, host, port, connect)
