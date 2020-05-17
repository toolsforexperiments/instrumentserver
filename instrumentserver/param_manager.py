from typing import Any

from qcodes import Instrument, Parameter
from qcodes.utils.validators import Anything


class ParameterManager(Instrument):
    """
    A virtual instrument that acts as a manager for a collection of
    arbitrary parameters and groups of parameters.

    Allows extra-easy on-the-fly addition/removal of new parameters.
    """

    def __init__(self, name):
        super().__init__(name)
        self.parameters.pop('IDN')

    def _get_param(self, param_name: str) -> Parameter:
        parent = self._get_parent(param_name)
        return parent.parameters[param_name.split('.')[-1]]

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
                    parent.add_submodule(n, ParameterManager(full_name))
                else:
                    raise ValueError(f'{n} does not exist.')
            parent = parent.submodules[n]
        return parent

    def add(self, param_name: str, value: Any, **kw: Any) -> None:
        """Add a parameter.

        :param param_name: name of the parameter.
            if the name contains `.`s, then an element before a dot is interpreted
            as a submodule. multiple dots represent nested submodules. I.e., when
            we supply ``foo.bar.foo2`` we have a top-level submodule ``foo``,
            containing a submodule ``bar``, containing the parameter ``foo2``.
            Submodules are generated on demand.
        :param value: the initial value of the parameter
        :param kw: Any keyword arguments will be passed on to
            qcodes.Instrument.add_parameter, except:
            - ``set_cmd`` is always set to ``None``
            - ``parameter_class`` is ``qcodes.Parameter``
            - ``vals`` defaults to ``qcodes.utils.validators.Anything()``.
        :return: None
        """
        kw['parameter_class'] = Parameter
        if 'vals' not in kw:
            kw['vals'] = Anything()
        kw['set_cmd'] = None
        kw['initial_value'] = value

        parent = self._get_parent(param_name, create_parent=True)
        parent.add_parameter(param_name.split('.')[-1], **kw)

    def remove(self, param_name: str, cleanup: bool = True):
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
                parent.submodules[n].close()
                del parent.submodules[n]

        purge(self)
