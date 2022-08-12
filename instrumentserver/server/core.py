# -*- coding: utf-8 -*-
"""
instrumentserver.server.core
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Core functionality of the instrument server.

"""

# TODO: add a signal for when instruments are closed?
# TODO: validator only when the parameter is settable?
# TODO: the BluePrints should probably go into the serialization module.
# TODO: for full functionality in the proxy, we probably need to introduce
#   operations for adding parameters/submodules/functions
# TODO: can we also create methods remotely?

import os
import importlib
import inspect
import logging
import random
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Dict, Any, Union, Optional, Tuple, List, Callable

import zmq

import qcodes as qc
from qcodes import (
    Station, Instrument, InstrumentChannel, Parameter, ParameterWithSetpoints)
from qcodes.instrument.base import InstrumentBase
from qcodes.utils.validators import Validator

from .. import QtCore, serialize
from ..base import send, recv

from ..helpers import nestedAttributeFromString, objectClassPath, typeClassPath

__author__ = 'Wolfgang Pfaff', 'Chao Zhou'
__license__ = 'MIT'

logger = logging.getLogger(__name__)

INSTRUMENT_MODULE_BASE_CLASSES = [
    Instrument, InstrumentChannel, InstrumentBase
]
InstrumentModuleType = Union[Instrument, InstrumentChannel, InstrumentBase]

PARAMETER_BASE_CLASSES = [
    Parameter, ParameterWithSetpoints
]
ParameterType = Union[Parameter, ParameterWithSetpoints]


@unique
class Operation(Enum):
    """Valid operations for the server."""

    #: Get a list of instruments the server has instantiated.
    get_existing_instruments = 'get_existing_instruments'

    #: Create a new instrument.
    create_instrument = 'create_instrument'

    #: Get the blueprint of an object.
    get_blueprint = 'get_blueprint'

    #: Make a call to an object.
    call = 'call'

    #: Get the station contents as parameter dict.
    get_param_dict = 'get_param_dict'

    #: Set station parameters from a dictionary.
    set_params = 'set_params'


@dataclass
class InstrumentCreationSpec:
    """Spec for creating an instrument instance."""

    #: Driver class as string, in the format "global.path.to.module.DriverClass".
    instrument_class: str

    #: Name of the new instrument, I separate this from args and kwargs to
    # make it easier to be found.
    name: str = ''

    #: Arguments to pass to the constructor.
    args: Optional[Tuple] = None

    #: kw args to pass to the constructor.
    kwargs: Optional[Dict[str, Any]] = None


@dataclass
class CallSpec:
    """Spec for executing a call on an object in the station."""

    #: Full name of the callable object, as string, relative to the station object.
    #: E.g.: "instrument.my_callable" refers to ``station.instrument.my_callable``.
    target: str

    #: Positional arguments to pass.
    args: Optional[Any] = None

    #: kw args to pass.
    kwargs: Optional[Dict[str, Any]] = None

import pickle
def is_picklable(obj):
    try:
      pickle.dumps(obj)
    except:
      return False
    return True

@dataclass
class ParameterBluePrint:
    """Spec necessary for creating parameter proxies."""


    def __init__(self, path, parameter):
        
        #adds picklable attributes of the actual parameter to the parameter blueprint
        for attr in dir(parameter):
            if(attr[0:2] != '__'): #don't try to use these
                temp = getattr(parameter, attr)                
                picklable = is_picklable(temp)
                if picklable:
                    setattr(self, attr, temp)
        setattr(self, 'path', path)
        
        #gets the base class and parameter class. possibly these would make more sense swapped
        #TODO: make this neater
        if not hasattr(self, 'base_class'): 
            if typeClassPath(type(parameter)).split('.')[0] == 'qcodes': #then it's a regular Parameter
                setattr(self, 'base_class', typeClassPath(type(parameter))) 
            else: #otherwise it's a child class of a parameter of some sort
                setattr(self, 'base_class', typeClassPath(type(parameter).__bases__[0])) #should do e.g. vna.s21 -> MultiParameter
        if not hasattr(self, 'parameter_class'):
            setattr(self, 'parameter_class', objectClassPath(parameter))
        #gettable, settable should come from the param. I'll be surprised if they don't
        setattr(self, 'docstring', parameter.__doc__)
        
    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.name}: {self.parameter_class}"

    def tostr(self, indent=0): #is this used? I think these objects are pickled instead
        i = indent * ' '
        ret = f"""{self.name}: {self.parameter_class}
        """
        for attr in dir(self):
            if(attr[0:2] != '__'): #don't try to use these
                temp_str = f"""{i}- {attr}: {getattr(self, attr)}
                """
                ret = ret + temp_str
        return ret


