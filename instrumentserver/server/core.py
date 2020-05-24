# -*- coding: utf-8 -*-
"""
instrumentserver.server.core
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Core functionality of the instrument server.

"""

import importlib
import inspect
import logging
import random
from dataclasses import dataclass
from enum import Enum, unique
from types import MethodType
from typing import Dict, Any, Union, Optional, Tuple, List, Callable

import jsonpickle
import qcodes as qc
import zmq
from qcodes import (
    Station, Instrument, InstrumentChannel, ChannelList,
    Parameter, ParameterWithSetpoints, Function)
from qcodes.instrument import parameter
from qcodes.utils.validators import Validator, Arrays

from .. import QtCore
from ..base import send, recv
from ..helpers import nestedAttributeFromString, objectClassPath, typeClassPath

__author__ = 'Wolfgang Pfaff', 'Chao Zhou'
__license__ = 'MIT'


logger = logging.getLogger(__name__)

INSTRUMENT_MODULE_BASE_CLASSES = [
    Instrument, InstrumentChannel
]
InstrumentModuleType = Union[Instrument, InstrumentChannel]

PARAMETER_BASE_CLASSES = [
    Parameter, ParameterWithSetpoints
]
ParameterType = Union[Parameter, ParameterWithSetpoints]


@unique
class Operation(Enum):
    """Valid operations for the server."""

    #: get a list of instruments the server has instantiated
    get_existing_instruments = 'get_existing_instruments'

    #: create a new instrument
    create_instrument = 'create_instrument'

    #: get the blueprint of an instrument. The blueprint goes beyond a snapshot
    #: and is useful for creating proxies.
    get_instrument_blueprint = 'get_instrument_blueprint'

    #: make a call to an object.
    call = 'call'


@dataclass
class InstrumentCreationSpec:
    """Spec for creating an instrument instance."""

    #: driver class as string, in the format "global.path.to.module.DriverClass"
    instrument_class: str

    #: arguments to pass to the constructor
    args: Optional[Tuple] = None

    #: kw args to pass to the constructor.
    kwargs: Optional[Dict[str, Any]] = None


@dataclass
class CallSpec:
    """Spec for executing a call on an object in the station."""

    #: Full name of the callable object, as string, relative to the station object.
    #: E.g.: "instrument.my_callable" refers to ``station.instrument.my_callable``.
    target: str

    #: positional arguments to pass.
    args: Optional[Any] = None

    #: kw args to pass
    kwargs: Optional[Dict[str, Any]] = None


@dataclass
class ParameterBluePrint:
    """Spec necessary for creating parameter proxies."""
    name: str
    path: str
    base_class: str
    parameter_class: str
    gettable: bool = True
    settable: bool = True
    unit: str = ''
    validator: Optional[Validator] = None
    doc: str = ''

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.tostr()

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{self.name}: {self.parameter_class}
{i}- unit: {self.unit}
{i}- path: {self.path}
{i}- base class: {self.base_class}
{i}- gettable: {self.gettable}
{i}- settable: {self.settable}
{i}- validator: {self.validator}
"""
        return ret


def bluePrintFromParameter(path: str, param: ParameterType) -> \
        Union[ParameterBluePrint, None]:

    base_class = None
    for bc in PARAMETER_BASE_CLASSES:
        if isinstance(param, bc):
            base_class = bc
            break
    if base_class is None:
        logger.warning(f"Blueprints for parameter base type of {param} are "
                       f"currently not supported.")
        return None

    bp = ParameterBluePrint(
        name=param.name,
        path=path,
        base_class=typeClassPath(base_class),
        parameter_class=objectClassPath(param),
        gettable=True if hasattr(param, 'get') else False,
        settable=True if hasattr(param, 'set') else False,
        unit=param.unit,
        doc=param.__doc__,
    )
    if hasattr(param, 'set'):
        bp.validator = param.vals

    return bp


@dataclass
class MethodBluePrint:
    """Spec necessary for creating method proxies."""
    name: str
    path: str
    call_signature: inspect.Signature
    doc: str = ''

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.tostr()

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{self.name}{str(self.call_signature)}
{i}- path: {self.path}
"""
        return ret


def bluePrintFromMethod(path: str, method: Callable) -> Union[MethodBluePrint, None]:
    sig = inspect.signature(method)
    bp = MethodBluePrint(
        name=path.split('.')[-1],
        path=path,
        call_signature=sig,
        doc=method.__doc__,
    )
    return bp


