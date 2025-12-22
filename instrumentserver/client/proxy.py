# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
import inspect
import json
import yaml
import logging
import os
from types import MethodType
import collections
from typing import Any, Union, Optional, Dict, List
import threading
from contextlib import contextmanager

import qcodes as qc
import zmq
from qcodes import Instrument, Parameter
from qcodes.instrument.base import InstrumentBase

from instrumentserver import QtCore, DEFAULT_PORT
from instrumentserver.helpers import flat_to_nested_dict, flatten_dict, is_flat_dict
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
            if self.cli is None:
                self.bp = self._getBluePrintFromServer(self.remotePath)
            else:
                self.bp = self.cli.getBluePrint(self.remotePath)
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

    def get_snapshot(self, *args, **kwargs):
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
    """Construct a proxy module using the given blueprint. Each proxy
    instantiation represents a virtual module (instrument of submodule of
    instrument).

    :param bluePrint: The blueprint that the describes the module.
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

        # FIXME: This is not consistent with how mixin handles a `None` client. However, this seems like a more
        #  elegant solution than any time we need the client to check to be None, start a new context client instead.
        if cli is None:
            self.cli = Client(host=host, port=port)

        for mn in self.bp.methods.keys():
            if mn == 'remove_parameter':
                def remove_parameter(obj, name: str):
                    obj.cli.call(f'{obj.remotePath}.remove_parameter', name)
                    obj.update()

                self.remove_parameter = MethodType(remove_parameter, self)

        self.parameters.pop('IDN', None)  # we will redefine this later

        # When a new parameter or method is added to client, qcodes checks if that item exists or not. This is done
        #  by calling __getattr__ method. The problem is that when that method gets called and cannot find that item it
        #  creates it, generating an infinite loop. This flag stops that. It should be set to True before doing any change
        #  to the proxy object and set to False after the change is done.
        self.is_updating = False
        with self._updating():
            self.update()

    @contextmanager
    def _updating(self):
        old = self.is_updating
        self.is_updating = True
        try:
            yield
        finally:
            self.is_updating = old


    def initKwargsFromBluePrint(self, bp):
        return {}

    def update(self):
        self.cli.invalidateBlueprint(self.remotePath)
        self.bp = self.cli.getBluePrint(self.remotePath)
        self._getProxyParameters()
        self._getProxyMethods()
        self._getProxySubmodules()
    
    def set_parameters(self, **param_dict:dict):
        """
        Set instrument parameters in batch with a dict, keyed by parameter names.

        """
        for k, v in param_dict.items():
            try:
                self.parameters[k](v)
            except KeyError:
                raise KeyError(f"{self.bp.instrument_module_class} instrument does not have parameter '{k}'")

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
        if self.cli is None:
            raise ValueError("No client is connected to the proxy instrument.")
        bp = self.cli.getBluePrint(self.name)
        self.cli.call(self.name + ".add_parameter", name, *arg, **kw)
        self.update()

    def remove_parameter(self, name: str, *arg, **kw):
        """Removes parameter from the proxy instrument.

        Checking whether the paremeter exists or not is left to the instrument in the server. This is to avoid having
        to check on every submodule for the parameter manager.
        """
        bp: InstrumentModuleBluePrint
        if self.cli is None:
            raise ValueError("No client is connected to the proxy instrument.")
        bp = self.cli.getBluePrint(self.name)
        self.cli.call(self.name + ".remove_parameter", name, *arg, **kw)
        self.update()

    def _getProxyParameters(self) -> None:
        """Based on the parameter blueprint replied from server, add the
        instrument parameters to the proxy instrument class."""

        if self.cli is None:
            raise ValueError("No client is connected to the proxy instrument.")

        # note: we can always provide setpoints_instruments, because in case
        # the parameter doesn't, `setpoints` will just be `None`.
        for pn, p in self.bp.parameters.items():
            if pn not in self.parameters:
                pbp = self.cli.getBluePrint(f"{self.remotePath}.{pn}")
                with self._updating():
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
                with self._updating():
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
        globs = {'wrap': wrap, 'qcodes': qc, 'collections': collections}
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
            del self.submodules[k]

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
            if not self.is_updating:
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
            else:
                raise e


ProxyInstrument = ProxyInstrumentModule


class Client(BaseClient):
    """Client with common server requests as convenience functions."""
    def __init__(self, host='localhost', port=DEFAULT_PORT, connect=True, timeout=20, raise_exceptions=True):
        super().__init__(host, port, connect, timeout, raise_exceptions)
        self._bp_cache = {}
        self._bp_cache_lock = threading.Lock()

    def list_instruments(self) -> Dict[str, str]:
        """ Get the existing instruments on the server.
        """
        message = ServerInstruction(operation=Operation.get_existing_instruments)
        try:
            return self.ask(message)
        except Exception as e:
            logger.error(f"Failed to send or receive message to server at {self.host}:{self.port}", exc_info=True)
            raise RuntimeError("Communication with server failed. See logs for details.") from e

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

        if not isinstance(instrument_class, str):
            raise TypeError('Class name must be a string with the import path of the class. '
                             'If trying to start the parameter manager for example use "instrumentserver.params.ParameterManager" instead of '
                             'passing the class itself.')

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
        """
        get blueprint from server
        :param path:
        :return:
        """
        with self._bp_cache_lock:
            bp = self._bp_cache.get(path)
        if bp is not None:
            return bp

        msg = ServerInstruction(
            operation=Operation.get_blueprint,
            requested_path=path,
        )
        bp = self.ask(msg)
        with self._bp_cache_lock:
            self._bp_cache[path] = bp
        return bp

    def invalidateBlueprint(self, path=None):
        """
        invalidate a parameter in the blueprint cache
        :param path:
        :return:
        """
        with self._bp_cache_lock:
            if path is None:
                self._bp_cache.clear()
            else:
                for k in list(self._bp_cache):
                    if k == path or k.startswith(path + '.'):
                        del self._bp_cache[k]

    def get_snapshot(self, instrument: str | None = None, *args, **kwargs):
        msg = ServerInstruction(
            operation=Operation.call,
            call_spec=CallSpec(
                target='snapshot' if instrument is None else f"{instrument}.snapshot",
                args=args,
                kwargs=kwargs,
            )
        )
        return self.ask(msg)

    def getParamDict(self, instrument: str | None = None,
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

    def _getGuiConfig(self, instrumentName: str) -> Dict[str, Any]:
        """ Gets the GUI config for an instrument from the object. Should only be used in a detached server GUI."""
        msg = ServerInstruction(operation=Operation.get_gui_config, requested_path=instrumentName)
        return self.ask(msg)

class SubClient(QtCore.QObject):
    """
    Specific subscription client used for real-time parameter updates.
    """
    #: Signal(ParameterBroadcastBluePrint) --
    #: emitted when the server broadcast either a new parameter or an update to an existing one.
    update = QtCore.Signal(ParameterBroadcastBluePrint)

    #: Signal emitted when the listener finishes (for proper cleanup)
    finished = QtCore.Signal()

    def __init__(self, instruments: Optional[List[str]] = None, sub_host: str = 'localhost', sub_port: int = DEFAULT_PORT + 1):
        """
        Creates a new subscription client.

        :param instruments: List of instruments the subclient will listen for.
                            If empty/None it will listen to all broadcasts done by the server.
        :param sub_host: The host location of the updates.
        :param sub_port: Should not be changed. It always is the server normal port +1.
        """
        super().__init__()
        self.host = sub_host
        self.port = sub_port
        self.addr = f"tcp://{self.host}:{self.port}"
        self.instruments = instruments

        self.connected = False
        self._stop = False
        self._ctx = None
        self._sock = None

    @QtCore.Slot()
    def connect(self):
        """
        Connects the subscription client with the broadcast
        and runs an infinite loop to check for updates.

        It should always be run on a separate thread or the program will get stuck in the loop.
        """
        logger.info(f"Connecting to {self.addr}")
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.SUB)

        try:
            self._sock.connect(self.addr)

            # subscribe to the specified instruments
            if self.instruments is None:
                self._sock.setsockopt_string(zmq.SUBSCRIBE, '')
            else:
                for ins in self.instruments:
                    self._sock.setsockopt_string(zmq.SUBSCRIBE, ins)

            # Make recv interruptible so we can stop gracefully
            self._sock.setsockopt(zmq.RCVTIMEO, 200)  # ms

            self.connected = True

            while self.connected and not self._stop:
                try:
                    message = recvMultipart(self._sock)
                    self.update.emit(message[1])
                except zmq.Again:
                    # timeout -> loop to check _stop
                    continue
                except (KeyboardInterrupt, SystemExit):
                    logger.info("Program Stopped Manually")
                    break
        finally:
            try:
                if self._sock is not None:
                    self._sock.close(linger=0)
            finally:
                self._sock = None
            self.finished.emit()

        return True

    @QtCore.Slot()
    def stop(self):
        """
        Stops the listener gracefully.
        """
        self._stop = True
        self.connected = False

    def disconnect(self):
        """
        Alias for stop() for backwards compatibility.
        """
        self.stop()


class _QtAdapter(QtCore.QObject):
    def __init__(self, parent, *arg, **kw):
        super().__init__(parent)


class QtClient(_QtAdapter, Client):
    def __init__(self, parent=None,
                 host='localhost',
                 port=DEFAULT_PORT,
                 connect=True,
                 timeout=5,
                 raise_exceptions=True):
        # Calling the parents like this ensures that the arguments arrive to the parents properly.
        _QtAdapter.__init__(self, parent=parent)
        Client.__init__(self, host, port, connect, timeout, raise_exceptions)


class ClientStation:
    def __init__(self, host='localhost', port=DEFAULT_PORT, connect=True, timeout=20, raise_exceptions=True,
                 init_instruments: Union[str, Dict[str, dict]] = None,
                 param_path: str = None):
        """
        A lightweight container for managing a collection of proxy instruments on the client side.

        Conceptually, this acts like a QCoDeS station on the client side, composed of proxy instruments.
        It helps isolate a set of instruments that belong to a specific experiment or user, avoiding
        accidental interactions with other instruments managed by the shared `Client`, as the `Client`
        object has access to all instruments on the server.

        :param host: The host address of the server, defaults to localhost.
        :param port: The port of the server, defaults to the value of DEFAULT_PORT.
        :param connect: If true, the server connects as it is being constructed, defaults to True.
        :param timeout: Amount of time that the client waits for an answer before declaring timeout in seconds.
                        Defaults to 20s.
        :param init_instruments: Either a dictionary or a YAML file path specifying instruments to initialize,
                                 keyed by instrument names.
                                 **Example:**
                                 {"my_vna": {
                                    "instrument_class": "qcodes_drivers.Keysight_E5080B.Keysight_E5080B",
                                    "address": "TCPIP0::10.66.86.251::INSTR"
                                    },
                                  "my_yoko": {...}
                                }
        :param param_path: Optional default file path to use when saving or loading parameters.

        """

        # initialize a client that has access to all the instruments on the server
        self._host = host
        self._port = port
        self._timeout = timeout
        self._raise_exceptions = raise_exceptions
        self.client = self._make_client(connect=connect)
        self.param_path = param_path

        # create proxy instruments based on init_instruments
        self.instruments: Dict[str, ProxyInstrument] = {}
        if isinstance(init_instruments, str):
            with open(init_instruments, 'r') as f:
                init_instruments = yaml.load(f, Loader=yaml.Loader)

        self._create_instruments(init_instruments)
        self._init_instruments = init_instruments

    def _make_client(self, connect=True):
        cli = Client(host=self._host, port=self._port, connect=connect,
                     timeout=self._timeout, raise_exceptions=self._raise_exceptions)
        return cli

    def _create_instruments(self, instrument_dict: dict):
        """
        create proxy instruments based on the parameters in instrument_dict
        """
        for name, conf in instrument_dict.items():
            kwargs = {k: v for k, v in conf.items() if k != 'instrument_class'}
            instrument = self.client.find_or_create_instrument(
                name=name,
                instrument_class=conf['instrument_class'],
                **kwargs
            )
            self.instruments[name] = instrument

    def close_instrument(self, instrument_name:str):
        self.client.close_instrument(instrument_name)

    @staticmethod
    def _remake_client_station_when_fail(func):
        """
        Decorator for remaking a client station object when function call fails
        """

        def wrapper(self, *args, **kwargs):
            try:
                retval = func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error calling {func}: {e}. Trying to remake instrument client ", exc_info=True)
                self.client = self._make_client(connect=True)
                self._create_instruments(self._init_instruments)
                logger.info(f"Successfully remade instrument client.")
                retval = func(self, *args, **kwargs)
            return retval

        return wrapper

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
        ins = self.client.find_or_create_instrument(name, instrument_class, *args, **kwargs)
        self.instruments[name] = ins
        return ins

    def get_instrument(self, name: str) -> ProxyInstrument:
        return self.instruments[name]

    @_remake_client_station_when_fail
    def get_parameters(self, instruments: List[str] = None) -> Dict:
        """
        Get all instrument parameters as a nested dictionary.


        :param instruments: list of instrument names. If None, all instrument parameters are returned.
        :return:
        """
        inst_params = {}
        if instruments is None:
            instruments = self.instruments.keys()
        for name in instruments:
            ins_paras = self.client.getParamDict(name, get=True)
            ins_paras = flat_to_nested_dict(ins_paras)
            inst_params.update(ins_paras)

        return inst_params

    @_remake_client_station_when_fail
    def set_parameters(self, inst_params: Dict):
        """
        load instrument parameters from a nested dictionary.

        :param inst_params: Nested dict of instrument parameters keyed by instrument names.
        :return:
        """

        # make sure we are not setting parameters that doesn't belong to this station
        # even if the might exist on the server
        if is_flat_dict(inst_params):
            inst_params = flat_to_nested_dict(inst_params)

        params_set = {}
        for k in inst_params:
            if k in self.instruments:
                params_set[k] = inst_params[k]
            else:
                logger.warning(f"Instrument {k} parameter neglected, as it doesn't belong to this station")

        # the client `setParameters` function requires a flat param dict
        self.client.setParameters(flatten_dict(params_set))

    @_remake_client_station_when_fail
    def save_parameters(self, file_path: str = None, flat=False, instruments:List[str] = None):
        """
        Save all instrument parameters to a JSON file.

        :param file_path: path to the json file, defaults to self.param_path
        :param flat: when True, save parameters as a flat dictionary with "." separated keys.
        :param instruments: list of instrument names. If None, all instrument parameters are returned.
        :return:
        """
        file_path = file_path if file_path is not None else self.param_path
        inst_params = self.get_parameters(instruments)
        if flat:
            inst_params = flatten_dict(inst_params)

        with open(file_path, 'w') as f:
            json.dump(inst_params, f, indent=2)

        return inst_params

    @_remake_client_station_when_fail
    def load_parameters(self, file_path: str, select_instruments:List[str] = None):
        """
        Load instrument parameters from a JSON file.

        :param file_path: path to the json file, defaults to self.param_path
        :param select_instruments: List of instrument names to load parameters for.
            Defaults to all instruments in the json file.
        :return:
        """
        file_path = file_path if file_path is not None else self.param_path
        with open(file_path, 'r') as f:
            inst_params = json.load(f)

        inst_params = flat_to_nested_dict(inst_params)

        if select_instruments is None:
            params_set = inst_params
        else:
            params_set = {}
            for k in select_instruments:
                params_set[k] = inst_params[k]

        self.set_parameters(params_set)

        return params_set

    def __getitem__(self, item):
        return self.instruments[item]

