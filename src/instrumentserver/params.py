import json
import logging
import os
from collections.abc import Sequence
from enum import Enum, auto, unique
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Tuple, Union

from qcodes import Parameter, validators
from qcodes.instrument import InstrumentBase
from qcodes.parameters import ParameterBase

from . import serialize
from .base import Broadcaster
from .blueprints import PMLockBluePrint

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
    ParameterTypes.any: {"name": "Any", "validatorType": validators.Anything},
    ParameterTypes.numeric: {"name": "Numeric", "validatorType": validators.Numbers},
    ParameterTypes.integer: {"name": "Integer", "validatorType": validators.Ints},
    ParameterTypes.string: {"name": "String", "validatorType": validators.Strings},
    ParameterTypes.bool: {"name": "Boolean", "validatorType": validators.Bool},
    ParameterTypes.complex: {
        "name": "Complex",
        "validatorType": validators.ComplexNumbers,
    },
}


def paramTypeFromVals(vals: validators.Validator | None) -> Union[ParameterTypes, None]:
    if vals is None:
        vals = validators.Anything()

    for k, v in parameterTypes.items():
        validator_type = v["validatorType"]
        if isinstance(validator_type, type) and isinstance(vals, validator_type):
            return k

    return None


def paramTypeFromName(name: str) -> Union[ParameterTypes, None]:
    for k, v in parameterTypes.items():
        if name == v["name"]:
            return k
    return None