def bluePrintFromParameter(path: str, param: ParameterType) -> \
        Union[ParameterBluePrint, None]:

    bp = ParameterBluePrint(path, param)
    


    return bp




@dataclass
class MethodBluePrint:
    """Spec necessary for creating method proxies."""
    name: str
    path: str
    call_signature: inspect.Signature
    docstring: str = ''

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self.name}{str(self.call_signature)}"

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
        docstring=method.__doc__,
    )
    return bp


@dataclass
class InstrumentModuleBluePrint:
    """Spec necessary for creating instrument proxies."""
    name: str
    path: str
    base_class: str
    instrument_module_class: str
    docstring: str = ''
    parameters: Optional[Dict[str, ParameterBluePrint]] = field(default_factory=dict)
    methods: Optional[Dict[str, MethodBluePrint]] = field(default_factory=dict)
    submodules: Optional[Dict[str, "InstrumentModuleBluePrint"]] = field(default_factory=dict)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.name}: {self.instrument_module_class}"

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{i}{self.name}: {self.instrument_module_class}
{i}- path: {self.path}
{i}- base class: {self.base_class}
"""
        ret += f"{i}- Parameters:\n{i}  -----------\n"
        for pn, p in self.parameters.items():
            ret += f"{i}  - " + p.tostr(indent + 4)

        ret += f"{i}- Methods:\n{i}  --------\n"
        for mn, m in self.methods.items():
            ret += f"{i}  - " + m.tostr(indent + 4)

        ret += f"{i}- Submodules:\n{i}  -----------\n"
        for sn, s in self.submodules.items():
            ret += f"{i}  - " + s.tostr(indent + 4)

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
        docstring=ins.__doc__
    )
    bp.parameters = {}
    bp.methods = {}
    bp.submodules = {}

    for pn, p in ins.parameters.items():
        param_path = f"{path}.{p.name}"
        param_bp = bluePrintFromParameter(param_path, p)
        if param_bp is not None:
            bp.parameters[pn] = param_bp

    for elt in dir(ins):
        # don't include private methods, or methods that belong to the qcodes
        # base classes.
        if elt[0] == '_' or hasattr(base_class, elt):
            continue
        o = getattr(ins, elt)
        #changing the check of whether it's a parameter
        #if callable(o) and not o.__module__ == 'qcodes.instrument.parameter':
        if callable(o):
            #I'm sure there's a cleaner way to do this but I don't know it
            #idea is every parameter can actually be a parameter so don't make
            #it a method
            isparam = False
            for pn, p in ins.parameters.items(): 
                if o == pn or o == p:
                    isparam = True
            if not isparam:
                meth_path = f"{path}.{elt}"
                meth_bp = bluePrintFromMethod(meth_path, o)
                if meth_bp is not None:
                    bp.methods[elt] = meth_bp

    for sn, s in ins.submodules.items():
        sub_path = f"{path}.{sn}"
        sub_bp = bluePrintFromInstrumentModule(sub_path, s)
        if sub_bp is not None:
            bp.submodules[sn] = sub_bp

    return bp

@dataclass
class ParameterBroadcastBluePrint:
    """Blueprint to broadcast parameter changes."""
    name: str
    action: str
    value: int = None
    unit: str = None

    def __init__(self, name: str, action: str, value: int = None, unit: str = None):
        self.name = name
        self.value = value
        self.unit = unit
        self.action = action

    def __str__(self) -> str:
        ret = f"""\"name\":\"{self.name}\": {{    
    \"action\":\"{self.action}" """
        if self.value is not None:
            ret = ret + f"\n    \"value\":\"{self.value}\""
        if self.unit is not None:
            ret = ret + f"\n    \"unit\":\"{self.unit}\""
        ret = ret + f"""\n}}"""
        return ret

    def __repr__(self):
        return str(self)

    def pprint(self, indent=0):

        i = indent * ' '
        ret = f"""name: {self.name}
{i}- action: {self.action}
{i}- value: {self.value}
{i}- unit: {self.unit}
    """
        return ret

    def toDictFormat(self):
        """
        Formats the blueprint for easy conversion to dictionary later.
        """
        ret = f"'name': '{self.name}'," \
              f" 'action': '{self.action}'," \
              f" 'value': '{self.value}'," \
              f" 'unit': '{self.unit}'"
        return "{"+ret+"}"


@dataclass
class ParameterSerializeSpec:

    #: Path of the object to serialize. ``None`` refers to the station as a whole.
    path: Optional[str] = None

    #: Which attributes to include for each parameter. Default is ['values'].
    attrs: List[str] = field(default_factory=lambda: ['values'])

    #: Additional arguments to pass to the serialization function
    #: :func:`.serialize.toParamDict`.
    args: Optional[Any] = field(default_factory=list)

    #: Additional kw arguments to pass to the serialization function
    #: :func:`.serialize.toParamDict`.
    kwargs: Optional[Dict[str, Any]] = field(default_factory=dict)



@dataclass
class ServerInstruction:
    #TODO: Remove set parameterr from the code.
    """Instruction spec for the server.

    Valid operations:

    - :attr:`Operation.get_existing_instruments` -- get the instruments currently
      instantiated in the station.

        - **Required options:** -
        - **Return message:** dictionary with instrument name and class (as string).

    - :attr:`Operation.create_instrument` -- create a new instrument in the station.

        - **Required options:** :attr:`.create_instrument_spec`
        - **Return message:** ``None``

    - :attr:`Operation.call` -- make a call to an object in the station.

        - **Required options:** :attr:`.call_spec`
        - **Return message:** The return value of the call.

    - :attr:`Operation.get_blueprint` -- request the blueprint of an object

        - **Required options:** :attr:`.requested_path`
        - **Return message:** The blueprint of the object.

    - :attr:`Operation.get_param_dict` -- request parameters as dictionary
      Get the parameters of either the full station or a single object.

        - **Options:** :attr:`.serialization_opts`
        - **Return message:** param dict.

    """

    #: This is the only mandatory item.
    #: Which other fields are required depends on the operation.
    operation: Operation

    #: Specification for creating an instrument.
    create_instrument_spec: Optional[InstrumentCreationSpec] = None

    #: Specification for executing a call.
    call_spec: Optional[CallSpec] = None

    #: Name of the instrument for which we want the blueprint.
    requested_path: Optional[str] = None

    #: Options for serialization.
    serialization_opts: Optional[ParameterSerializeSpec] = None

    #: Setting parameters in bulk with a paramDict.
    set_parameters: Optional[Dict[str, Any]] = field(default_factory=dict)

    #: Generic arguments.
    args: Optional[List[Any]] = field(default_factory=list)

    #: Generic keyword arguments.
    kwargs: Optional[Dict[str, Any]] = field(default_factory=dict)

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

    If the requested operation succeeds, `message` will the return of that operation,
    and `error` is None.
    See :class:`ServerInstruction` for a documentation of the expected returns.
    If an error occurs, `message` is typically ``None``, and `error` contains an
    error message or object describing the error.
    """
    #: The return message.
    message: Optional[Any] = None

    #: Any error message occured during execution of the instruction.
    error: Optional[Union[None, str, Warning, Exception]] = None


