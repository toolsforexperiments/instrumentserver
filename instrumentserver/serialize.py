"""
instrumentserver.serialize
^^^^^^^^^^^^^^^^^^^^^^^^^^

Serializing and de-serializing instruments and parameters.
The tools in here can be used to perform the following tasks:

    * Store instrument and parameter information to json.

    * Load instrument and parameter information from json.

The main utility of the methods here is to have a relatively simple representation
of the state of the system (by system we mean: either a qcodes station, or simply
a collection of qcodes instruments and parameters).
All of this information is also provided by the qcodes snaphot.
This module is currently intended to supplement that with a format that is easier
to read and contains only state information (such as values).

The main methods here are :func:`toParamDict` and :func:`fromParamDict`, which allow
extracting instrument parameters to JSON and load parameters from JSON.

The main format for the JSON objects we work with follows this scheme::

    paramDict = {
        "parameter_name": {
            "value": value,
            "unit": "unit of this parameter",
            [...]
        },
        "instrument.instrument_parameter": {
            "value": value,
            "unit": "the unit of this parameter",
            [...]
        },
        "another_instrument.a_submodule.some_parameter": {
            "value": value,
            [...]
        }
    }

Only "value" is required as key for each parameter, but arbitrary additional meta
data can be added in principle.
The naming of the parameters is the same way in which they would be addressed inside
a qcodes station.
I.e., if the parameter is called using::

    station.[parent object(s)].parameter()

Then the name in `paramDict` is "[parent objects(s)].parameter".

In case the only property of each parameter is `value`, then it is also possible
to use a simplified format which looks like this::

    paramDict = {
        "parameter_name": value,
        "instrument.instrument_parameter": value,
        "another_instrument.a_submodule.some_parameter": value,
    }

This format is sufficient to store/load parameter values, but not to create
parameters that are not present yet.
"""

# TODO: would be good to have a serialization format the also captures validators,
#  for example. But that would mean we need to use either binary, or come up with
#  something that allows recreation from text.
# TODO: make a proper type from the paramdict?

import json
import logging
import os
from typing import Dict, List, Any, Union
from dataclasses import fields, dataclass

from jsonschema import validate
import pandas as pd
from qcodes import Instrument, Station, Parameter
from qcodes.instrument.base import InstrumentBase

from . import PARAMS_SCHEMA_PATH


logger = logging.getLogger(__name__)

SerializableType = Union[Station, List[Union[InstrumentBase, Parameter]]]


def toParamDict(input: SerializableType,
                get: bool = False,
                includeMeta: List[str] = [],
                excludeParameters: List[str] = [],
                simpleFormat: bool = True) -> Dict:
    """Create a dictionary that holds parameter values, and optionally additional
    information about them.

    :param input: qcodes station or list of instruments/parameters.
    :param get: Whether to call `get` on the parameters.
        If not, use the values from the current snapshot.
        Note: Parameters that are not included in the snapshot are never included.
    :param includeMeta: List of parameter attributes to include besides value.
        All keys occurring in snapshots are valid.
    :param excludeParameters: List of parameters we don't include in the return.
    :param simpleFormat: If ``True`` and no additional metadata is included,
        then the output format will be simplified such that the the value for
        each parameter key is simply `value`, rather than a dictionary of
        multiple properties.
    :returns: Dictionary. If not simple format, conforms to
        instrumentserver/schemas/parameters.json

    """
    if isinstance(input, Station):
        if hasattr(input, "get_snapshot"):
            snap = input.get_snapshot()
        else:
            snap = input.snapshot()
        input = [getattr(input, k) for k in snap['instruments'].keys()] \
            + [getattr(input, k) for k in snap['parameters'].keys()] \
            + [getattr(input, k) for k in snap['components'].keys()]

    ret = {}
    for obj in input:
        if isinstance(obj, InstrumentBase):
            ret.update(_singleInstrumentParametersToJson(
                obj, get=get, addPrefix=f"{obj.name}.",
                includeMeta=includeMeta,
                simpleFormat=simpleFormat,
                excludeParameters=excludeParameters))

        elif isinstance(obj, Parameter):
            ret.update(_singleParameterToJson(
                obj, get=get, simpleFormat=simpleFormat,
                includeMeta=includeMeta))

        else:
            raise ValueError(f"Invalid object: {obj}. Can only process "
                             f"Station, Instrument, and Parameter.")

    return ret


def fromParamDict(paramDict: Dict[str, Any],
                  target: SerializableType) -> None:
    """Load parameter values from JSON.

    :param paramDict: The parameter dictionary in a valid JSON format (may be
        simple or regular format).
    :param target: Object(s) holding the parameters to load.
    """

    validateParamDict(paramDict)
    simple = isSimpleFormat(paramDict)

    for k in sorted(paramDict.keys()):
        paramAsList = k.split('.')
        parent = _getObjectByName(paramAsList[0], src=target)

        if parent is None:
            logger.info(f"[{k}] Cannot find '{paramAsList[0]}', ignore.")
            continue

        try:
            param = _getParamFromList(parent, paramAsList[1:])
        except AttributeError:
            logger.info(f"[{k}] not present in target, ignore.")
            continue

        if simple:
            value = paramDict[k]
        else:
            value = paramDict[k]['value']

        if hasattr(param, 'set'):
            logger.info(f"[{k}] set to: {value}")
            try:
                param.set(value)
            except Exception as e:
                logger.error(f"\t{type(e)}: {e}")
        else:
            logger.info(f"[{k}] does not support setting, ignore.")

