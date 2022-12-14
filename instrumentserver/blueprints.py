import inspect
import logging
from dataclasses import dataclass, field, fields
from typing import Union, Optional, List, Dict, Callable, Tuple

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
    vals: Optional[Validator] = None
    docstring: str = ''
    setpoints: Optional[List[str]] = None
    bp_type: str = 'parameter'

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.name}: {self.parameter_class}"

    # def __dict__(self) -> dict:
    #     param_dict = {}
    #     for my_field in fields(self):
    #         print(f'what are you my_field: {my_field} \n the type: {type(my_field)}')
    #         param_dict[my_field.name] = str(self.__getattribute__(my_field.name))
    #     return param_dict

    def tostr(self, indent=0):
        i = indent * ' '
        ret = f"""{self.name}: {self.parameter_class}
{i}- unit: {self.unit}
{i}- path: {self.path}
{i}- base class: {self.base_class}
{i}- gettable: {self.gettable}
{i}- settable: {self.settable}
{i}- validator: {self.vals}
{i}- setpoints: {self.setpoints}
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
        docstring=param.__doc__,
    )
    if hasattr(param, 'set'):
        bp.vals = param.vals
    if hasattr(param, 'setpoints'):
        bp.setpoints = [setpoint.name for setpoint in param.setpoints]

    return bp


@dataclass
class MethodBluePrint:
    """Spec necessary for creating method proxies."""
    name: str
    path: str
    call_signature: inspect.Signature
    docstring: str = ''
    bp_type: str = 'method'

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


@dataclass
class MethodBluePrintNew:
    """Spec necessary for creating method proxies"""
    name: str
    path: str
    call_signature_str: str
    signature_parameters: dict
    docstring: str = None
    bp_type: str = 'method'

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


def bluePrintFromMethod(path: str, method: Callable) -> Union[MethodBluePrint, None]:
    sig = inspect.signature(method)
    bp = MethodBluePrint(
        name=path.split('.')[-1],
        path=path,
        call_signature=sig,
        docstring=method.__doc__,
    )
    return bp


def bluePrintFromMethodNew(path: str, method: Callable) -> Union[MethodBluePrintNew, None]:
    sig = inspect.signature(method)
    sig_str, param_dict = MethodBluePrintNew.signature_str_and_params_from_obj(sig)
    bp = MethodBluePrintNew(
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
    bp_type: str = 'instrument'

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
        if callable(o) and not isinstance(o, tuple(PARAMETER_BASE_CLASSES)):
            meth_path = f"{path}.{elt}"
            meth_bp = bluePrintFromMethodNew(meth_path, o)
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
    bp_type: str = 'parameter_broadcast'

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


BluePrintType = Union[ParameterBluePrint, MethodBluePrint, MethodBluePrintNew, InstrumentModuleBluePrint, ParameterBroadcastBluePrint]


def _dictToJson(_dict: dict, json_type: bool=True) -> dict:
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


def bluePrintFromDict(bp: dict) -> BluePrintType:
    """
    Don't have nested items other than dictionaries containing more blueprints since we are not checking for those
    """
    if 'bp_type' not in bp:
        raise AttributeError(f'Blueprint does not indicates its type')

    bp_type = bp['bp_type']
    for key, value in bp.items():
        numeric_form = _is_numeric(value)
        if numeric_form is not None:
            bp[key] = numeric_form
        elif value == 'None':
            bp[key] = None
        elif value == 'True':
            bp[key] = True
        elif value == 'False':
            bp[key] = False

    if bp_type == 'parameter':
        return ParameterBluePrint(**bp)
    elif bp_type == 'method':
        return MethodBluePrintNew(**bp)
    elif bp_type == 'instrument':
        return InstrumentModuleBluePrint(**bp)
    elif bp_type == 'parameter_broadcast':
        return ParameterBroadcastBluePrint(**bp)
    else:
        raise AttributeError(f'Could not identify blueprint type {bp_type}')