class StationServer(QtCore.QObject):
    """The main server object.

    Encapsulated in a separate object so we can run it in a separate thread.

    Port should always be an odd number to allow the next even number to be its corresponding
    publishing port.
    """

    # We use this to quit the server.
    # If this string is sent as message to the server, it'll shut down and close
    # the socket. Should only be used from within this module.
    # It's randomized in the instantiated server for a little bit of safety.
    SAFEWORD = 'BANANA'

    #: Signal(str, str) -- emit messages for display in the gui (or other stuff the gui
    #: wants to do with it.
    #: Arguments: the message received, and the reply sent.
    messageReceived = QtCore.Signal(str, str)

    #: Signal(int) -- emitted when the server is started.
    #: Arguments: the port.
    serverStarted = QtCore.Signal(str)

    #: Signal() -- emitted when we shut down.
    finished = QtCore.Signal()

    #: Signal(Dict) -- emitted when a new instrument was created.
    #: Argument is the blueprint of the instrument.
    instrumentCreated = QtCore.Signal(object)

    #: Signal(str, Any) -- emitted when a parameter was set
    #: Arguments: full parameter location as string, value.
    parameterSet = QtCore.Signal(str, object)

    #: Signal(str, Any) -- emitted when a parameter was retrieved
    #: Arguments: full parameter location as string, value.
    parameterGet = QtCore.Signal(str, object)

    #: Signal(str, List[Any], Dict[str, Any], Any) -- emitted when a function was called
    #: Arguments: full function location as string, arguments, kw arguments, return value.
    funcCalled = QtCore.Signal(str, object, object, object)

    def __init__(self,
                 parent: Optional[QtCore.QObject] = None,
                 port: int = 5555,
                 allowUserShutdown: bool = False,
                 addresses: List[str] = [],
                 initScript: Optional[str] = None,
                 ) -> None:
        super().__init__(parent)

        if addresses is None:
            addresses = []
        if initScript == None:
            initScript = ''

        self.SAFEWORD = ''.join(random.choices([chr(i) for i in range(65, 91)], k=16))
        self.serverRunning = False
        self.port = int(port)
        self.station = Station()
        self.allowUserShutdown = allowUserShutdown
        self.listenAddresses = list(set(['127.0.0.1'] + addresses))
        self.initScript = initScript

        self.broadcastPort = self.port + 1
        self.broadcastSocket = None

        self.parameterSet.connect(
            lambda n, v: logger.info(f"Parameter '{n}' set to: {str(v)}")
        )
        self.parameterGet.connect(
            lambda n, v: logger.debug(f"Parameter '{n}' retrieved: {str(v)}")
        )
        self.funcCalled.connect(
            lambda n, args, kw, ret: logger.debug(f"Function called:"
                                                  f"'{n}', args: {str(args)}, "
                                                  f"kwargs: {str(kw)})'.")
        )

    def _runInitScript(self):
        if os.path.exists(self.initScript):
            path = os.path.abspath(self.initScript)
            env = dict(station=self.station)
            exec(open(path).read(), env)
            
        else:
            logger.warning(f"path to initscript ({self.initScript}) not found.")

    @QtCore.Slot()
    def startServer(self) -> None:
        """Start the server. This function does not return until the ZMQ server
        has been shut down."""

        logger.info(f"Starting server.")
        logger.info(f"The safe word is: {self.SAFEWORD}")
        context = zmq.Context()
        socket = context.socket(zmq.REP)

        for a in self.listenAddresses:
            addr = f"tcp://{a}:{self.port}"
            socket.bind(addr)
            logger.info(f"Listening at {addr}")

        # creating and binding publishing socket to broadcast changes
        broadcastAddr = f"tcp://*:{self.broadcastPort}"
        logger.info(f"Starting publishing server at {broadcastAddr}")
        self.broadcastSocket = context.socket(zmq.PUB)
        self.broadcastSocket.bind(broadcastAddr)

        self.serverRunning = True
        if self.initScript not in ['', None]:
            logger.info(f"Running init script")
            self._runInitScript()
        self.serverStarted.emit(addr)

        while self.serverRunning:
            message = recv(socket)
            message_ok = True
            response_to_client = None
            response_log = None

            # Allow the test client from within the same process to make sure the
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

            # If the message is a string we just echo it back.
            # This is used for testing sometimes, but has no functionality.
            elif isinstance(message, str):
                response_log = f"Server has received: {message}. No further action."
                response_to_client = ServerResponse(message=response_log)
                logger.info(response_log)

            # We assume this is a valid instruction set now.
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
                    # We don't need to use a try-block here, because
                    # errors are already handled in executeServerInstruction.
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

        self.broadcastSocket.close()
        socket.close()
        self.finished.emit()
        return True

    def executeServerInstruction(self, instruction: ServerInstruction) \
            -> Tuple[ServerResponse, str]:
        """
        This is the interpreter function that the server will call to translate the
        dictionary received from the proxy to instrument calls.

        :param instruction: The instruction object.
        :returns: The results returned from performing the operation.
        """
        args = []
        kwargs = {}

        # We call a helper function depending on the operation that is requested.
        if instruction.operation == Operation.get_existing_instruments:
            func = self._getExistingInstruments
        elif instruction.operation == Operation.create_instrument:
            func = self._createInstrument
            args = [instruction.create_instrument_spec]
        elif instruction.operation == Operation.call:
            func = self._callObject
            args = [instruction.call_spec]
        elif instruction.operation == Operation.get_blueprint:
            func = self._getBluePrint
            args = [instruction.requested_path]
        elif instruction.operation == Operation.get_param_dict:
            func = self._toParamDict
            args = [instruction.serialization_opts]
        elif instruction.operation == Operation.set_params:
            func = self._fromParamDict
            args = [instruction.set_parameters]
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
        Get the existing instruments in the station.

        :returns: A dictionary that contains the instrument name and its class name.
        """
        comps = self.station.components
        info = {k: v.__class__ for k, v in comps.items()}
        return info

    def _createInstrument(self, spec: InstrumentCreationSpec) -> None:
        """Create a new instrument on the server."""
        sep_class = spec.instrument_class.split('.')
        modName = '.'.join(sep_class[:-1])
        clsName = sep_class[-1]
        mod = importlib.import_module(modName)
        cls = getattr(mod, clsName)

        args = [] if spec.args is None else spec.args
        kwargs = dict() if spec.kwargs is None else spec.kwargs

        new_instrument = qc.find_or_create_instrument(
            cls, name=spec.name, *args, **kwargs)
        if new_instrument.name not in self.station.components:
            self.station.add_component(new_instrument)

            self.instrumentCreated.emit(
                bluePrintFromInstrumentModule(new_instrument.name,
                                              new_instrument)
            )

    def _callObject(self, spec: CallSpec) -> Any:
        """Call some callable found in the station."""
        obj = nestedAttributeFromString(self.station, spec.target)
        args = spec.args if spec.args is not None else []
        kwargs = spec.kwargs if spec.kwargs is not None else {}
        ret = obj(*args, **kwargs)

        # Check if a new parameter is being created.
        self._newOrDeleteParameterDetection(spec, args, kwargs)

        if isinstance(obj, Parameter):
            if len(args) > 0:
                self.parameterSet.emit(spec.target, args[0])

                # Broadcast changes in parameter values.
                self._broadcastParameterChange(ParameterBroadcastBluePrint(spec.target, 'parameter-update', args[0]))
            else:
                self.parameterGet.emit(spec.target, ret)

                # Broadcast calls of parameters.
                self._broadcastParameterChange(ParameterBroadcastBluePrint(spec.target, 'parameter-call', ret))
        else:
            self.funcCalled.emit(spec.target, args, kwargs, ret)

        return ret

    def _getBluePrint(self, path: str) -> Union[InstrumentModuleBluePrint,
                                                ParameterBluePrint,
                                                MethodBluePrint]:
        
        logger.info(f"Getting blueprint for path {path}")
        logger.info(f"Path is type {type(path)}")
        
        #TODO: tidy this up
        path_split = path.split('.')
        path_minus1 = path_split[0:-1]
        path_minus1_rejoined = '.'.join(path_minus1)
        if path_minus1_rejoined != '':
            obj_minus1 = nestedAttributeFromString(self.station, path_minus1_rejoined)
            

        obj = nestedAttributeFromString(self.station, path)
        
        #if it's an instrument class, give an instrument blueprint
        if isinstance(obj, tuple(INSTRUMENT_MODULE_BASE_CLASSES)):
            return bluePrintFromInstrumentModule(path, obj)
        #if it's something like instrument.obj, assume it's a parameter #TODO: improve this
        elif isinstance(obj_minus1, tuple(INSTRUMENT_MODULE_BASE_CLASSES)):
            return bluePrintFromParameter(path, obj)
        elif callable(obj): #the check before probably grabs all of these. Not sure if that's bad
            return bluePrintFromMethod(path, obj)
        else:
            raise ValueError(f'Cannot create a blueprint for {type(obj)}')

    def _toParamDict(self, opts: ParameterSerializeSpec) -> Dict[str, Any]:
        if opts.path is None:
            obj = self.station
        else:
            obj = [nestedAttributeFromString(self.station, opts.path)]

        includeMeta = [k for k in opts.attrs if k != 'value']
        return serialize.toParamDict(obj, *opts.args, includeMeta=includeMeta,
                                     **opts.kwargs)

    def _fromParamDict(self, params: Dict[str, Any]):
        return serialize.fromParamDict(params, self.station)

    def _broadcastParameterChange(self, blueprint: ParameterBroadcastBluePrint):
        """
        Broadcast any changes to parameters in the server.
        The message is composed of a 2 part array. The first item is the name of the instrument the parameter is from,
        with the second item being the string of the blueprint in dict format.
        This is done to allow subscribers to subscribe to specific instruments.

        :param blueprint: The parameter broadcast blueprint that is being broadcast
        """
        self.broadcastSocket.send_string(blueprint.name.split('.')[0], flags=zmq.SNDMORE)
        self.broadcastSocket.send_string((blueprint.toDictFormat()))
        logger.info(f"Parameter {blueprint.name} has broadcast an update of type: {blueprint.action},"
                     f" with a value: {blueprint.value}.")

    def _newOrDeleteParameterDetection(self, spec, args, kwargs):
        """
        Detects if the call action is being used to create a new parameter or deletes an existing parameter.
        If so, it creates the parameter broadcast blueprint and broadcast it.

        :param spec: CallSpec object being passed to the call method.
        :param args: args being passed to the call method.
        :param kwargs: kwargs being passed to the call method.
        """

        if spec.target.split('.')[-1] == 'add_parameter':
            name = spec.target.split('.')[0] + '.' + '.'.join(spec.args)
            pb = ParameterBroadcastBluePrint(name,
                                             'parameter-creation',
                                             kwargs['initial_value'],
                                             kwargs['unit'])
            self._broadcastParameterChange(pb)
        elif spec.target.split('.')[-1] == 'remove_parameter':
            name = spec.target.split('.')[0] + '.' + '.'.join(spec.args)
            pb = ParameterBroadcastBluePrint(name,
                                             'parameter-deletion')
            self._broadcastParameterChange(pb)


def startServer(port: int = 5555,
                allowUserShutdown: bool = False,
                addresses: List[str] = [],
                initScript: Optional[str] = None) -> \
        Tuple[StationServer, QtCore.QThread]:
    """Create a server and run in a separate thread.

    :returns: The server object and the thread it's running in.
    """
    server = StationServer(port=port,
                           allowUserShutdown=allowUserShutdown,
                           addresses=addresses,
                           initScript=initScript)
    thread = QtCore.QThread()
    server.moveToThread(thread)
    server.finished.connect(thread.quit)
    thread.started.connect(server.startServer)
    thread.start()
    return server, thread
