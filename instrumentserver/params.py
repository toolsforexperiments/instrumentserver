import os
from pathlib import Path
from typing import Any, Dict, Union, List
from enum import Enum, unique, auto
import logging

import json
from qcodes import Instrument, Parameter
from qcodes.instrument.base import InstrumentBase
from qcodes.utils import validators

from . import serialize


logger = logging.getLogger(__name__)


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

    For the parameter manager to recognize other profiles in disk,
    the profile filename needs to start with 'parameter_manager-'
    and end with '.json' with the name of the profile in the middle.
    For example, 'parameter_manager-qubit1.json' represents the profile qubit1
    """

    # TODO: method to instantiate entirely from paramDict

    def __init__(self, name):
        super().__init__(name)

        self._workingDirectory = Path(os.getcwd())

        #: default location and name of the parameters save file.
        self.defaultProfile = f'parameter_manager-{self.name}.json'
        self.selectedProfile = self.defaultProfile
        self.profiles = []
        self.refresh_profiles()

        self.fromFile()

    @property
    def workingDirectory(self):
        return self._workingDirectory

    @workingDirectory.setter
    def workingDirectory(self, path: Union[str, Path]):
        self._workingDirectory = Path(path)
        self.refresh_profiles()

    def getWorkingDirectory(self):
        return self.workingDirectory

    @staticmethod
    def createFromParamDict(paramDict: Dict[str, Any], name: str) -> "ParameterManager":
        """Create a new ParameterManager instance from a paramDict.

        :param paramDict: The paramDict object.
        :param name: Name of the instrument in the paramDict (each entry in the
            paramDict starts with <instrumentName>.[...]).
        :returns: New ParameterManager instance.
        """
        raise NotImplementedError

    @staticmethod
    def cleanProfileName(name: str) -> str:
        """
        When passed the full file name of a parameter_manager profile, return only the middle
        string representing the profile's name.
        """
        return name.replace('parameter_manager-', '').replace('.json', '')

    @staticmethod
    def fullProfileName(name: str) -> str:
        """
        Adds 'parameter_manager-' to the beginning of `name` and adds '.json' at the end.
        """

        if not name.startswith('parameter_manager-'):
            name = 'parameter_manager-' + name
        if not name.endswith('.json'):
            name += '.json'
        return name

    @classmethod
    def _to_tree(cls, pm: 'ParameterManager') -> Dict:
        ret = {}
        for smn, sm in pm.submodules.items():
            ret[smn] = cls._to_tree(sm)
        for pn, p in pm.parameters.items():
            ret[pn] = p
        return ret

    @classmethod
    def does_profile_exist(cls, profiles, target):
        found = False
        for profile in profiles:
            if target in profile:
                found = True
                break
        return found

    def refresh_profiles(self) -> List[str]:
        """
        Goes into the working directory and updates the list of profiles.

        :return: List of profiles in the working directory
        """
        profiles = []
        for filename in os.listdir(self.workingDirectory):
            if filename.startswith("parameter_manager") and filename.endswith(".json"):
                profiles.append(filename)

        self.profiles = profiles
        return profiles

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

        :param name: Name of the parameter.
            If the name contains `.`s, then an element before a dot is interpreted
            as a submodule. Multiple dots represent nested submodules. I.e., when
            we supply ``foo.bar.foo2`` we have a top-level submodule ``foo``,
            containing a submodule ``bar``, containing the parameter ``foo2``.
            Submodules are generated on demand.
        :param kw: Any keyword arguments will be passed on to
            qcodes.Instrument.add_parameter, except:
            - ``set_cmd`` is always set to ``None``
            - ``parameter_class`` is ``qcodes.Parameter``
            - ``vals`` defaults to ``qcodes.utils.validators.Anything()``.
        :return: None.
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
        """Delete all empty submodules in the instrument."""

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

    def remove_all_parameters(self):
        """Remove all parameters from the instrument."""
        for param in self.list():
            self.remove_parameter(param, cleanup=False)
        self.remove_empty_submodules()

    def parameter(self, name: str) -> "Parameter":
        """Get a parameter object from the manager.

        :param name: the full name
        :returns: the parameter
        """
        return self._get_param(name)

    def list(self) -> List[str]:
        """Return a list of all parameters."""
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
        """Load parameters from a parameter json file
        (see :mod:`.serialize`).

        If the filepath starts with 'parameter_manager-' and ends with '.json',
        selectedProfile is changed to the filename.

        :param filePath: Path to the json file. If ``None`` it looks in the instrument current location
                         directory for a file called "parametermanager_parameters.json".
        :param deleteMissing: If ``True``, delete parameters currently in the
            ParameterManager that are not listed in the file.
        """
        if filePath is None:
            filePath = self.defaultProfile

        if os.path.exists(filePath):
            with open(filePath, 'r') as f:
                pd = json.load(f)
            self.fromParamDict(pd)

            filePath = Path(filePath)

            if filePath.name.startswith("parameter_manager-") and filePath.name.endswith(".json"):
                path = Path(filePath)
                self.selectedProfile = path.name
                if path.name not in self.profiles:
                    self.profiles.append(path.name)

        else:
            logger.warning("parameter file not found, cannot load.")

    def fromParamDict(self, paramDict: Dict[str, Any],
                      deleteMissing: bool = True):
        """Load parameters from a parameter dictionary (see :mod:`.serialize`).

        :param paramDict: Parameter dictionary.
        :param deleteMissing: If ``True``, delete parameters currently in the
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

    def toParamDict(self, simpleFormat: bool = False, includeMeta: List[str] = ['unit']):
        params = serialize.toParamDict([self], simpleFormat=simpleFormat,
                                       includeMeta=includeMeta)
        return params

    def toFile(self, filePath: str = None, name: str = None):

        """Save parameters from the instrument into a json file.
        If the file being saved is a profile file (starts with 'parameter_manager-' and ends with '.json'),
        the selectedProfile is changed to the filename.

        :param filePath: Path to the json file.
            If ``None`` it looks in the instrument current working
            directory for a file called "parameter_manager-<name_of_this_instrument>.json".
        :param name: If the filePath passed is a directory, The name of the file that it will
            create follows the convention of "parameter_manager-<name>.json". If none it will name it
            the name of the instrument.

        """

        if filePath is None:
            filePath = self.workingDirectory

        if os.path.isdir(filePath):
            if name is None:
                name = self.name
            filePath = os.path.join(filePath, f"parameter_manager-{name}.json")

        folder, file = os.path.split(filePath)
        params = self.toParamDict()
        if not os.path.exists(folder):
            os.makedirs(folder)
        with open(filePath, 'w') as f:
            json.dump(params, f, indent=2, sort_keys=True)

        file = str(file)
        if file.startswith("parameter_manager-") and file.endswith(".json"):
            self.selectedProfile = file

    def list_profiles(self) -> List[str]:
        """
        Returns a list of all profiles.
        """
        return self.profiles

    def switch_to_profile(self, profile: str):
        """
        Switches the server to the passed profile.
        """
        if not self.does_profile_exist(self.profiles, profile):
            raise ValueError(f"Profile {profile} does not exist")

        self.toFile(str(self.workingDirectory), self.cleanProfileName(str(self.selectedProfile)))
        self.remove_all_parameters()
        self.fromFile(str(self.workingDirectory.joinpath(self.fullProfileName(profile))))
        self.selectedProfile = self.fullProfileName(profile)
