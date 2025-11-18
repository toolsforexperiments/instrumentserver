"""
Blueprints Module
=================

This module contains all objects that are being sent between client and server. This includes all of the blueprints
and other messaging objects (and its parts) like ServerInstruction and ServerResponse.

This module is responsible for defining them, present tools to create them and serializing them and deserializing them.

Any object that is ment to be sent, should have the method "toJson" implemented and should return a dictionary object
with all of its item json compatible. This however does not apply to any argument or keyword argument inside those
objects. These will each be tried to be serialized as best as possible. If an arbitrary class that is sent inside one
of the objects present in this module needs to be serialized, this class must have an attribute called "attributes"
inside listing all of the arguments that are needed to deserialize the class, these arguments must also be accepted
by the constructor of the class.

After passing the string through the json.loads function, to deserialize the object we call the deserialize_obj. If we
pass a dictionary containing the key '_class_type'. the function assumes that that dictionary is representing an object
that must be instantiated. If the key is missing, it will try to deserialize any value in the keys and return the
dictionary. If a list is passed, the function will go through the items in the list and deserialize them.

More Specifics for Developers
=============================

The server and client only communicate by sending a class that is in this module. You can split them in to 2
different categories: blueprints and instructions/information. The blueprints are used to represent instruments,
functions, and parameters for the client to utilize. While instructions/information are classes used to ask for
commands or request items and their responses.

All of the classes in the module contain the toJson method inside of them. For blueprints, their toJson calls the
function bluePrintToDict, which returns the blueprint in a dict representation with all the values as strings. The
function is smart enough such that if a blueprint has another blueprint inside, the inside blueprint gets properly
deserialized. This occurs for all attributes inside the blueprint.

The rest of the classes each handles its own serialization in their own toJson function. There are occasions when
classes like ServerInstruction, contain other classes of this module inside of it. When this happens the toJson function
of that class is called.

Special care is placed in serializing the args and kwargs fields of all of those classes, as they do not have
specified types and often require special handling. Because args always comes inside iterables, to serialize those
the function iterable_to_serialize_dict is called. The function goes through each item and serializes them one by
one. This ensures that any nested classes gets properly serialized. For kwargs, a similar process happens but for a
dictionary, the function dict_to_serialized_dict is called instead.

To deserialize objects the function deserialize_obj is called. If an object is a dictionary or an iterable (except
string) the function will go through all of the items inside of it trying to deserialize them as best as it can. A
few helper functions are used like _is_numeric and _convert_dict_to_obj. If a string is passed, it will try and pass
json.load to the string in case this happens because the first round of deserialization missed some nested object,
otherwise, it will keep it as a string.
"""

import importlib
import inspect
import json
import logging
from enum import Enum, unique
from collections.abc import Iterable
from dataclasses import dataclass, field, fields, asdict, is_dataclass, Field
from typing import Union, Optional, List, Dict, Callable, Tuple, Any, get_args, cast

import numpy as np
from qcodes import (
    Station, Instrument, InstrumentChannel, Parameter, ParameterWithSetpoints)
from qcodes.instrument.base import InstrumentBase
from qcodes.utils.validators import Validator

from .helpers import objectClassPath, typeClassPath

logger = logging.getLogger(__name__)

INSTRUMENT_MODULE_BASE_CLASSES = [
    Instrument, InstrumentChannel, InstrumentBase
]
InstrumentModuleType = Union[Instrument, InstrumentChannel, InstrumentBase]

PARAMETER_BASE_CLASSES = [
    Parameter, ParameterWithSetpoints
]

ParameterType = Union[Parameter, ParameterWithSetpoints]


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
    docstring: str = ''
    setpoints: Optional[List[str]] = None
    _class_type: str = 'ParameterBluePrint'

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.name}: {self.parameter_class}"

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{self.name}: {self.parameter_class}
{i}- unit: {self.unit}
{i}- path: {self.path}
{i}- base class: {self.base_class}
{i}- gettable: {self.gettable}
{i}- settable: {self.settable}
{i}- setpoints: {self.setpoints}
"""
        return ret

    def toJson(self):
        return bluePrintToDict(self)


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
        docstring=param.__doc__ or "",
    )
    if hasattr(param, 'setpoints'):
        bp.setpoints = [setpoint.name for setpoint in param.setpoints]

    return bp


@dataclass
class MethodBluePrint:
    """Spec necessary for creating method proxies"""
    name: str
    path: str
    call_signature_str: str
    signature_parameters: dict
    docstring: str = ""
    _class_type: str = 'MethodBluePrint'

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self.name}{str(self.call_signature_str)}"

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{self.name}{str(self.call_signature_str)}
{i}- path: {self.path}
"""
        return ret

    # we might want to be careful to keep them in the correct order
    @classmethod
    def signature_str_and_params_from_obj(cls, sig: inspect.Signature) -> Tuple[str, dict]:
        call_signature_str = str(sig)
        param_dict = {}
        for name, param in sig.parameters.items():
            param_dict[name] = str(param.kind)
        return call_signature_str, param_dict

    def toJson(self):
        return bluePrintToDict(self)