class ManagedParameter(Parameter):
    """
    A parameter that can carry a Lock naming another parameter as its Target.

    While the Lock is locked, the parameter answers ``get`` with the Target's
    value and refuses ``set`` with a ``ValueError`` naming the Target: values
    are pulled on get, nothing is ever pushed into a Follower (ADR-0002).
    Locking never touches the own cached value, so unlocking exposes the own
    value again. With no Lock, or with a Lock that is present but unlocked,
    the parameter behaves like a plain ``Parameter``; an unlocked Lock only
    remembers its Target.
    """

    def __init__(self, name: str, path: str | None = None, **kwargs: Any) -> None:
        # The Lock state must exist before ``super().__init__``: creating the
        # parameter with an ``initial_value`` already runs ``set_raw``.
        self.lock: PMLockBluePrint | None = None
        self._target: ParameterBase | None = None
        self._path: str | None = path
        super().__init__(name, **kwargs)

    @property
    def path(self) -> str:
        """The parameter's full dotted path with the instrument name, the
        form Locks and files use (``parameter_manager.q01.x``); for a
        standalone parameter, its plain name."""
        return self._path if self._path is not None else self.name

    @property
    def locked(self) -> bool:
        """Whether a Lock is present and currently locked."""
        return self.lock is not None and self.lock.locked

    def _locked_target(self) -> ParameterBase:
        """The Target parameter object of a locked Lock."""
        assert self._target is not None, "a locked Lock has no Target"
        return self._target

    def own_value(self) -> Any:
        """Return the own cached value, whatever state the Lock is in."""
        return self.cache.get(get_if_invalid=False)

    def get_raw(self) -> Any:
        """Answer with the Target's value while locked, the own cached value
        otherwise."""
        if self.locked:
            return self._locked_target().get()
        return self.cache.raw_value

    def set_raw(self, value: Any) -> None:
        """Store the value while not locked; while locked, refuse with a
        ``ValueError`` naming the full dotted paths of Follower and Target."""
        if self.locked:
            assert self.lock is not None, "a locked Lock has no record"
            raise ValueError(f"{self.path} is locked to {self.lock.target}")
        self.cache._set_from_raw_value(value)

    def _wrap_get(self, get_function: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap ``get_raw`` so that a locked get answers with the Target's
        value without recording it in the own cache.

        qcodes' get wrapper writes every answered value into the parameter's
        cache; for a Follower that would destroy the own value that unlocking
        must expose again (ADR-0002).
        """
        plain_get = super()._wrap_get(get_function)

        @wraps(get_function)
        def get_wrapper(*args: Any, **kwargs: Any) -> Any:
            if self.locked:
                return self._locked_target().get()
            return plain_get(*args, **kwargs)

        return get_wrapper

    def snapshot_base(
        self,
        update: bool | None = True,
        params_to_skip_update: Sequence[str] | None = None,
    ) -> Dict[str, Any]:
        """Snapshot with a ``lock`` entry while a Lock is present; while
        locked, the reported ``value`` is the Target's value.

        With ``update=True`` the base snapshot already asks this parameter,
        whose locked get answers with the Target's value, so the Target is
        not read a second time. With a falsy ``update`` the Target is read
        directly — not its cache — so that each hop of a chain reads
        according to its own state (D7).
        """
        snap = super().snapshot_base(
            update=update, params_to_skip_update=params_to_skip_update
        )
        if self.lock is not None:
            if self.locked and update is not True:
                snap["value"] = self._locked_target().get()
            snap["lock"] = {"target": self.lock.target, "locked": self.lock.locked}
        return snap


class ParameterGroup(InstrumentBase):
    """
    A Parameter Group: a plain container of parameters and nested Parameter
    Groups inside a Parameter Manager.

    It holds parameters and nested Parameter Groups and offers the tree
    helpers (dotted-path add/remove/get/set, listing, tree building), but
    has no file, profile, Type or Lock logic of its own. Every submodule
    of a Parameter Manager is a Parameter Group; only the root is the
    Parameter Manager, which extends the Parameter Group with those
    responsibilities.
    """

    @classmethod
    def _to_tree(cls, pm: "ParameterGroup") -> Dict:
        ret: dict[str, Any] = {}
        for smn, sm in pm.submodules.items():
            assert isinstance(sm, ParameterGroup)
            ret[smn] = cls._to_tree(sm)
        for pn, p in pm.parameters.items():
            ret[pn] = p
        return ret

    def to_tree(self) -> Dict:
        return ParameterGroup._to_tree(self)

    def _iter_params(self) -> Iterator[Tuple[str, ParameterBase]]:
        """Yield ``(relative dotted path, parameter)`` for every parameter
        in this Parameter Group and its nested Parameter Groups, in tree
        order. The paths are relative to this group."""
        for pname, param in self.parameters.items():
            yield pname, param
        for smn, sm in self.submodules.items():
            assert isinstance(sm, ParameterGroup)
            for path, param in sm._iter_params():
                yield f"{smn}.{path}", param

    def _get_param(self, param_name: str) -> ParameterBase:
        parent = self._get_parent(param_name)
        try:
            param = parent.parameters[param_name.split(".")[-1]]
            return param
        except KeyError:
            raise ValueError(f"Parameter '{param_name}' does not exist")

    def _get_parent(
        self, param_name: str, create_parent: bool = False
    ) -> "ParameterGroup":

        split_names = param_name.split(".")
        parent = self
        full_name = self.name

        for i, n in enumerate(split_names[:-1]):
            full_name += f".{n}"
            if n in parent.parameters:
                raise ValueError(
                    f"{n} is a parameter, and cannot have child parameters."
                )
            if n not in parent.submodules:
                if create_parent:
                    parent.add_submodule(n, ParameterGroup(n))  # type: ignore[type-var]
                else:
                    raise ValueError(f"{n} does not exist.")
            parent = parent.submodules[n]  # type: ignore[assignment]
        return parent

    def has_param(self, param_name: str) -> bool:
        try:
            self._get_param(param_name)
            return True
        except ValueError:
            return False

    def add_parameter(self, name: str, **kw: Any) -> None:  # type: ignore[override]
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
            - ``parameter_class`` defaults to ``qcodes.Parameter``
            - ``vals`` defaults to ``qcodes.utils.validators.Anything()``.
        :return: None.
        """
        kw.setdefault("parameter_class", Parameter)
        if "vals" not in kw:
            kw["vals"] = validators.Anything()
        kw["set_cmd"] = None

        parent = self._get_parent(name, create_parent=True)
        if parent is self:
            super().add_parameter(name.split(".")[-1], **kw)
        else:
            parent.add_parameter(name.split(".")[-1], **kw)

    def remove_parameter(self, param_name: str, cleanup: bool = True) -> None:
        parent = self._get_parent(param_name)
        pname = param_name.split(".")[-1]
        del parent.parameters[pname]
        if cleanup:
            self.remove_empty_submodules()

    def get(self, param_name: str) -> Any:
        param = self._get_param(param_name)
        return param.get()

    def set(self, param_name: str, value: Any) -> Any:
        param = self._get_param(param_name)
        param.set(value)

    def remove_empty_submodules(self) -> None:
        """Delete all empty submodules in the instrument."""

        def is_empty(parent: InstrumentBase) -> bool:
            if len(parent.submodules) == 0 and len(parent.parameters) == 0:
                return True
            else:
                return False

        def purge(parent: InstrumentBase) -> None:
            mark_for_deletion = []
            for n, s in parent.submodules.items():
                purge(s)  # type: ignore[arg-type]
                if is_empty(s):  # type: ignore[arg-type]
                    mark_for_deletion.append(n)
            for n in mark_for_deletion:
                del parent.submodules[n]

        purge(self)

    def parameter(self, name: str) -> ParameterBase:
        """Get a parameter object from the manager.

        :param name: the full name
        :returns: the parameter
        """
        return self._get_param(name)

    def list(self) -> List[str]:
        """Return a list of all parameters."""
        tree = self.to_tree()

        def tolist(x: Dict[str, Any]) -> List[str]:
            ret_ = []
            for k, v in x.items():
                if isinstance(v, Parameter):
                    ret_.append(f"{k}")
                else:
                    ret_ += [f"{k}.{e}" for e in tolist(v)]
            return ret_

        return tolist(tree)


class ParameterManager(Broadcaster, ParameterGroup):
    """
    A virtual instrument that acts as a manager for a collection of
    arbitrary parameters and groups of parameters.

    Allows extra-easy on-the-fly addition/removal of new parameters.

    The Parameter Manager is the root of the parameter tree. It extends the
    Parameter Group with file, profile, Lock, and (later) Type logic;
    its submodules are plain Parameter Groups.

    It implements the Broadcaster contract, so the Server can register
    itself as a broadcast sink when the Parameter Manager joins the
    Station. Nothing is broadcast yet; the Lock and Type features will
    emit through it.

    For the parameter manager to recognize other profiles in disk,
    the profile filename needs to start with 'parameter_manager-'
    and end with '.json' with the name of the profile in the middle.
    For example, 'parameter_manager-qubit1.json' represents the profile qubit1
    """

    # TODO: method to instantiate entirely from paramDict

    def __init__(self, name: str) -> None:
        super().__init__(name)

        self._workingDirectory = Path(os.getcwd())

        #: default location and name of the parameters save file.
        self.selectedProfile = self.fullProfileName(self.name)
        self.profiles: List[str] = []
        self.refresh_profiles()

        self.fromFile()

    @property
    def workingDirectory(self) -> Path:
        return self._workingDirectory

    @workingDirectory.setter
    def workingDirectory(self, path: Union[str, Path]) -> None:
        self._workingDirectory = Path(path)
        self.refresh_profiles()

    def getWorkingDirectory(self):  # type: ignore[no-untyped-def]
        return self.workingDirectory

    def add_parameter(self, name: str, **kw: Any) -> None:  # type: ignore[override]
        """Add a parameter, created as a :class:`ManagedParameter`.

        Same dotted-name semantics as :meth:`ParameterGroup.add_parameter`,
        which this method calls; only the parameter class differs, so that
        the Parameter Manager's parameters can carry a Lock. The created
        parameter's ``path`` is set to its full dotted path with the
        instrument name (``parameter_manager.q01.x``), the form Locks and
        files use.

        :param name: Name of the parameter; see
            :meth:`ParameterGroup.add_parameter`.
        :param kw: Any keyword arguments will be passed on to
            qcodes.Instrument.add_parameter, as in
            :meth:`ParameterGroup.add_parameter`.
        :return: None.
        """
        kw["parameter_class"] = ManagedParameter
        kw["path"] = f"{self.name}.{name}"
        super().add_parameter(name, **kw)

    def remove_parameter(self, param_name: str, cleanup: bool = True) -> None:
        """Remove a parameter, first removing every Lock whose Target it is
        (ADR-0002): the Followers become plain parameters and answer ``get``
        with their own values again.

        Same signature and deletion behaviour as
        :meth:`ParameterGroup.remove_parameter`; the path is relative to
        this Parameter Manager.
        """
        # validate-then-mutate: the parameter must exist before any Lock is
        # touched. The checks mirror what the deletion itself would raise.
        parent = self._get_parent(param_name)
        pname = param_name.split(".")[-1]
        if pname not in parent.parameters:
            raise KeyError(pname)

        # every Lock pointing at the removed parameter goes away with it,
        # locked or not: an unlocked Lock must not keep remembering a
        # Target that no longer exists.
        target_full = self._full_path(param_name)
        for rel_path, param in self._iter_params():
            lock = getattr(param, "lock", None)
            if lock is not None and lock.target == target_full:
                assert isinstance(param, ManagedParameter)
                param.lock = None
                param._target = None

        super().remove_parameter(param_name, cleanup)

    # ------------------------------------------------------------------
    # Lock API (plan decision D9)
    #
    # A Lock lives on the Follower's :class:`ManagedParameter`: its
    # :class:`PMLockBluePrint` records the Target as a full dotted path
    # with the instrument name and whether the Lock is currently locked.
    # Every method validates first and raises before touching anything
    # (no partial state on error). Paths passed in by name and returned
    # by name are dotted paths relative to this Parameter Manager; only
    # ``PMLockBluePrint.target`` and the stored Lock Target use the full
    # form, as :attr:`ManagedParameter.path` does.

    def _full_path(self, relative_name: str) -> str:
        """The full dotted path (with the instrument name) of a path
        relative to this Parameter Manager."""
        return f"{self.name}.{relative_name}"

    def _resolve_param(self, name: str) -> ParameterBase:
        """The parameter object at a dotted path relative to this
        Parameter Manager; raises ``ValueError`` naming the path when no
        parameter exists there."""
        try:
            parent = self._get_parent(name)
        except ValueError:
            raise ValueError(f"Parameter '{name}' does not exist") from None
        pname = name.split(".")[-1]
        if pname not in parent.parameters:
            raise ValueError(f"Parameter '{name}' does not exist")
        return parent.parameters[pname]

    def _param_by_full_path(self, full_path: str) -> ParameterBase | None:
        """The parameter object at a full dotted path (the form a Lock's
        Target is stored in), or ``None`` when the path points outside
        this Parameter Manager or no parameter exists there."""
        prefix = f"{self.name}."
        if not full_path.startswith(prefix):
            return None
        try:
            return self._get_param(full_path[len(prefix):])
        except ValueError:
            return None

    def _require_lock(self, param: ParameterBase, name: str) -> PMLockBluePrint:
        """The Lock record of a Follower; raises ``ValueError`` naming the
        path when the parameter carries no Lock."""
        lock = getattr(param, "lock", None)
        if lock is None:
            raise ValueError(f"{self._full_path(name)} has no Lock")
        return lock

    def _check_lock_allowed(self, follower_full: str, target_full: str) -> None:
        """Raise ``ValueError`` for a self-lock, or when locking would
        close a cycle: the walk follows each Target's Lock regardless of
        locked/unlocked state (D7)."""
        if follower_full == target_full:
            raise ValueError(f"cannot lock {follower_full} to itself")
        chain = [target_full]
        seen = {target_full}
        current = target_full
        while True:
            param = self._param_by_full_path(current)
            if param is None:
                break
            lock = getattr(param, "lock", None)
            if lock is None:
                break
            nxt = lock.target
            if nxt == follower_full or nxt in seen:
                raise ValueError(
                    f"cannot lock {follower_full} to {target_full}: cycle in "
                    f"Lock targets: {' -> '.join(chain + [nxt])}"
                )
            seen.add(nxt)
            chain.append(nxt)
            current = nxt

    def lock(self, name: str, target: str) -> None:
        """Lock the parameter at ``name`` to the parameter at ``target``
        (dotted paths relative to this Parameter Manager).

        Creates the Lock, or re-targets it when one exists already, and
        locks it: while locked, ``name`` answers ``get`` with the Target's
        value and refuses ``set`` (ADR-0002). The Target must be a
        parameter of this same Parameter Manager (D8). Raises
        ``ValueError`` naming the paths when a path does not exist, the
        Follower cannot carry a Lock, the Lock would be a self-lock, or it
        would close a cycle (walking Targets regardless of locked/unlocked
        state, D7).

        :param name: path of the Follower.
        :param target: path of the Target.
        """
        follower = self._resolve_param(name)
        target_param = self._resolve_param(target)
        follower_full = self._full_path(name)
        target_full = self._full_path(target)
        if not isinstance(follower, ManagedParameter):
            raise ValueError(f"{follower_full} cannot carry a Lock")
        self._check_lock_allowed(follower_full, target_full)
        follower._target = target_param
        follower.lock = PMLockBluePrint(target=target_full, locked=True)

    def unlock(self, name: str) -> None:
        """Unlock the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager): it keeps remembering its
        Target but answers ``get`` with its own value again (D5). Raises
        ``ValueError`` naming the path when the parameter does not exist
        or carries no Lock; unlocking an already unlocked Lock does
        nothing and logs at INFO level."""
        param = self._resolve_param(name)
        lock = self._require_lock(param, name)
        if not lock.locked:
            logger.info(
                f"{self._full_path(name)} is already unlocked; nothing to do"
            )
            return
        lock.locked = False

    def relock(self, name: str) -> None:
        """Lock the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager) to its remembered Target again
        (D5). Raises ``ValueError`` naming the paths when the parameter
        does not exist, carries no Lock, or when the remembered Target is
        gone or locking to it would close a cycle (D7); relocking an
        already locked Lock does nothing and logs at INFO level."""
        param = self._resolve_param(name)
        lock = self._require_lock(param, name)
        follower_full = self._full_path(name)
        if lock.locked:
            logger.info(f"{follower_full} is already locked; nothing to do")
            return
        target_param = self._param_by_full_path(lock.target)
        if target_param is None:
            raise ValueError(
                f"{follower_full} remembers Target {lock.target}, "
                "which does not exist"
            )
        self._check_lock_allowed(follower_full, lock.target)
        assert isinstance(param, ManagedParameter)
        param._target = target_param
        lock.locked = True

    def toggle_lock(self, name: str) -> None:
        """Toggle the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager): locked becomes unlocked and
        unlocked becomes locked again (D5). Raises ``ValueError`` naming
        the path when the parameter does not exist or carries no Lock, and
        like :meth:`relock` when locking back would close a cycle."""
        param = self._resolve_param(name)
        lock = self._require_lock(param, name)
        if lock.locked:
            self.unlock(name)
        else:
            self.relock(name)

    def remove_lock(self, name: str) -> None:
        """Remove the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager) entirely: the Target is
        forgotten and the parameter behaves as a plain parameter again
        (D5). Raises ``ValueError`` naming the path when the parameter
        does not exist or carries no Lock."""
        param = self._resolve_param(name)
        self._require_lock(param, name)
        assert isinstance(param, ManagedParameter)
        param.lock = None
        param._target = None

    def get_lock(self, name: str) -> "PMLockBluePrint | None":
        """The Lock of the parameter at ``name`` (dotted path relative to
        this Parameter Manager) as a :class:`PMLockBluePrint` whose Target
        is the full dotted path, or ``None`` when it carries no Lock.
        Raises ``ValueError`` naming the path when the parameter does not
        exist."""
        param = self._resolve_param(name)
        lock = getattr(param, "lock", None)
        if lock is None:
            return None
        return PMLockBluePrint(target=lock.target, locked=lock.locked)

    def list_locks(self) -> "Dict[str, PMLockBluePrint]":
        """All Locks in this Parameter Manager, locked and unlocked alike
        (D5), as a mapping from the Follower's path (relative to this
        Parameter Manager) to its :class:`PMLockBluePrint`."""
        locks: Dict[str, PMLockBluePrint] = {}
        for rel_path, param in self._iter_params():
            lock = getattr(param, "lock", None)
            if lock is not None:
                locks[rel_path] = PMLockBluePrint(
                    target=lock.target, locked=lock.locked
                )
        return locks

    def followers_of(self, name: str) -> "List[str]":
        """Paths (relative to this Parameter Manager) of every Follower
        whose Lock points at the parameter at ``name``, locked and
        unlocked alike. Raises ``ValueError`` naming the path when the
        parameter does not exist."""
        self._resolve_param(name)
        target_full = self._full_path(name)
        followers: List[str] = []
        for rel_path, param in self._iter_params():
            lock = getattr(param, "lock", None)
            if lock is not None and lock.target == target_full:
                followers.append(rel_path)
        return followers

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
        return name.replace("parameter_manager-", "").replace(".json", "")

    @staticmethod
    def fullProfileName(name: str) -> str:
        """
        Adds 'parameter_manager-' to the beginning of `name` and adds '.json' at the end.
        """

        if not name.startswith("parameter_manager-"):
            name = "parameter_manager-" + name
        if not name.endswith(".json"):
            name += ".json"
        return name

    @classmethod
    def does_profile_exist(cls, profiles: List[str], target: str) -> bool:
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

    def remove_all_parameters(self) -> None:
        """Remove all parameters from the instrument."""
        for param in self.list():
            self.remove_parameter(param, cleanup=False)
        self.remove_empty_submodules()

    def fromFile(
        self,
        filePath: str | None = None,
        deleteMissing: bool = True,
    ) -> None:
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
            filePath = str(
                self.workingDirectory.joinpath(
                    self.fullProfileName(self.selectedProfile)
                )
            )

        if os.path.exists(filePath):
            with open(filePath, "r") as f:
                pd = json.load(f)
            self.fromParamDict(pd)

            path = Path(filePath)

            if path.name.startswith("parameter_manager-") and path.name.endswith(
                ".json"
            ):
                profileName = path.name
                self.selectedProfile = profileName
                if path.name not in self.profiles:
                    self.profiles.append(profileName)

        else:
            logger.warning("parameter file not found, cannot load.")

    def fromParamDict(
        self, paramDict: Dict[str, Any], deleteMissing: bool = True
    ) -> None:
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
        fileParams = [
            ".".join(k.split(".")[1:])
            for k in paramDict.keys()
            if k.split(".")[0] == self.name
        ]

        for pn in fileParams:
            if simple:
                val = paramDict[f"{self.name}.{pn}"]
                unit = ""
            else:
                val = paramDict[f"{self.name}.{pn}"]["value"]
                unit = paramDict[f"{self.name}.{pn}"].get("unit", "")

            if self.has_param(pn):
                self.parameter(pn)(val)
                if unit is not None:
                    param = self.parameter(pn)
                    assert hasattr(param, "unit")
                    param.unit = unit

            else:
                self.add_parameter(pn, initial_value=val, unit=unit)

        for pn in currentParams:
            if pn not in fileParams and deleteMissing:
                self.remove_parameter(pn)

    def toParamDict(
        self, simpleFormat: bool = False, includeMeta: List[str] = ["unit"]
    ) -> Dict[str, Any]:
        params = serialize.toParamDict(
            [self], simpleFormat=simpleFormat, includeMeta=includeMeta
        )
        return params

    def toFile(
        self,
        filePath: str | None = None,
        name: str | None = None,
    ) -> None:
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
            filePath = str(self.workingDirectory)

        if os.path.isdir(filePath):
            if name is None:
                name = self.selectedProfile
            filePath = os.path.join(filePath, self.fullProfileName(name))

        folder, file = os.path.split(filePath)
        params = self.toParamDict()
        if not os.path.exists(folder):
            os.makedirs(folder)
        with open(filePath, "w") as f:
            json.dump(params, f, indent=2, sort_keys=True)

        file = str(file)
        if file.startswith("parameter_manager-") and file.endswith(".json"):
            self.selectedProfile = file

    def list_profiles(self) -> List[str]:
        """
        Returns a list of all profiles.
        """
        return self.profiles

    def switch_to_profile(self, profile: str) -> None:
        """
        Switches the server to the passed profile.
        """
        if not self.does_profile_exist(self.profiles, profile):
            raise ValueError(f"Profile {profile} does not exist")

        self.toFile(str(self.workingDirectory), self.selectedProfile)
        self.remove_all_parameters()
        self.fromFile(
            str(self.workingDirectory.joinpath(self.fullProfileName(profile)))
        )
        self.selectedProfile = self.fullProfileName(profile)
