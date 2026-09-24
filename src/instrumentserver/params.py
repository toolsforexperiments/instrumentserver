import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto, unique
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Tuple, Union

from qcodes import Parameter, validators
from qcodes.instrument import InstrumentBase
from qcodes.parameters import ParameterBase

from . import serialize
from .base import Broadcaster
from .blueprints import (
    PM_LOCK_UPDATE,
    ParameterBroadcastBluePrint,
    PMLockBluePrint,
    PMTypeBluePrint,
)

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
    responsibilities. When a Parameter Group belongs to a Parameter
    Manager, its public ``add_parameter``/``remove_parameter`` route to
    the root, so ``ManagedParameter`` creation and the Lock cleanup always
    happen; a standalone Parameter Group behaves as a plain container.
    """

    #: The root Parameter Manager this Parameter Group belongs to, or
    #: ``None`` for a standalone Parameter Group or the root itself. When
    #: set, the public add/remove methods route to the root (D15): only
    #: the root owns ``ManagedParameter`` creation and Lock logic.
    _root: "ParameterManager | None" = None

    #: This Parameter Group's dotted path relative to its root Parameter
    #: Manager, with a trailing dot (``"q01.ro."``); empty on the root and
    #: on standalone Parameter Groups. Set together with ``_root`` at
    #: creation and used to build root-relative paths when routing.
    _path_prefix: str = ""

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
        prefix = self._path_prefix

        for i, n in enumerate(split_names[:-1]):
            full_name += f".{n}"
            prefix += f"{n}."
            if n in parent.parameters:
                raise ValueError(
                    f"{n} is a parameter, and cannot have child parameters."
                )
            if n not in parent.submodules:
                if create_parent:
                    new_group = ParameterGroup(n)
                    new_group._root = self._root_for_new_groups()
                    new_group._path_prefix = prefix
                    parent.add_submodule(n, new_group)  # type: ignore[type-var]
                else:
                    raise ValueError(f"{n} does not exist.")
            parent = parent.submodules[n]  # type: ignore[assignment]
        return parent

    def _root_for_new_groups(self) -> "ParameterManager | None":
        """The root Parameter Manager that nested Parameter Groups created
        under this group belong to: this group's root, or ``None`` when
        this group is standalone."""
        return self._root

    def has_param(self, param_name: str) -> bool:
        try:
            self._get_param(param_name)
            return True
        except ValueError:
            return False

    def add_parameter(self, name: str, **kw: Any) -> None:  # type: ignore[override]
        """Add a parameter.

        A Parameter Group that belongs to a Parameter Manager routes the
        call to the root, with the path made relative to it
        (``<group path>.<name>``), so the parameter is created as a
        :class:`ManagedParameter` that can carry a Lock (D15). A
        standalone Parameter Group creates a plain qcodes ``Parameter``.

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
        if self._root is not None:
            self._root.add_parameter(f"{self._path_prefix}{name}", **kw)
            return
        kw.setdefault("parameter_class", Parameter)
        if "vals" not in kw:
            kw["vals"] = validators.Anything()
        kw["set_cmd"] = None

        parent = self._get_parent(name, create_parent=True)
        parent._add_own_parameter(name.split(".")[-1], **kw)

    def _add_own_parameter(self, name: str, **kw: Any) -> None:
        """Create a parameter directly on this Parameter Group, without
        routing: the plain creation path the root's methods end in."""
        super().add_parameter(name, **kw)

    def remove_parameter(self, param_name: str, cleanup: bool = True) -> None:
        """Remove a parameter.

        A Parameter Group that belongs to a Parameter Manager routes the
        call to the root, with the path made relative to it, so the
        root's Lock cleanup happens before the deletion (D3, D15). A
        standalone Parameter Group deletes directly.

        :param param_name: Name of the parameter; dotted names traverse
            nested Parameter Groups.
        :param cleanup: Whether to remove emptied submodules afterwards.
        """
        if self._root is not None:
            self._root.remove_parameter(
                f"{self._path_prefix}{param_name}", cleanup=cleanup
            )
            return
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


@dataclass
class _TypeEntry:
    """One entry of a Type: a relative parameter path with its default
    value and unit, plus the Target of the entry's Type Lock (``None``
    until a Type Lock is declared on it)."""

    default: Any = None
    unit: str = ""
    target: str | None = None


@dataclass
class _TypeDefinition:
    """The Type registry's record of a Type: its name, its entries by
    relative parameter path, and its Nested Types as a mapping from the
    submodule name that requires them to the nested Type's name."""

    name: str
    parameters: Dict[str, _TypeEntry] = field(default_factory=dict)
    nested: Dict[str, str] = field(default_factory=dict)