def bluePrintFromMethod(path: str, method: Callable) -> Union[MethodBluePrint, None]:
    sig = inspect.signature(method)
    sig_str, param_dict = MethodBluePrint.signature_str_and_params_from_obj(sig)
    bp = MethodBluePrint(
        name=path.split('.')[-1],
        path=path,
        call_signature_str=sig_str,
        signature_parameters=param_dict,
        docstring=method.__doc__ or "",
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
    _class_type: str = 'InstrumentModuleBluePrint'

    def __init__(self, name: str,
                 path: str,
                 base_class: str,
                 instrument_module_class: str,
                 docstring: str = '',
                 parameters: Optional[Dict[str, ParameterBluePrint]] = None,
                 methods: Optional[Dict[str, MethodBluePrint]] = None,
                 submodules: Optional[Dict[str, "InstrumentModuleBluePrint"]] = None,
                 _class_type: str = 'InstrumentModuleBluePrint'):

        self.name = name
        self.path = path
        self.base_class = base_class
        self.instrument_module_class = instrument_module_class
        self.docstring = docstring

        self.parameters = None
        if parameters is not None:
            self.parameters = {}
            for paramName, param in parameters.items():
                if isinstance(param, dict):
                    self.parameters[paramName] = deserialize_obj(param)
                elif isinstance(param, ParameterBluePrint):
                    self.parameters[paramName] = param
                else:
                    raise AttributeError("parameters has invalid type.")

        self.methods = None
        if methods is not None:
            self.methods = {}
            for methName, meth in methods.items():
                if isinstance(meth, dict):
                    self.methods[methName] = deserialize_obj(meth)
                elif isinstance(meth, MethodBluePrint):
                    self.methods[methName] = meth
                else:
                    raise AttributeError("methods has invalid type.")

        self.submodules = None
        if submodules is not None:
            self.submodules = {}
            for submodName, submod in submodules.items():
                if isinstance(submod, dict):
                    self.submodules[submodName] = deserialize_obj(submod)
                elif isinstance(submod, InstrumentModuleBluePrint):
                    self.submodules[submodName] = submod
                else:
                    raise AttributeError("parameters has invalid type.")

        self._class_type = 'InstrumentModuleBluePrint'

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

    def toJson(self):
        return bluePrintToDict(self)


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
        docstring=ins.__doc__ or "",
    )
    bp.parameters = {}
    bp.methods = {}
    bp.submodules = {}

    for pn, p in ins.parameters.items():
        param_path = f"{path}.{p.name}"
        p = cast(ParameterType, p)
        param_bp = bluePrintFromParameter(param_path, p)
        if param_bp is not None:
            bp.parameters[pn] = param_bp

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
                bp.methods[elt] = meth_bp

    for sn, s in ins.submodules.items():
        sub_path = f"{path}.{sn}"
        # FIXME: Fix this mypy ignore
        sub_bp = bluePrintFromInstrumentModule(sub_path, s)  # type:ignore[arg-type]
        if sub_bp is not None:
            bp.submodules[sn] = sub_bp

    return bp


