import os
from typing import Any, Dict, Union, List
from enum import Enum, unique, auto

import json
from qcodes import Instrument, Parameter
from qcodes.instrument.base import InstrumentBase
from qcodes.utils import validators

from . import serialize
from .server.core import ParameterBluePrint, bluePrintFromParameter

@unique
class ParameterTypes(Enum):
    any = auto()
    numeric = auto()
    integer = auto()
    string = auto()
    bool = auto()
    complex = auto()


parameterTypes = {
    ParameterTypes.any:
        {'name': 'Any',
         'validatorType': validators.Anything},
    ParameterTypes.numeric:
        {'name': 'Numeric',
         'validatorType': validators.Numbers},
    ParameterTypes.integer:
        {'name': 'Integer',
         'validatorType': validators.Ints},
    ParameterTypes.string:
        {'name': 'String',
         'validatorType': validators.Strings},
    ParameterTypes.bool:
        {'name': 'Boolean',
         'validatorType': validators.Bool},
    ParameterTypes.complex:
        {'name': 'Complex',
         'validatorType': validators.ComplexNumbers},
}


def paramTypeFromVals(vals: validators.Validator) -> Union[ParameterTypes, None]:
    if vals is None:
        vals = validators.Anything()

    for k, v in parameterTypes.items():
        if isinstance(vals, v['validatorType']):
            return k

    return None


def paramTypeFromName(name: str) -> Union[ParameterTypes, None]:
    for k, v in parameterTypes.items():
        if name == v['name']:
            return k
    return None


