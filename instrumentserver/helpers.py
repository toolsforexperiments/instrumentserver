import inspect
from typing import Dict, Any, List, Union, Tuple

from qcodes import Instrument, Parameter

from .serialize import toParamDict


# TODO: check for usage of get params / methods functions -- might not be needed


def stringToArgsAndKwargs(value: str) -> Tuple[List[Any], Dict[str, Any]]:
    """create argument list and kwarg dict from a string.

    Example::
        >>> stringToArgsAndKwargs("1, True, abc=12.3")
        [1, True], {'abc': 12.3}

    :returns: list of arguments and dictionary with keyword arguments.

    :raises: ``ValueError`` if:
        - kwargs are not in the right format (i.e. not``key=value``)
        - args or kwarg values cannot be evaluated with ``eval``.
    """
    value = value.strip()
    if value == '':
        return [], {}

    args = []
    kwargs = {}
    elts = [v.strip() for v in value.split(',')]
    for elt in elts:
        if '=' in elt:
            keyandval = elt.split('=')
            if len(keyandval) != 2:
                raise ValueError(f"{elt} cannot be interpreted as kwarg")
            try:
                kwargs[keyandval[0].strip()] = eval(keyandval[1].strip())
            except Exception as e:
                raise ValueError(f"Cannot evaluate '{keyandval[1]}', {type(e)} raised.")
        else:
            try:
                args.append(eval(elt))
            except Exception as e:
                raise ValueError(f"Cannot evaluate '{elt}', {type(e)} raised.")

    return args, kwargs


def typeClassPath(t) -> str:
    return f"{t.__module__}.{t.__qualname__}"


def objectClassPath(o) -> str:
    return f"{o.__class__.__module__}.{o.__class__.__qualname__}"


def nestedAttributeFromString(root: Any, loc: str) -> Any:
    """return a sub-object. Example::

        >>> nestedAttributeFromString(parent_object, 'foo.bar.spam.bacon')

    returns the object that can be found at parent_object.foo.bar.spam.bacon.
    """
    mods = loc.split('.')
    obj = root
    for m in mods:
        obj = getattr(obj, m)
    return obj


def getInstrumentParameters(ins: Instrument) -> Dict[str, Dict[str, str]]:
    """return the parameters of an instrument.

    :param ins: instrument instance
    :returns: a param dict with entries `unit`, `vals`, for each
        instrument parameter.
    """
    paramDict = toParamDict([ins], includeMeta=['unit', 'vals'])
    for k, v in paramDict.items():
        paramDict[k].pop('value', None)
    return paramDict


def getInstrumentMethods(ins: Instrument) -> Dict[str, Dict[str, Union[str, List[str]]]]:
    """return the methods of an instrument.

    :param ins: instrument instance
    :returns: a dictionary, with keys being the names of methods that are not private
        and not inherited from qcodes.Instrument. Each entry is a dictionary containing:
        - 'parameters': List of string representations of the parameters
        - 'doc': Docstring of the method
        - 'return': string representation of the return type.
    """
    funcs = {}
    for attr_name in dir(ins):
        if attr_name[0] != '_' and attr_name not in dir(Instrument):
            obj = getattr(ins, attr_name)
            if callable(obj) and not isinstance(obj, Parameter):
                funcs[attr_name] = dict()

    for fname in funcs.keys():
        fun = getattr(ins, fname)
        signature = inspect.signature(fun)
        funcs[fname]['parameters'] = [str(signature.parameters[a]) for a in
                                      signature.parameters]
        funcs[fname]['doc'] = str(fun.__doc__)
        funcs[fname]['return'] = str(signature.return_annotation)

    return funcs