@dataclass
class ParameterBroadcastBluePrint:
    """Blueprint to broadcast parameter changes."""
    name: str
    action: str
    value: int | None = None
    unit: str = ""
    _class_type: str = 'ParameterBroadcastBluePrint'

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
{i}- bp_type: {self.bp_type}
    """
        return ret

    def toJson(self):
        return bluePrintToDict(self)


BluePrintType = Union[ParameterBluePrint, MethodBluePrint, InstrumentModuleBluePrint, ParameterBroadcastBluePrint]


def _dictToJson(_dict: dict, json_type: bool = True) -> dict:
    ret: dict = {}
    for key, value in _dict.items():
        if isinstance(value, dict):
            ret[key] = _dictToJson(value, json_type)
        elif isinstance(value, get_args(BluePrintType)):
            ret[key] = bluePrintToDict(value, json_type)
        else:
            if json_type:
                ret[key] = str(value)
            else:
                ret[key] = value
    return ret


def bluePrintToDict(bp: BluePrintType, json_type=True) -> dict:
    """
    Converts a blueprint into a dictionary.

    :param bp: The blueprint to convert
    :param json_type: If True, the values are str. If False, the values remain the objects that are in the blueprint.
        Defaults True.
    """
    bp_dict: dict = {}
    for my_field in fields(bp):
        value = bp.__getattribute__(my_field.name)
        if isinstance(value, get_args(BluePrintType)):
            bp_dict[my_field.name] = bluePrintToDict(value, json_type)
        elif isinstance(value, dict):
            bp_dict[my_field.name] = _dictToJson(bp.__getattribute__(my_field.name), json_type)
        else:
            if json_type:
                bp_dict[my_field.name] = str(bp.__getattribute__(my_field.name))
            else:
                bp_dict[my_field.name] = bp.__getattribute__(my_field.name)
    return bp_dict


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

    #: Gets the GUI configuration for an instrument.
    get_gui_config = 'get_gui_config'


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

    _class_type: str = 'InstrumentCreationSpec'

    def toJson(self):
        ret = asdict(self)
        ret['args'] = iterable_to_serialized_dict(self.args)
        ret['kwargs'] = dict_to_serialized_dict(self.kwargs)
        return ret


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

    _class_type: str = 'CallSpec'

    def toJson(self):
        ret = asdict(self)
        ret['args'] = iterable_to_serialized_dict(self.args)
        ret['kwargs'] = dict_to_serialized_dict(self.kwargs)
        return ret


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

    _class_type: str = 'ParameterSerializeSpec'

    def toJson(self):
        ret = asdict(self)
        ret['args'] = iterable_to_serialized_dict(self.args)
        ret['kwargs'] = dict_to_serialized_dict(self.kwargs)
        return ret


@dataclass
class ServerInstruction:
    # TODO: Remove set parameter from the code.
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

    _class_type: str = 'ServerInstruction'

    def validate(self):
        if self.operation is Operation.create_instrument:
            if not isinstance(self.create_instrument_spec, InstrumentCreationSpec):
                raise ValueError('Invalid instrument creation spec.')

        if self.operation is Operation.call:
            if not isinstance(self.call_spec, CallSpec):
                raise ValueError('Invalid call spec.')

        if self.operation is Operation.get_gui_config:
            if not isinstance(self.requested_path, str):
                raise ValueError('Invalid requested path.')

    def toJson(self):
        ret = {'operation': str(self.operation.name)}

        if self.create_instrument_spec is None:
            ret['create_instrument_spec'] = None
        else:
            ret['create_instrument_spec'] = self.create_instrument_spec.toJson()

        if self.call_spec is None:
            ret['call_spec'] = None
        else:
            ret['call_spec'] = self.call_spec.toJson()

        if self.requested_path is None:
            ret['requested_path'] = None
        else:
            ret['requested_path'] = str(self.requested_path)

        if self.serialization_opts is None:
            ret['serialization_opts'] = None
        else:
            ret['serialization_opts'] = self.serialization_opts.toJson()

        ret['set_parameters'] = self.set_parameters
        ret['args'] = iterable_to_serialized_dict(self.args)
        ret['kwargs'] = dict_to_serialized_dict(self.kwargs)
        ret['_class_type'] = self._class_type

        return ret


@dataclass
class ServerResponse:
    """Spec for what the server can return. If the message is a string, it will assume it is a serialized json object
    and will try and deserialize it

    If the requested operation succeeds, `message` will the return of that operation,
    and `error` is None.
    See :class:`ServerInstruction` for a documentation of the expected returns.
    If an error occurs, `message` is typically ``None``, and `error` contains an
    error message or object describing the error.
    """
    #: The return message.
    message: Optional[Any] = None

    #: Any error message occurred during execution of the instruction.
    error: Optional[Union[None, str, Warning, Exception]] = None

    #: The type of the class, used for deserializing it.
    _class_type: str = 'ServerResponse'

    def __init__(self, message: Optional[Any] = None,
                 error: Optional[Union[None, str, Warning, Exception, dict]] = None,
                 _class_type: str = 'ServerResponse'):
        self.message = message
        if isinstance(message, str):
            try:
                # Replacing some key characters so that if the serializer missed it,
                # they can still be deserialize to objects and not strings.
                message = message.replace("'", '"')
                message = message.replace("(", "[")
                message = message.replace(")", "]")
                message = message.replace("T", "t")
                message = message.replace("F", "f")
                message = message.replace("None", "null")
                message = message.replace("none", "null")
                after_json_loads = json.loads(message)
                self.message = after_json_loads
            except json.JSONDecodeError as e:
                logger.debug(f'message could not be decoded by JSON and will be treated as a string: {message}')
        if isinstance(error, dict):
            self.error = Exception(error['message'])
        else:
            self.error = error

        self._class_type = 'ServerResponse'

    def toJson(self):
        ret = {}
        if isinstance(self.message, get_args(BluePrintType)):
            ret['message'] = self.message.toJson()
        elif hasattr(self.message, 'attributes'):
            ret['message'] = _convert_arbitrary_obj_to_dict(self.message)
        elif not isinstance(self.message, str) and isinstance(self.message, Iterable):
            if isinstance(self.message, dict):
                message_dict = dict_to_serialized_dict(self.message)
                ret['message'] = str(message_dict)
            else:
                message_iterable = iterable_to_serialized_dict(self.message)
                ret['message'] = str(message_iterable)
        else:
            ret['message'] = str(self.message)
        if isinstance(self.error, Exception):
            ret['error'] = dict(exception_type=str(type(self.error)), message=str(self.error))
        else:
            ret['error'] = str(self.error)

        ret['_class_type'] = self._class_type

        return ret


def _convert_arbitrary_obj_to_dict(obj: object) -> Dict[str, Any]:
    """
    Converts an arbitrary objects into a dictionary. Assumes that the object contains an attribute called
    'attributes' in which it lists all the attributes it needs for the object to be able to be serialized and that
    all of those attributes are natively JSON serializable. These should also be accepted as keyword arguments in the
    constructor of the object.
    """
    if not hasattr(obj, 'attributes'):
        raise AttributeError('Object does not have an attribute called "attributes"')

    obj_dict = {}
    for attr in obj.attributes:
        obj_dict[attr] = getattr(obj, attr)
    obj_dict['_class_type'] = f'{obj.__module__}.{obj.__class__.__name__}'
    return obj_dict


def _convert_dict_to_obj(item_dict: dict) -> Any:
    """
    Instantiates an object from an object dictionary. The reverse of the _convert_obj_to_dict. The constructor of the
    object should accept all of the items in the dictionary in the constructor.

    Assumes that the dictionary has a key '_class_type' indicating what class it should be instantiated from.
    """
    class_type = item_dict['_class_type']

    # if a dot is present indicates the class is arbitrary and needs to be imported
    if '.' in class_type:
        parts = class_type.split('.')
        mod = importlib.import_module('.'.join(parts[:-1]))
        cls = getattr(mod, parts[-1])
        item_dict.pop('_class_type')
        return cls(**item_dict)

    try:
        instantiated_obj = eval(f'{class_type}(**item_dict)')
    # built-ins (like complex) will not want the _class_type argument
    except TypeError:
        cls = item_dict.pop('_class_type')
        instantiated_obj = eval(f'{cls}(**item_dict)')

    return instantiated_obj


def iterable_to_serialized_dict(iterable: Optional[Iterable[Any]] = None):
    """
    Goes through an iterable (lists, tuples, sets) and serialize each object inside of it. If trying to serialize an
    arbitrary object, this object must have a class attribute "attributes" for the serialization to happen correctly.

    returns a list with the args as serialized dictionaries.

    The current rules:
        - Any arbitrary object that is being serialized here must have a class attribute listing all the classes attributes that
        the constructor needs to create an identical instance of that class
        - The serialized dictionary need to have the field: '_class_type', to indicate what it is that needs to be
        instantiated.
    """
    converted_iterable: list | dict | None = None
    if iterable is not None:
        converted_iterable = []
        for item in iterable:
            # Check if the object is iterable since the objects inside the iterable should be serialized too.
            # All of the specific iterable objects should go before the generic if to catch them before.
            if isinstance(item, dict):
                serialized_iterable = dict_to_serialized_dict(dct=item)
                converted_iterable.append(serialized_iterable)

            elif not isinstance(item, str) and isinstance(item, Iterable):
                serialized_iterable = iterable_to_serialized_dict(iterable=item)
                converted_iterable.append(serialized_iterable)

            elif hasattr(item, 'attributes'):
                arg_dict = _convert_arbitrary_obj_to_dict(item)
                converted_iterable.append(arg_dict)

            elif isinstance(item, complex):
                arg_dict = dict(real=item.real, imag=item.imag, _class_type='complex')
                converted_iterable.append(arg_dict)

            else:
                converted_iterable.append(str(item))

        if isinstance(iterable, np.ndarray):
            converted_iterable = dict(object=converted_iterable, _class_type="numpy.array")

    return converted_iterable


def dict_to_serialized_dict(dct: Optional[Dict[str, Any]] = None):
    """
    Same idea as iterable_to_serialized_dict but for dictionaries.
    """

    converted_dict = None
    if dct is not None:
        converted_dict = {}
        for name, value in dct.items():
            # Check if the object is iterable since the objects inside the iterable should be serialized too.
            # All of the specific iterable objects should go before the generic if to catch them before.
            if isinstance(value, dict):
                serialized_iterable = dict_to_serialized_dict(dct=value)
                converted_dict[name] = serialized_iterable

            elif not isinstance(value, str) and isinstance(value, Iterable):
                serialized_iterable = iterable_to_serialized_dict(iterable=value)
                converted_dict[name] = serialized_iterable

            elif hasattr(value, 'attributes'):
                kwarg_dict = _convert_arbitrary_obj_to_dict(value)
                converted_dict[name] = kwarg_dict
            elif isinstance(value, complex):
                kwarg_dict = dict(real=value.real, imag=value.imag, _class_type='complex')
                converted_dict[name] = kwarg_dict
            else:
                converted_dict[name] = str(value)

    return converted_dict


def to_dict(data) -> Union[Dict[str, str], str]:
    """
    Converts object to json serializable. This is done by calling the method toJson of the object being passed.
    Strings are returned without any more processing.
    """
    if isinstance(data, str):
        return data

    return data.toJson()


def _is_numeric(val) -> Optional[Union[float, complex]]:
    """
    Tries to convert the input into a int or a float. If it can, returns the conversion. Otherwise returns None.
    """
    try:
        if val is not None and not '.' in val:
            int_conversion = int(val)
            return int_conversion
    except Exception:
        pass

    try:
        float_conversion = float(val)
        return float_conversion
    except Exception:
        pass

    try:
        complex_conversion = complex(val)
        return complex_conversion
    except Exception:
        pass

    return None


def deserialize_obj(data: Any):
    """
    Tries to deserialize any object. If the object is a dictionary and contains the key '_class_type' it means that
    that dictionary represents a serialized object that needs to be instantiated. The function will try and deserailize
    any other item in the dictionary.
    """
    if data is None or data == 'None':
        return None

    elif isinstance(data, dict):
        deserialized_dict = {}
        for key, value in data.items():
            deserialized_dict[key] = deserialize_obj(value)
        if '_class_type' in deserialized_dict:
            obj_instance = _convert_dict_to_obj(deserialized_dict)
            return obj_instance

        return deserialized_dict

    numeric_form = _is_numeric(data)
    if numeric_form is not None:
        return numeric_form
    elif data == 'True':
        return True
    elif data == 'False':
        return False
    elif data == '{}':
        return {}
    elif data == '[]':
        return []

    elif isinstance(data, str):
        if len(data) > 0:
            # Try and load other items in the string it since it might be a nested item
            if (data[0] == '{' and data[-1] == '}') or (data[0] == '[' and data[-1] == ']'):
                try:
                    loaded_json = json.loads(data.replace("'", '"'))
                    return deserialize_obj(loaded_json)
                except json.JSONDecodeError as e:
                    logger.debug('str could not be decoded, treating it as a str')

        return data

    elif isinstance(data, Iterable):
        deserialized_iterable = []
        for item in data:
            deserialized_iterable.append(deserialize_obj(item))
        # Returns the same type of iterable
        return deserialized_iterable

