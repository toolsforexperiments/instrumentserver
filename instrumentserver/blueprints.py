import inspect
import json
import logging
from enum import Enum, unique
from dataclasses import dataclass, field, fields, asdict, is_dataclass
from typing import Union, Optional, List, Dict, Callable, Tuple, Any

import qcodes as qc
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
        docstring=param.__doc__,
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
    docstring: str = None
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
    def signature_str_and_params_from_obj(cls, sig: inspect.signature) -> Tuple[str, dict]:
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
    _class_type: str = 'InstrumentModuleBluePrint'

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
        if callable(o) and not isinstance(o, tuple(PARAMETER_BASE_CLASSES)):
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

    # TODO: Delete this once we move to json serializable
    def toDictFormat(self):
        """
        Formats the blueprint for easy conversion to dictionary later.
        """
        ret = f"'name': '{self.name}'," \
              f" 'action': '{self.action}'," \
              f" 'value': '{self.value}'," \
              f" 'unit': '{self.unit}'"
        return "{"+ret+"}"

    def toJson(self):
        return bluePrintToDict(self)


BluePrintType = Union[ParameterBluePrint, MethodBluePrint, InstrumentModuleBluePrint, ParameterBroadcastBluePrint]


def _dictToJson(_dict: dict, json_type: bool = True) -> dict:
    ret = {}
    for key, value in _dict.items():
        if isinstance(value, dict):
            ret[key] = _dictToJson(value, json_type)
        elif isinstance(value, BluePrintType):
            ret[key] = bluePrintToDict(value, json_type)
        else:
            if json_type:
                ret[key] = str(value)
            else:
                ret[key] = value
    return ret


def bluePrintToDict(bp: BluePrintType,  json_type=True) -> dict:
    bp_dict = {}
    for my_field in fields(bp):
        value = bp.__getattribute__(my_field.name)
        if isinstance(value, BluePrintType):
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
        return asdict(self)


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
        return asdict(self)


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
        return asdict(self)


@dataclass
class ServerInstruction:
    #TODO: Remove set parameter from the code.
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
        ret['args'] = self.args
        ret['kwargs'] = self.kwargs
        ret['_class_type'] = self._class_type

        return ret


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

    #: Any error message occurred during execution of the instruction.
    error: Optional[Union[None, str, Warning, Exception]] = None

    _class_type: str = 'ServerResponse'

    def __init__(self, message: Optional[Any] = None,
                 error: Optional[Union[None, str, Warning, Exception, dict]] = None,
                 _class_type: str = 'ServerResponse'):
        self.message = message
        if isinstance(message, str):
            try:
                # TODO: have this documented somewhere that these replacements are happening so we can deserialize it
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
                logger.info(f'message could not be decoded by JSON and will be treated as a string: {message}')
        if isinstance(error, dict):
            self.error = Exception(error['message'])
        else:
            self.error = error

        self._class_type = 'ServerResponse'

    def toJson(self):
        ret = {}
        if isinstance(self.message, BluePrintType):
            ret['message'] = self.message.toJson()
        else:
            ret['message'] = str(self.message)
        if isinstance(self.error, Exception):
            ret['error'] = dict(exception_type=str(type(self.error)), message=str(self.error))
        else:
            ret['error'] = str(self.error)

        ret['_class_type'] = self._class_type

        return ret


def to_dict(data) -> Union[Dict[str, str], str]:
    """
    Converts object to json serializable. This is done by calling the method toJson of the object being passed.
    Strings are returned without any more processing.
    """
    if isinstance(data, str):
        return data

    return data.toJson()


def _is_numeric(val) -> Optional[Union[int, float]]:
    try:
        int_conversion = int(val)
        return int_conversion
    except Exception:
        pass

    try:
        float_conversion = float(val)
        return float_conversion
    except Exception:
        pass

    return None


def from_dict(data: Union[dict, str]) -> Any:
    """
    Don't have nested items other than dictionaries containing more blueprints since we are not checking for those
    """
    if isinstance(data, str):
        return data

    if '_class_type' not in data:
        raise AttributeError(f'message does not indicates its type: {data}')

    class_type = data['_class_type']

    # Convert some things that the JSON decoder misses.
    for key, value in data.items():
        numeric_form = _is_numeric(value)
        if numeric_form is not None:
            data[key] = numeric_form
        elif value == 'None':
            data[key] = None
        elif value == 'True':
            data[key] = True
        elif value == 'False':
            data[key] = False
        elif value == '{}':
            data[key] = {}
        elif isinstance(value, dict):
            if '_class_type' in value:
                data[key] = from_dict(value)
        elif isinstance(value, str):
            if len(value) > 0:
                if value[0] == '{' and value[-1] == '}':
                    try:
                        data[key] = json.loads(value.replace("'", '"'))
                    except json.JSONDecodeError as e:
                        logger.error(f'Could not decode: "{value}".'
                                     f' It does not conform to JSON standard, Might not be correct once used: {e}.')

    if class_type == 'ParameterBluePrint':
        return ParameterBluePrint(**data)
    elif class_type == 'MethodBluePrint':
        return MethodBluePrint(**data)
    elif class_type == 'InstrumentModuleBluePrint':
        instr_bp = InstrumentModuleBluePrint(**data)
        # InstrumentModuleBluePrint has nested items that are serialized and need to be instantiated too.
        if data['methods'] is not None:
            methods = {key: from_dict(value) for key, value in data['methods'].items()}
            instr_bp.methods = methods
        if data['parameters'] is not None:
            parameters = {key: from_dict(value) for key, value in data['parameters'].items()}
            instr_bp.parameters = parameters
        if data['submodules'] is not None:
            submodules = {key: from_dict(value) for key, value in data['submodules'].items()}
            instr_bp.submodules = submodules
        return instr_bp
    elif class_type == 'ParameterBroadcastBluePrint':
        return ParameterBroadcastBluePrint(**data)
    elif class_type == 'InstrumentCreationSpec':
        return InstrumentCreationSpec(**data)
    elif class_type == 'CallSpec':
        return CallSpec(**data)
    elif class_type == 'ParameterSerializeSpec':
        return ParameterSerializeSpec(**data)
    elif class_type == 'ServerInstruction':
        return ServerInstruction(**data)
    elif class_type == 'ServerResponse':
        return ServerResponse(**data)
    else:
        raise AttributeError(f'Could not decode {class_type}')