# Tools

def saveParamsToFile(input: SerializableType,
                     filePath: str, **kw: Any) -> None:
    """Save (instrument) parameters to file.

    First obtains the parameters from :func:`toParamDict`, then saves its output.

    :param input: qcodes station or list of instruments/parameters.
    :param filePath: Output file path.
    :param kw: Options, all passed to :func:`toParamDict`.
    :returns:
    """
    ret = toParamDict(input, **kw)
    filePath = os.path.abspath(filePath)
    folder, file = os.path.split(filePath)
    if not os.path.exists(folder):
        os.makedirs(folder)
    with open(filePath, 'w') as f:
        json.dump(ret, f, indent=2, sort_keys=True)


def loadParamsFromFile(filePath: str,
                       target: SerializableType) -> None:
    """Load (instrument) parameters from file.

    Loads the json from file, then tries to restore the state into the target,
    using :func:`fromParamDict`.
    """
    ret = None
    with open(filePath, 'r') as f:
        ret = json.load(f)
    fromParamDict(ret, target)


def isSimpleFormat(paramDict: Dict[str, Any]):
    """Checks if the supplied paramDict is in the simplified format.

    We identify the simple format by the fact that otherwise **all** item values
    are a dictionary with a least the key `value` in it.
    """
    for k, v in paramDict.items():
        if not isinstance(v, dict) or not "value" in v:
            return True

    return False


def validateParamDict(params: Dict[str, Any]):
    if isSimpleFormat(params):
        return

    with open(PARAMS_SCHEMA_PATH) as f:
        schema = json.load(f)
    try:
        validate(params, schema)
    except:
        raise


def toDataFrame(input: SerializableType):
    """Make a pandas data frame from the parameters. Mainly useful for
    printing overviews in notebooks."""
    params = toParamDict(input, includeMeta=['unit', 'vals'])
    return pd.DataFrame(params).T.sort_index()


# private tool functions

def _singleParameterToJson(parameter: Parameter,
                           get: bool = False,
                           includeMeta: List[str] = [],
                           simpleFormat: bool = True) -> Dict:
    """Create a JSON representation of a parameter."""

    ret: dict[str, Any] = {parameter.name: None}
    if hasattr(parameter, "get_snapshot"):
        snap = parameter.get_snapshot(update=get)
    else:
        snap = parameter.snapshot(update=get)
    if len(includeMeta) == 0 and simpleFormat:
        ret[parameter.name] = snap.get('value', None)
    else:
        ret[parameter.name] = dict()
        for k in ['value'] + includeMeta:
            ret[parameter.name][k] = snap.get(k, None)

    return ret


def _singleInstrumentParametersToJson(instrument: InstrumentBase,
                                      get: bool = False,
                                      addPrefix: str = '',
                                      includeMeta: List[str] = [],
                                      excludeParameters: List[str] = [],
                                      simpleFormat: bool = True) -> Dict:
    """Create a dictionary that holds the parameters of an instrument."""

    if "IDN" not in excludeParameters:
        excludeParameters.append("IDN")

    ret = {}
    if hasattr(instrument, "get_snapshot"):
        snap = instrument.get_snapshot(update=get)
    else:
        snap = instrument.snapshot(update=get)
    for name, param in instrument.parameters.items():
        if name not in excludeParameters:
            if len(includeMeta) == 0 and simpleFormat:
                ret[addPrefix + name] = snap['parameters'][name].get('value', None)
            else:
                ret[addPrefix + name] = dict()
                for k, v in snap['parameters'][name].items():
                    if k in (['value'] + includeMeta):
                        ret[addPrefix + name][k] = v
        else:
            logger.debug(f"excluded: {addPrefix + name}")

    for name, submod in instrument.submodules.items():
        ret.update(_singleInstrumentParametersToJson(
            # FIXME: Fix this mypy ignore
            submod, get=get, addPrefix=f"{addPrefix + name}.",  # type: ignore[arg-type]
            simpleFormat=simpleFormat, includeMeta=includeMeta))
    return ret


def _getParamFromList(parent: Any, childrenList: List[str]) -> Parameter:
    """Return the lowest attribute in the hierarchy:
    returns the object described by parent.<child_0>.<child_1>.[...].<child_N>.
    Works for any `N` >= 0.

    For 2 children, an equivalent code would be:
    >>> getattr(getattr(parent, childrenList[0]), childrenList[1])
    """

    if len(childrenList) == 0:
        return parent
    nextObj = getattr(parent, childrenList[0])
    if len(childrenList) == 1:
        return nextObj
    else:
        return _getParamFromList(nextObj, childrenList[1:])


def _getObjectByName(name: str,
                     src: SerializableType):
    """Get an object from a container by specifying its name."""

    if isinstance(src, Station):
        try:
            ret = getattr(src, name)
        except AttributeError:
            ret = None
        return ret
    if isinstance(src, list):
        for elt in src:
            if elt.name == name:
                return elt
    return None