class ParameterManager(InstrumentBase):
    """
    A virtual instrument that acts as a manager for a collection of
    arbitrary parameters and groups of parameters.

    Allows extra-easy on-the-fly addition/removal of new parameters.
    """

    # TODO: method to instantiate entirely from paramDict

    def __init__(self, name):
        super().__init__(name)

        #: default location and name of the parameters save file.
        self._paramValuesFile = os.path.join(os.getcwd(), f'parameter_manager_{self.name}.json')

    @staticmethod
    def createFromParamDict(paramDict: Dict[str, Any], name: str) -> "ParameterManager":
        """Create a new ParameterManager instance from a paramDict.

        :param paramDict: the paramDict object.
        :param name: name of the instrument in the paramDict (each entry in the
            paramDict starts with <instrumentName>.[...])
        :returns: new ParameterManager instance.
        """
        raise NotImplementedError

    @classmethod
    def _to_tree(cls, pm: 'ParameterManager') -> Dict:
        ret = {}
        for smn, sm in pm.submodules.items():
            ret[smn] = cls._to_tree(sm)
        for pn, p in pm.parameters.items():
            ret[pn] = p
        return ret

    def to_tree(self):
        return ParameterManager._to_tree(self)

    def _get_param(self, param_name: str) -> Parameter:
        parent = self._get_parent(param_name)
        try:
            param = parent.parameters[param_name.split('.')[-1]]
            return param
        except KeyError:
            raise ValueError(f"Parameter '{param_name}' does not exist")

    def _get_parent(self, param_name: str, create_parent: bool = False) \
            -> 'ParameterManager':

        split_names = param_name.split('.')
        parent = self
        full_name = self.name

        for i, n in enumerate(split_names[:-1]):
            full_name += f'.{n}'
            if n in parent.parameters:
                raise ValueError(f"{n} is a parameter, and cannot have child parameters.")
            if n not in parent.submodules:
                if create_parent:
                    parent.add_submodule(n, ParameterManager(n))
                else:
                    raise ValueError(f'{n} does not exist.')
            parent = parent.submodules[n]
        return parent

    def has_param(self, param_name: str):
        try:
            param = self._get_param(param_name)
            return True
        except ValueError:
            return False

    def add_parameter(self, name: str, **kw: Any) -> None:
        """Add a parameter.

        :param name: name of the parameter.
            if the name contains `.`s, then an element before a dot is interpreted
            as a submodule. multiple dots represent nested submodules. I.e., when
            we supply ``foo.bar.foo2`` we have a top-level submodule ``foo``,
            containing a submodule ``bar``, containing the parameter ``foo2``.
            Submodules are generated on demand.
        :param kw: Any keyword arguments will be passed on to
            qcodes.Instrument.add_parameter, except:
            - ``set_cmd`` is always set to ``None``
            - ``parameter_class`` is ``qcodes.Parameter``
            - ``vals`` defaults to ``qcodes.utils.validators.Anything()``.
        :return: None
        """
        kw['parameter_class'] = Parameter
        if 'vals' not in kw:
            kw['vals'] = validators.Anything()
        kw['set_cmd'] = None

        parent = self._get_parent(name, create_parent=True)
        if parent is self:
            super().add_parameter(name.split('.')[-1], **kw)
        else:
            parent.add_parameter(name.split('.')[-1], **kw)

    def remove_parameter(self, param_name: str, cleanup: bool = True):
        parent = self._get_parent(param_name)
        pname = param_name.split('.')[-1]
        del parent.parameters[pname]
        if cleanup:
            self.remove_empty_submodules()

    def get(self, param_name: str) -> Any:
        param = self._get_param(param_name)
        return param.get()

    def set(self, param_name: str, value: Any) -> Any:
        param = self._get_param(param_name)
        param.set(value)

    def remove_empty_submodules(self):
        """delete all empty submodules in the instrument."""

        def is_empty(parent):
            if len(parent.submodules) == 0 and len(parent.parameters) == 0:
                return True
            else:
                return False

        def purge(parent):
            mark_for_deletion = []
            for n, s in parent.submodules.items():
                purge(s)
                if is_empty(s):
                    mark_for_deletion.append(n)
            for n in mark_for_deletion:
                del parent.submodules[n]

        purge(self)

    def parameter(self, name: str) -> "Parameter":
        """get a parameter object from the manager.

        :param name: the full name
        :returns: the parameter
        """
        return self._get_param(name)

    def list(self) -> List[str]:
        """return a list of all parameters."""
        tree = self.to_tree()

        def tolist(x):
            ret_ = []
            for k, v in x.items():
                if isinstance(v, Parameter):
                    ret_.append(f"{k}")
                else:
                    ret_ += [f"{k}.{e}" for e in tolist(v)]
            return ret_

        return tolist(tree)

    def fromFile(self, filePath: str = None, deleteMissing: bool = True):
        """load parameters from a parameter json file
        (see :mod:`.serialize`).

        :param filePath: path to the json file. If ``None`` it looks in the instrument current location
                         directory for a file called "parametermanager_parameters.json"
        :param deleteMissing: if ``True``, delete parameters currently in the
            ParameterManager that are not listed in the file.
        """
        if filePath is None:
            filePath = self._paramValuesFile

        with open(filePath, 'r') as f:
            pd = json.load(f)
        self.fromParamDict(pd)

    def fromParamDict(self, paramDict: Dict[str, Any],
                      deleteMissing: bool = True):
        """load parameters from a parameter dictionary (see :mod:`.serialize`).

        :param paramDict: parameter dictionary
        :param deleteMissing: if ``True``, delete parameters currently in the
            ParameterManager that are not listed in the file.
        """
        serialize.validateParamDict(paramDict)
        if serialize.isSimpleFormat(paramDict):
            simple = True
        else:
            simple = False

        currentParams = self.list()
        fileParams = ['.'.join(k.split('.')[1:]) for k in paramDict.keys()
                      if k.split('.')[0] == self.name]

        for pn in fileParams:
            if simple:
                val = paramDict[f"{self.name}.{pn}"]
                unit = ''
            else:
                val = paramDict[f"{self.name}.{pn}"]['value']
                unit = paramDict[f"{self.name}.{pn}"].get('unit', '')

            if self.has_param(pn):
                self.parameter(pn)(val)
                if unit is not None:
                    self.parameter(pn).unit = unit

            else:
                self.add_parameter(pn, initial_value=val, unit=unit)

        for pn in currentParams:
            if pn not in fileParams and deleteMissing:
                self.remove_parameter(pn)

    def toFile(self, filePath : str = None):

        """Save parameters from the instrument into a json file.

        :param filePath: path to the json file. 
                         If ``None`` it looks in the instrument current location
                         directory for a file called "parameter_manager_<parameter_manager_name>.json"
        """

        if filePath is None:
            filePath = self._paramValuesFile

        folder, file = os.path.split(filePath)
        params = serialize.toParamDict([self], simpleFormat=False, includeMeta=['unit'])
        if not os.path.exists(folder):
            os.makedirs(folder)
        with open(filePath, 'w') as f:
            json.dump(params, f, indent=2, sort_keys=True)