@dataclass
class InstrumentModuleBluePrint:
    """Spec necessary for creating instrument proxies."""
    name: str
    path: str
    base_class: str
    instrument_module_class: str
    doc: str = ''
    parameters: Optional[List[ParameterBluePrint]] = None
    methods: Optional[List[MethodBluePrint]] = None
    submodules: Optional[List["InstrumentModuleBluePrint"]] = None

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.tostr()

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{i}{self.name}: {self.instrument_module_class}
{i}- path: {self.path}
{i}- base class: {self.base_class}
"""
        ret += f"{i}- Parameters:\n{i}  -----------\n"
        for p in self.parameters:
            ret += f"{i}  - " + p.tostr(indent+4)

        ret += f"{i}- Methods:\n{i}  --------\n"
        for m in self.methods:
            ret += f"{i}  - " + m.tostr(indent+4)

        ret += f"{i}- Submodules:\n{i}  -----------\n"
        for s in self.submodules:
            ret += f"{i}  - " + s.tostr(indent+4)

        return ret


def bluePrintFromInstrumentModule(path: str, ins: InstrumentModuleType) -> \
        Union[InstrumentModuleBluePrint, None]:

    base_class = None
    for bc in INSTRUMENT_MODULE_BASE_CLASSES:
        if isinstance(ins, bc):
            base_class = bc
            break
    if base_class is None:
        logger.warning(f"Blueprints for instrument base type of {ins} are "
                       f"currently not supported.")
        return None

    bp = InstrumentModuleBluePrint(
        name=ins.name,
        path=path,
        base_class=typeClassPath(base_class),
        instrument_module_class=objectClassPath(ins),
        doc=ins.__doc__
    )
    bp.parameters = []
    bp.methods = []
    bp.submodules = []

    for pn, p in ins.parameters.items():
        param_path = f"{path}.{p.name}"
        param_bp = bluePrintFromParameter(param_path, p)
        if param_bp is not None:
            bp.parameters.append(param_bp)

    for elt in dir(ins):
        # don't include private methods, or methods that belong to the qcodes
        # base classes.
        if elt[0] == '_' or hasattr(base_class, elt):
            continue
        o = getattr(ins, elt)
        if callable(o) and not isinstance(o, tuple(PARAMETER_BASE_CLASSES)):
            meth_path = f"{path}.{elt}"
            meth_bp = bluePrintFromMethod(meth_path, o)
            if meth_bp is not None:
                bp.methods.append(meth_bp)

    for sn, s in ins.submodules.items():
        sub_path = f"{path}.{sn}"
        sub_bp = bluePrintFromInstrumentModule(sub_path, s)
        if sub_bp is not None:
            bp.submodules.append(sub_bp)

    return bp



@dataclass
class ServerInstruction:
    """Instruction spec for the server.

    Valid operations:

    - :attr:`Operation.get_existing_instruments` -- get the instruments currently
      instantiated in the station.

        - **Required options:** -
        - **Return message:** dictionary with instrument name and class (as string)

    - :attr:`Operation.create_instrument` -- create a new instrument in the station.

        - **Required options:** :attr:`.create_instrument_spec`
        - **Return message:** ``None``

    - :attr:`Operation.call` -- make a call to an object in the station.

        - **Required options:** :attr:`.call_spec`
        - **Return message:** The return value of the call.

    """

    #: This is the only mandatory item.
    #: Which other fields are required depends on the operation.
    operation: Operation

    #: Specification for creating an instrument
    create_instrument_spec: Optional[InstrumentCreationSpec] = None

    #: Specification for executing a call
    call_spec: Optional[CallSpec] = None

    def validate(self):
        if self.operation is Operation.create_instrument:
            if not isinstance(self.create_instrument_spec, InstrumentCreationSpec):
                raise ValueError('Invalid instrument creation spec.')

        if self.operation is Operation.call:
            if not isinstance(self.call_spec, CallSpec):
                raise ValueError('Invalid call spec.')


@dataclass
class ServerResponse:
    """Spec for what the server can return.

    if the requested operation succeeds, `message` will the return of that operation,
    and `error` is None.
    See :class:`ServerInstruction` for a documentation of the expected returns.
    If an error occurs, `message` is typically ``None``, and `error` contains an
    error message or object describing the error.
    """
    #: the return message
    message: Optional[Any] = None

    #: Any error message occured during execution of the instruction.
    error: Optional[Union[None, str, Warning, Exception]] = None


class StationServer(QtCore.QObject):
    """The main server object.

    Encapsulated in a separate object so we can run it in a separate thread.
    """

    # we use this to quit the server.
    # if this string is sent as message to the server, it'll shut down and close
    # the socket. Should only be used from within this module.
    # it's randomized in the instantiated server for a little bit of safety.
    SAFEWORD = 'BANANA'

    #: Signal(str, str) -- emit messages for display in the gui (or other stuff the gui
    #: wants to do with it.
    #: Arguments: the message received, and the reply sent.
    messageReceived = QtCore.Signal(str, str)

    #: Signal(int) -- emitted when the server is started.
    #: Arguments: the port.
    serverStarted = QtCore.Signal(str)

    #: Signal() -- emitted when we shut down
    finished = QtCore.Signal()

    #: Signal(Dict) -- emitted when a new instrument was created.
    #: Argument is the snapshot of the instrument.
    instrumentCreated = QtCore.Signal(dict)

    #: Signal(str, Any) -- emitted when a parameter was set
    #: Arguments: full parameter location as string, value
    parameterSet = QtCore.Signal(str, object)

    #: Signal(str, Any) -- emitted when a parameter was retrieved
    #: Arguments: full parameter location as string, value
    parameterGet = QtCore.Signal(str, object)

    #: Signal(str, List[Any], Dict[str, Any], Any) -- emitted when a function was called
    #: Arguments: full function location as string, arguments, kw arguments, return value
    funcCalled = QtCore.Signal(str, object, object, object)

    def __init__(self, parent=None, port=5555, allowUserShutdown=False):
        super().__init__(parent)

        self.SAFEWORD = ''.join(random.choices([chr(i) for i in range(65, 91)], k=16))
        self.serverRunning = False
        self.port = port
        self.station = Station()
        self.allowUserShutdown = allowUserShutdown

        self.parameterSet.connect(
            lambda n, v: logger.info(f"Parameter '{n}' set to: {str(v)}")
        )
        self.parameterGet.connect(
            lambda n, v: logger.debug(f"Parameter '{n}' retrieved: {str(v)}")
        )
        self.funcCalled.connect(
            lambda n, args, kw, ret: logger.debug(f"Function called:"
                                                  f"'{n}({str(args), str(kw)})'.")
        )

    @QtCore.Slot()
    def startServer(self):
        """Start the server. This function does not return until the ZMQ server
        has been shut down."""

        addr = f"tcp://*:{self.port}"
        logger.info(f"Starting server at {addr}")
        logger.info(f"The safe word is: {self.SAFEWORD}")
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind(addr)

        self.serverRunning = True
        self.serverStarted.emit(addr)

        while self.serverRunning:
            message = recv(socket)
            message_ok = True
            response_to_client = None
            response_log = None

            # allow the test client from within the same process to make sure the
            # server shuts down. This is
            if message == self.SAFEWORD:
                response_log = 'Server has received the safeword and will shut down.'
                response_to_client = ServerResponse(message=response_log)
                self.serverRunning = False
                logger.warning(response_log)

            elif self.allowUserShutdown and message == 'SHUTDOWN':
                response_log = 'Server shutdown requested by client.'
                response_to_client = ServerResponse(message=response_log)
                self.serverRunning = False
                logger.warning(response_log)

            # if the message is a string we just echo it back.
            # this is used for testing sometimes, but has no functionality.
            elif isinstance(message, str):
                response_log = f"Server has received: {message}. No further action."
                response_to_client = ServerResponse(message=response_log)
                logger.info(response_log)

            # we assume this is a valid instruction set now.
            elif isinstance(message, ServerInstruction):
                instruction = message
                try:
                    instruction.validate()
                    logger.info(f"Received request for operation: "
                                f"{str(instruction.operation)}")
                    logger.debug(f"Instruction received: "
                                 f"{str(instruction)}")
                except Exception as e:
                    message_ok = False
                    response_log = f'Received invalid message. Error raised: {str(e)}'
                    response_to_client = ServerResponse(message=None, error=e)
                    logger.warning(response_log)

                if message_ok:
                    # we don't need to use a try-block here, because
                    # errors are already handled in executeServerInstruction
                    response_to_client = self.executeServerInstruction(instruction)
                    response_log = f"Response to client: {str(response_to_client)}"
                    if response_to_client.error is None:
                        logger.info(f"Response sent to client.")
                        logger.debug(response_log)
                    else:
                        logger.warning(response_log)

            else:
                response_log = f"Invalid message type."
                response_to_client = ServerResponse(message=None, error=response_log)
                logger.warning(f"Invalid message type: {type(message)}.")
                logger.debug(f"Invalid message received: {str(message)}")

            send(socket, response_to_client)
            self.messageReceived.emit(str(message), response_log)

        socket.close()
        self.finished.emit()
        return True

    def executeServerInstruction(self, instruction: ServerInstruction) \
            -> ServerResponse:
        """
        This is the interpreter function that the server will call to translate the
        dictionary received from the proxy to instrument calls.

        :param instruction: The instruction object.
        :returns: the results returned from performing the operation.
        """
        args = []
        kwargs = {}

        # we call a helper function depending on the operation that is requested
        if instruction.operation == Operation.get_existing_instruments:
            func = self._getExistingInstruments
        elif instruction.operation == Operation.create_instrument:
            func = self._createInstrument
            args = [instruction.create_instrument_spec]
        elif instruction.operation == Operation.call:
            func = self._callObject
            args = [instruction.call_spec]
        else:
            raise NotImplementedError

        try:
            returns = func(*args, **kwargs)
            response = ServerResponse(message=returns)

        except Exception as err:
            response = ServerResponse(message=None, error=err)

        return response

    def _getExistingInstruments(self) -> Dict:
        """
        Get the existing instruments in the station,

        :returns : a dictionary that contains the instrument name and its class name.
        """
        snap_ins = self.station.snapshot()['instruments']
        info = {k: snap_ins[k]['__class__'] for k in snap_ins.keys()}
        return info

    def _createInstrument(self, spec: InstrumentCreationSpec) -> None:
        """Create a new instrument on the server"""
        sep_class = spec.instrument_class.split('.')
        modName = '.'.join(sep_class[:-1])
        clsName = sep_class[-1]
        mod = importlib.import_module(modName)
        cls = getattr(mod, clsName)

        args = [] if spec.args is None else spec.args
        kwargs = dict() if spec.kwargs is None else spec.kwargs

        new_instrument = qc.find_or_create_instrument(
            cls, *args, **kwargs)
        if new_instrument.name not in self.station.components:
            self.station.add_component(new_instrument)

        self.instrumentCreated.emit(new_instrument.snapshot())

    def _callObject(self, spec: CallSpec) -> Any:
        """call some callable found in the station."""
        obj = nestedAttributeFromString(self.station, spec.target)
        args = spec.args if spec.args is not None else []
        kwargs = spec.kwargs if spec.kwargs is not None else {}
        ret = obj(*args, **kwargs)

        if isinstance(obj, Parameter):
            if len(args) > 0:
                self.parameterSet.emit(spec.target, args[0])
            else:
                self.parameterGet.emit(spec.target, ret)
        else:
            self.funcCalled.emit(spec.target, args, kwargs, ret)

        return ret


def startServer(port=5555, allowUserShutdown=False) -> \
        Tuple[StationServer, QtCore.QThread]:
    """Create a server and run in a separate thread.
    :returns: the server object and the thread it's running in.
    """
    server = StationServer(port=port, allowUserShutdown=allowUserShutdown)
    thread = QtCore.QThread()
    server.moveToThread(thread)
    server.finished.connect(thread.quit)
    thread.started.connect(server.startServer)
    thread.start()
    return server, thread


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

#
# def _proxyGetParam(instrument: Instrument, paramDict: ParamDictType) -> Any:
#     """
#     Get a parameter from the instrument.
#
#     :param paramDict: the dictionary that contains the parameter to change, the
#         'value' item will be omitted.
#     :returns : value of the parameter returned from instrument
#
#     """
#     paramName = paramDict['name']
#     return instrument[paramName]()
#
#
# def _proxySetParam(instrument: Instrument, paramDict: ParamDictType) -> None:
#     """
#     Set a parameter in the instrument.
#
#     :param paramDict:  the dictionary that contains the parameter to change, the
#         'value' item will be the set value.
#         e.g. {'ch1': {'value' : 10} }
#     """
#     paramName = paramDict['name']
#     instrument[paramName](paramDict['value'])
#
#
# def _proxyCallFunc(instrument: Instrument, funcDict: FuncDictType) -> Any:
#     """
#     Call an instrument function.
#
#     :param funcDict:  the dictionary that contains the name of the function to
#         call and the argument values
#
#     :returns : result returned from the instrument function
#     """
#     funcName = funcDict['name']
#
#     if ('kwargs' in funcDict) and ('args' in funcDict):
#         args = funcDict['args']
#         kwargs = funcDict['kwargs']
#         return getattr(instrument, funcName)(*args, **kwargs)
#     elif 'args' in funcDict:
#         args = funcDict['args']
#         return getattr(instrument, funcName)(*args)
#     elif 'kwargs' in funcDict:
#         kwargs = funcDict['kwargs']
#         return getattr(instrument, funcName)(**kwargs)
#     else:
#         return getattr(instrument, funcName)()
#
#
# def _proxyWriteRaw(instrument: Instrument, cmd: str) -> Union[str, None]:
#     return instrument.write_raw(cmd)
#
#
# def _proxyAskRaw(instrument: Instrument, cmd: str) -> Union[str, None]:
#     return instrument.ask_raw(cmd)