class ParameterManager(Broadcaster, ParameterGroup):
    """
    A virtual instrument that acts as a manager for a collection of
    arbitrary parameters and groups of parameters.

    Allows extra-easy on-the-fly addition/removal of new parameters.

    The Parameter Manager is the root of the parameter tree. It extends the
    Parameter Group with file, profile, Lock, and Type logic;
    its submodules are plain Parameter Groups.

    It implements the Broadcaster contract, so the Server can register
    itself as a broadcast sink when the Parameter Manager joins the
    Station. Every Lock method that changes a Lock emits one
    ``pm-lock-update`` Broadcast per affected Follower (D10), and
    ``remove_parameter`` emits them for the Locks that deleting a Target
    drops; Type editing will emit through it too.

    For the parameter manager to recognize other profiles in disk,
    the profile filename needs to start with 'parameter_manager-'
    and end with '.json' with the name of the profile in the middle.
    For example, 'parameter_manager-qubit1.json' represents the profile qubit1
    """

    # TODO: method to instantiate entirely from paramDict

    def __init__(self, name: str) -> None:
        super().__init__(name)

        # The Type registry: maps each Type name to its ``_TypeDefinition``.
        # It lives on the root Parameter Manager only (D15); Parameter
        # Groups hold no Types.
        self._types: Dict[str, _TypeDefinition] = {}

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

    def _root_for_new_groups(self) -> "ParameterManager":
        """Parameter Groups created under the Parameter Manager belong to
        it: it is their root."""
        return self

    def remove_parameter(self, param_name: str, cleanup: bool = True) -> None:
        """Remove a parameter, first removing every Lock whose Target it is
        (ADR-0002): the Followers become plain parameters and answer ``get``
        with their own values again. One ``pm-lock-update`` Broadcast with a
        ``None`` value is emitted per dropped Lock (D10).

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
        dropped_followers: List[str] = []
        for rel_path, param in self._iter_params():
            lock = getattr(param, "lock", None)
            if lock is not None and lock.target == target_full:
                assert isinstance(param, ManagedParameter)
                param.lock = None
                param._target = None
                dropped_followers.append(rel_path)
        for rel_path in dropped_followers:
            self._broadcast_lock_update(rel_path, None)

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
    #
    # Every method that changes a Lock emits one ``pm-lock-update``
    # Broadcast per affected Follower (D10), through :meth:`broadcast` of
    # the Broadcaster contract. Broadcasts that only report state are
    # emitted after the change; failed validations and the logged no-op
    # paths (unlock on an unlocked, relock on a locked Lock) emit nothing.

    def _broadcast_lock_update(
        self, follower_path: str, lock: "PMLockBluePrint | None"
    ) -> None:
        """Emit one ``pm-lock-update`` Broadcast about the Follower at
        ``follower_path`` (relative to this Parameter Manager): the payload
        is its :class:`PMLockBluePrint`, or ``None`` when its Lock was
        removed (D10). With no sink registered, :meth:`broadcast` is a
        no-op, so standalone use of the Parameter Manager emits nothing."""
        self.broadcast(
            ParameterBroadcastBluePrint(
                name=self._full_path(follower_path),
                action=PM_LOCK_UPDATE,
                value=lock,
            )
        )

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
        ``ValueError`` naming every offending path when a path does not
        exist (both paths are checked before one error is raised), the
        Follower cannot carry a Lock, the Lock would be a self-lock, or it
        would close a cycle (walking Targets regardless of locked/unlocked
        state, D7). On success emits one ``pm-lock-update`` Broadcast
        naming the Follower with its new Lock (D10); a failed validation
        emits nothing.

        :param name: path of the Follower.
        :param target: path of the Target.
        """
        # validate-then-mutate: resolve both paths up front and name every
        # missing one in a single error (rule 3)
        resolved: List[ParameterBase] = []
        missing: List[str] = []
        for path in (name, target):
            try:
                resolved.append(self._resolve_param(path))
            except ValueError as exc:
                missing.append(str(exc))
        if missing:
            raise ValueError("; ".join(missing))
        follower, target_param = resolved
        follower_full = self._full_path(name)
        target_full = self._full_path(target)
        if not isinstance(follower, ManagedParameter):
            raise ValueError(f"{follower_full} cannot carry a Lock")
        self._check_lock_allowed(follower_full, target_full)
        follower._target = target_param
        follower.lock = PMLockBluePrint(target=target_full, locked=True)
        # a snapshot, not the stored record: sinks must not see the payload
        # change when the Lock is toggled or re-targeted later
        self._broadcast_lock_update(
            name, PMLockBluePrint(target=target_full, locked=True)
        )

    def unlock(self, name: str) -> None:
        """Unlock the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager): it keeps remembering its
        Target but answers ``get`` with its own value again (D5). Raises
        ``ValueError`` naming the path when the parameter does not exist
        or carries no Lock; unlocking an already unlocked Lock does
        nothing and logs at INFO level. On a state change emits one
        ``pm-lock-update`` Broadcast carrying the unlocked Lock (D10);
        the no-op path emits nothing."""
        param = self._resolve_param(name)
        lock = self._require_lock(param, name)
        if not lock.locked:
            logger.info(
                f"{self._full_path(name)} is already unlocked; nothing to do"
            )
            return
        lock.locked = False
        # a snapshot, not the live record: sinks must not see the payload
        # change when the Lock is toggled again
        self._broadcast_lock_update(
            name, PMLockBluePrint(target=lock.target, locked=lock.locked)
        )

    def relock(self, name: str) -> None:
        """Lock the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager) to its remembered Target again
        (D5). Raises ``ValueError`` naming the paths when the parameter
        does not exist, carries no Lock, or when the remembered Target is
        gone or locking to it would close a cycle (D7); relocking an
        already locked Lock does nothing and logs at INFO level. On a
        state change emits one ``pm-lock-update`` Broadcast carrying the
        locked Lock (D10); the no-op path emits nothing."""
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
        # a snapshot, not the live record: sinks must not see the payload
        # change when the Lock is toggled again
        self._broadcast_lock_update(
            name, PMLockBluePrint(target=lock.target, locked=lock.locked)
        )

    def toggle_lock(self, name: str) -> None:
        """Toggle the Lock of the parameter at ``name`` (dotted path
        relative to this Parameter Manager): locked becomes unlocked and
        unlocked becomes locked again (D5). Raises ``ValueError`` naming
        the path when the parameter does not exist or carries no Lock, and
        like :meth:`relock` when locking back would close a cycle. Emits
        one ``pm-lock-update`` Broadcast through :meth:`unlock` /
        :meth:`relock`, which carry out the change (D10)."""
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
        does not exist or carries no Lock. Emits one ``pm-lock-update``
        Broadcast with a ``None`` value for the Follower whose Lock was
        removed (D10)."""
        param = self._resolve_param(name)
        self._require_lock(param, name)
        assert isinstance(param, ManagedParameter)
        param.lock = None
        param._target = None
        self._broadcast_lock_update(name, None)

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

    # ------------------------------------------------------------------
    # Type API (plan decisions D11, D15, D16)
    #
    # The Type registry (``self._types``) lives on the root Parameter
    # Manager only: it maps each Type name to its ``_TypeDefinition``. A
    # Type's entries are relative dotted paths with a default value and a
    # unit; its Nested Types map the submodule name that requires them to
    # the nested Type's name. Type names are refused for the reserved
    # Globals submodule ``_globals``. Methods validate before mutating and
    # name every offending path or Type in an error. No Type method emits
    # a Broadcast yet: the ``pm-type-update`` emissions arrive with the
    # Type-editing broadcasts task.
    # ------------------------------------------------------------------

    def _require_type(self, name: str) -> "_TypeDefinition":
        """The registry entry of the Type ``name``; raises ``ValueError``
        naming the name when no such Type exists."""
        try:
            return self._types[name]
        except KeyError:
            raise ValueError(f"no Type named '{name}' exists") from None

    def add_type(self, name: str) -> None:
        """Create an empty Type named ``name`` in the Type registry.

        Raises ``ValueError`` naming the name when it is the reserved
        Globals name ``_globals`` or when a Type with that name exists
        already; nothing is changed then. A fresh Type has no entries and
        no Nested Types, so it has no Instances until entries are added.

        :param name: Name of the Type.
        """
        # validate-then-mutate: both refusals are checked before the
        # registry is touched
        if name == "_globals":
            raise ValueError(
                f"'{name}' is not a valid Type name: "
                "the Globals submodule name is reserved"
            )
        if name in self._types:
            raise ValueError(f"a Type named '{name}' already exists")
        self._types[name] = _TypeDefinition(name=name)

    def remove_type(self, name: str) -> None:
        """Remove the Type ``name`` from the Type registry.

        The parameters of Instances are untouched (D13). Raises
        ``ValueError`` when no such Type exists, and — naming every Type
        that nests it — while any other Type still requires ``name`` as a
        Nested Type; nothing is removed then.

        :param name: Name of the Type.
        """
        self._require_type(name)
        nesting = sorted(
            definition.name
            for definition in self._types.values()
            if name in definition.nested.values()
        )
        if nesting:
            nesters = ", ".join(f"'{other}'" for other in nesting)
            raise ValueError(
                f"cannot remove Type '{name}': nested in Type(s) {nesters}"
            )
        del self._types[name]

    def list_types(self) -> List[str]:
        """Names of every Type in the Type registry."""
        return list(self._types)

    def get_type(self, name: str) -> "PMTypeBluePrint":
        """The Type ``name`` as a :class:`PMTypeBluePrint`: its own
        entries as ``{path: {default, unit, target}}``, its Nested Types
        as ``{submodule: type}``, and the computed effective parameter
        set as ``{path: {unit, from_type}}``. Raises ``ValueError``
        naming the name when no such Type exists, and like
        :meth:`_effective_parameters` when its Nested Types cycle or its
        effective set contains a path twice."""
        definition = self._require_type(name)
        return PMTypeBluePrint(
            name=definition.name,
            parameters={
                path: {
                    "default": entry.default,
                    "unit": entry.unit,
                    "target": entry.target,
                }
                for path, entry in definition.parameters.items()
            },
            nested=dict(definition.nested),
            effective=self._effective_parameters(name),
        )

    def _effective_parameters(self, type_name: str) -> Dict[str, Dict[str, str]]:
        """The effective parameter set of the Type ``type_name`` (D11):
        every entry path of the Type itself and of its Nested Types,
        expanded recursively under the submodule name that requires them,
        mapped to ``{"unit": <unit>, "from_type": <defining Type>}``.

        Raises ``ValueError`` naming the cycle when the Nested Types
        reachable from ``type_name`` form a cycle, naming both Type names
        when a Nested Type is missing from the registry, and — naming
        every offending path — when an entry path appears twice in the
        expanded set."""
        definition = self._require_type(type_name)
        # cycles first: the expansion below would not terminate
        cycle = self._nested_cycle(definition)
        if cycle is not None:
            raise ValueError(f"cycle in nested Types: {' -> '.join(cycle)}")
        # the cycle walk visited every Nested Type of the closure, so all
        # lookups below are known to exist
        effective: Dict[str, Dict[str, str]] = {}
        duplicated: List[str] = []
        self._collect_effective(definition, "", effective, duplicated)
        if duplicated:
            paths = ", ".join(f"'{path}'" for path in sorted(duplicated))
            raise ValueError(
                f"parameter path(s) {paths} appear more than once in the "
                f"effective set of Type '{type_name}'"
            )
        return effective

    def _nested_cycle(
        self, definition: "_TypeDefinition"
    ) -> "List[str] | None":
        """The chain of Type names of the first cycle among the Nested
        Types reachable from ``definition`` (the chain starts and ends
        with the same Type), or ``None`` when none is reachable. Raises
        ``ValueError`` naming both names when a Nested Type is not in the
        registry. The walk follows each branch with its own chain, so
        nesting the same Type at several submodules is not a cycle."""
        def walk(defn: _TypeDefinition, chain: List[str]) -> List[str] | None:
            for nested_name in defn.nested.values():
                if nested_name in chain:
                    return chain[chain.index(nested_name):] + [nested_name]
                nested = self._types.get(nested_name)
                if nested is None:
                    raise ValueError(
                        f"Type '{defn.name}' nests '{nested_name}', "
                        "which does not exist"
                    )
                cycle = walk(nested, chain + [nested_name])
                if cycle is not None:
                    return cycle
            return None

        return walk(definition, [definition.name])

    def _collect_effective(
        self,
        definition: "_TypeDefinition",
        prefix: str,
        effective: Dict[str, Dict[str, str]],
        duplicated: List[str],
    ) -> None:
        """Add every entry of ``definition`` — and, recursively, of its
        Nested Types under their submodule names — to ``effective``,
        recording every path that appears more than once in
        ``duplicated`` instead of raising, so one error can name them all."""
        for path, entry in definition.parameters.items():
            full_path = f"{prefix}{path}"
            if full_path in effective:
                duplicated.append(full_path)
            else:
                effective[full_path] = {
                    "unit": entry.unit,
                    "from_type": definition.name,
                }
        for submodule, nested_name in definition.nested.items():
            self._collect_effective(
                self._types[nested_name],
                f"{prefix}{submodule}.",
                effective,
                duplicated,
            )

    # ------------------------------------------------------------------
    # Instance matching (plan decisions D12, D16; ADR-0001)
    #
    # Instances are duck-typed: a Parameter Group is an Instance of a Type
    # because it carries every path of the Type's effective parameter set,
    # each with the unit the Type declares; nothing stores membership and
    # matching walks the tree on every query. The root is never an
    # Instance, and the reserved Globals submodule ``_globals`` — wherever
    # it appears in the tree — and everything under it are excluded from
    # matching. ``instances_of`` and ``types_of`` are read-only queries:
    # they change no state and emit no Broadcast.
    # ------------------------------------------------------------------

    def _iter_submodule_groups(self) -> Iterator[Tuple[str, "ParameterGroup"]]:
        """Yield ``(dotted path, Parameter Group)`` for every Parameter
        Group below this Parameter Manager, at any depth: never the root
        itself, and never the reserved Globals submodule ``_globals`` or
        anything inside it (D12)."""
        def walk(
            group: "ParameterGroup", prefix: str
        ) -> Iterator[Tuple[str, "ParameterGroup"]]:
            for name, sm in group.submodules.items():
                assert isinstance(sm, ParameterGroup)
                if name == "_globals":
                    continue
                path = f"{prefix}{name}"
                yield path, sm
                yield from walk(sm, f"{path}.")

        yield from walk(self, "")

    @staticmethod
    def _carries_effective_set(
        group: "ParameterGroup", effective: Dict[str, Dict[str, str]]
    ) -> bool:
        """Whether the Parameter Group ``group`` carries every path of the
        effective set ``effective`` with the unit the Type declares for it
        (D12): a match requires existence **and** unit; values are
        irrelevant."""
        for path, spec in effective.items():
            try:
                param = group._get_param(path)
            except ValueError:
                return False
            if getattr(param, "unit", None) != spec["unit"]:
                return False
        return True

    def _instances_of_effective(
        self, effective: Dict[str, Dict[str, str]]
    ) -> List[str]:
        """Paths (relative to this Parameter Manager) of every Parameter
        Group in the tree that is an Instance for the effective set
        ``effective``: every submodule at any depth that carries the whole
        set with the declared units (D12)."""
        return [
            path
            for path, group in self._iter_submodule_groups()
            if self._carries_effective_set(group, effective)
        ]

    def instances_of(self, type_name: str) -> List[str]:
        """Paths (relative to this Parameter Manager) of every Instance of
        the Type ``type_name`` (D12): every Parameter Group at any depth
        that carries every path of the Type's effective set with the unit
        the Type declares; values are irrelevant. The root is never an
        Instance, the Globals submodule ``_globals`` and everything under
        it are excluded, and an empty Type has no Instances (ADR-0001).
        Matching is computed on demand; this query changes no state.

        Raises ``ValueError`` naming the name when no such Type exists,
        and like :meth:`_effective_parameters` when its Nested Types cycle
        or its effective set contains a path twice.

        :param type_name: Name of the Type.
        :return: Paths of the Instances, in tree order.
        """
        effective = self._effective_parameters(type_name)
        if not effective:
            return []
        return self._instances_of_effective(effective)

    def types_of(self, path: str) -> List[str]:
        """Names of the Types claiming the parameter at ``path`` (a dotted
        path relative to this Parameter Manager), innermost first (D16):
        the Type whose Instance is the deepest submodule above the
        parameter wins, then the one with the largest effective set, with
        any remaining tie broken by Type name. A Type claims the parameter
        when an Instance of it above the parameter — some submodule the
        parameter lives under — carries the parameter's path relative to
        that Instance in its effective set. Parameters under the Globals
        submodule ``_globals`` are claimed by nothing, since matching
        excludes ``_globals`` (D12). Matching is computed on demand; this
        query changes no state.

        Raises ``ValueError`` naming the path when no parameter exists
        there.

        :param path: Path of the parameter.
        :return: Claiming Type names, innermost first.
        """
        self._resolve_param(path)
        # one claim per Type: when a Type claims the parameter through
        # more than one Instance, its innermost Instance orders it
        claims: Dict[str, Tuple[int, int]] = {}
        for definition in self._types.values():
            effective = self._effective_parameters(definition.name)
            if not effective:
                continue
            for submodule_path in self._instances_of_effective(effective):
                prefix = f"{submodule_path}."
                if not path.startswith(prefix):
                    continue
                if path[len(prefix):] not in effective:
                    continue
                depth = len(submodule_path)
                size = len(effective)
                known = claims.get(definition.name)
                if known is None or depth > known[0]:
                    claims[definition.name] = (depth, size)
        return sorted(
            claims,
            key=lambda name: (-claims[name][0], -claims[name][1], name),
        )

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
