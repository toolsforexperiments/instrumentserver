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
from dataclasses import dataclass, field, fields
from enum import Enum, unique
from typing import Dict, Any, Union, Optional, Tuple, List, Callable

import zmq

import qcodes as qc
from qcodes import (
    Station, Instrument, InstrumentChannel, Parameter, ParameterWithSetpoints)
from qcodes.instrument.base import InstrumentBase
from qcodes.utils.validators import Validator

from .. import QtCore, serialize
from ..blueprints import (ParameterBluePrint, MethodBluePrint, InstrumentModuleBluePrint, ParameterBroadcastBluePrint,
                          bluePrintFromMethod, bluePrintFromInstrumentModule, bluePrintFromParameter,
                          INSTRUMENT_MODULE_BASE_CLASSES, PARAMETER_BASE_CLASSES, Operation,
                          InstrumentCreationSpec, CallSpec, ParameterSerializeSpec, ServerInstruction, ServerResponse,)

from ..base import send, recv
from ..helpers import nestedAttributeFromString, objectClassPath, typeClassPath

__author__ = 'Wolfgang Pfaff', 'Chao Zhou'
__license__ = 'MIT'

logger = logging.getLogger(__name__)


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
            lambda n, v: logger.info(f"Parameter '{n}' retrieved: {str(v)}")
        )
        self.funcCalled.connect(
            lambda n, args, kw, ret: logger.info(f"Function called:"
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
                logger.debug(response_log)

            # We assume this is a valid instruction set now.
            elif isinstance(message, ServerInstruction):
                instruction = message
                try:
                    instruction.validate()
                    logger.debug(f"Received request for operation: "
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
                        logger.debug(f"Response sent to client.")
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

        operation = Operation(instruction.operation)
        # We call a helper function depending on the operation that is requested.
        if operation == Operation.get_existing_instruments:
            func = self._getExistingInstruments
        elif operation == Operation.create_instrument:
            func = self._createInstrument
            args = [instruction.create_instrument_spec]
        elif operation == Operation.call:
            func = self._callObject
            args = [instruction.call_spec]
        elif operation == Operation.get_blueprint:
            func = self._getBluePrint
            args = [instruction.requested_path]
        elif operation == Operation.get_param_dict:
            func = self._toParamDict
            args = [instruction.serialization_opts]
        elif operation == Operation.set_params:
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

    def _getExistingInstruments(self) -> List[str]:
        """
        Get the existing instruments in the station.

        :returns: A list that contains the instrument name.
        """
        comps = self.station.components
        info = [key for key in comps.keys()]
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
            instrument_class=cls, name=spec.name, *args, **kwargs)
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
        obj = nestedAttributeFromString(self.station, path)
        if isinstance(obj, tuple(INSTRUMENT_MODULE_BASE_CLASSES)):
            return bluePrintFromInstrumentModule(path, obj)
        elif isinstance(obj, tuple(PARAMETER_BASE_CLASSES)):
            return bluePrintFromParameter(path, obj)
        elif callable(obj):
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
