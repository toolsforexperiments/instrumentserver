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
    PARAMETER_CREATION,
    PM_LOCK_UPDATE,
    PM_TYPE_UPDATE,
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
    drops. Every Type-editing method emits ``pm-type-update`` with the
    edited Type's fresh ``PMTypeBluePrint`` (D22), and the parameters the
    Type edits and :meth:`add_instance` create as side effects are
    re-emitted as ``parameter-creation`` Broadcasts (ADR-0003); direct
    ``add_parameter`` calls keep being announced by the Server, so nothing
    is announced twice. Declaring a Type Lock with
    :meth:`lock_type_parameter` and removing it with
    :meth:`unlock_type_parameter` do both: they emit the
    ``pm-lock-update`` Broadcasts of the Locks the declaration creates and
    the ``pm-type-update`` of the edited Type, and every new Instance gets
    the existing Type Locks of its Type at creation (D17). Removing a
    parameter that is the stored Target of Type Locks drops the Locks
    pointing at it and clears those Type Locks, emitting one
    ``pm-type-update`` per affected Type (D18).

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

        Raises ``ValueError`` naming the offending path, creating nothing,
        when ``name`` is the reserved Globals name ``_globals`` or starts
        with it (D18): the Globals submodule holds only the default
        Targets of Type Locks, and its parameters are created on demand by
        :meth:`_ensure_global_target`, not through the public API. Since a
        Parameter Group routes its ``add_parameter`` to the root (D15),
        this check covers calls made on any Parameter Group of this
        Parameter Manager as well.

        :param name: Name of the parameter; see
            :meth:`ParameterGroup.add_parameter`.
        :param kw: Any keyword arguments will be passed on to
            qcodes.Instrument.add_parameter, as in
            :meth:`ParameterGroup.add_parameter`.
        :return: None.
        """
        # validate-then-mutate: the Globals refusal runs before anything
        # is created (rule 3)
        if name == "_globals" or name.startswith("_globals."):
            raise ValueError(
                f"'{name}' is not a valid parameter path: "
                "the Globals submodule name is reserved"
            )
        kw["parameter_class"] = ManagedParameter
        kw["path"] = f"{self.name}.{name}"
        super().add_parameter(name, **kw)

    def _create_managed_parameter(
        self, path: str, initial_value: Any, unit: str
    ) -> None:
        """Create the parameter at the dotted path ``path`` (relative to
        this Parameter Manager) through the internal creation path —
        ``_get_parent(..., create_parent=True)`` +
        ``_add_own_parameter`` — as a :class:`ManagedParameter` whose
        ``path`` is the full dotted form with the instrument name, exactly
        like the public :meth:`add_parameter` creates its parameters.
        Missing Parameter Groups on the way are created; a segment of
        ``path`` that is an existing parameter raises ``ValueError``
        (through :meth:`_get_parent`).

        This is the shared creation path of the callers that must bypass
        the public :meth:`add_parameter` refusal of the Globals name
        (D18): :meth:`_ensure_global_target`, which creates the default
        Target of a Type Lock declaration, and :meth:`fromParamDict`,
        which creates the missing parameters a profile file asks for,
        Globals parameters included. It emits nothing: the callers own
        their Broadcasts.
        """
        parent = self._get_parent(path, create_parent=True)
        parent._add_own_parameter(
            path.split(".")[-1],
            parameter_class=ManagedParameter,
            path=self._full_path(path),
            initial_value=initial_value,
            unit=unit,
        )

    def _root_for_new_groups(self) -> "ParameterManager":
        """Parameter Groups created under the Parameter Manager belong to
        it: it is their root."""
        return self

    def remove_parameter(self, param_name: str, cleanup: bool = True) -> None:
        """Remove a parameter, first removing every Lock whose Target it is
        (ADR-0002): the Followers become plain parameters and answer ``get``
        with their own values again. One ``pm-lock-update`` Broadcast with a
        ``None`` value is emitted per dropped Lock (D10).

        When the removed parameter is the stored Target of one or more Type
        Locks — a Globals parameter, or any parameter an explicit Type Lock
        points at — the Type Lock is cleared as well (D18): every own entry
        of every Type whose stored Target it was gets ``target=None``, and
        one ``pm-type-update`` Broadcast per affected Type, in registry
        order and carrying the Type's fresh :class:`PMTypeBluePrint`, is
        emitted after the ``pm-lock-update``s (D22). The Locks a cleared
        Type Lock had put on Instance parameters are ordinary Locks
        pointing at the removed parameter, so the same cleanup drops them;
        a parameter that is no Type Lock Target emits no
        ``pm-type-update``.

        Same signature and deletion behaviour as
        :meth:`ParameterGroup.remove_parameter`; the path is relative to
        this Parameter Manager. The deletion itself emits nothing here:
        the Server announces a direct ``remove_parameter`` call with a
        ``parameter-deletion`` Broadcast (ADR-0003).
        """
        # validate-then-mutate: the parameter must exist before any Lock or
        # Type Lock is touched. The checks mirror what the deletion itself
        # would raise.
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

        # every Type Lock whose stored Target the removed parameter was is
        # cleared with it (D18): the entry keeps no Target that points
        # nowhere, so no later Instance is locked to a missing parameter.
        # Own entries only: a nesting Type's effective set carries units
        # and defining Types, not Targets, so only the Type owning the
        # entry is affected (like lock_type_parameter).
        affected_types: List[str] = []
        for type_name, definition in self._types.items():
            touched = False
            for entry in definition.parameters.values():
                if entry.target == target_full:
                    entry.target = None
                    touched = True
            if touched:
                affected_types.append(type_name)

        # broadcasts after the mutation, in order: one pm-lock-update with
        # None per dropped Follower (D10), then one pm-type-update per
        # affected Type, in registry order (D22); the deletion itself
        # emits nothing here
        for rel_path in dropped_followers:
            self._broadcast_lock_update(rel_path, None)
        for type_name in affected_types:
            self._broadcast_type_update(type_name)

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

    def _broadcast_type_update(self, type_name: str) -> None:
        """Emit one ``pm-type-update`` Broadcast about the Type ``type_name``
        (D22): ``name`` is the Type's full dotted name and the payload is
        its fresh :class:`PMTypeBluePrint`, so a GUI can replace that one
        Type locally with no follow-up fetch. With no sink registered,
        :meth:`broadcast` is a no-op, so standalone use of the Parameter
        Manager emits nothing."""
        self.broadcast(
            ParameterBroadcastBluePrint(
                name=f"{self.name}.{type_name}",
                action=PM_TYPE_UPDATE,
                value=self.get_type(type_name),
            )
        )

    def _broadcast_parameter_creation(
        self, parameter_path: str, value: Any, unit: str
    ) -> None:
        """Re-emit one ``parameter-creation`` Broadcast for a parameter this
        Parameter Manager created as a side effect of a Type edit or of
        :meth:`add_instance` (D22, ADR-0003), in the same shape the Server
        emits for a direct ``add_parameter`` call: the full dotted path as
        ``name``, the initial value as ``value`` and the unit as ``unit``.
        Direct ``add_parameter`` calls are announced by the Server and emit
        nothing here, so nothing is announced twice."""
        self.broadcast(
            ParameterBroadcastBluePrint(
                name=self._full_path(parameter_path),
                action=PARAMETER_CREATION,
                value=value,
                unit=unit,
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
    # name every offending path or Type in an error.
    #
    # Every Type-editing method emits its Broadcasts only after the whole
    # mutation succeeded (D22): one ``parameter-creation`` Broadcast per
    # parameter the edit created as a side effect, in creation order,
    # followed by one ``pm-type-update`` Broadcast per affected Type — the
    # edited Type first, then every Type nesting it, whose effective
    # parameter set the edit changed too — carrying that Type's fresh
    # ``PMTypeBluePrint``; ``remove_type`` emits exactly one
    # ``pm-type-update`` with a ``None`` payload. ``set_type_parameter_default``
    # changes no effective set, so only the edited Type is named. The
    # read-only queries (``list_types``, ``get_type``, ``instances_of``,
    # ``types_of``) and failed validations emit nothing.
    # ------------------------------------------------------------------

    def _require_type(
        self, name: str, types: "Dict[str, _TypeDefinition] | None" = None
    ) -> "_TypeDefinition":
        """The registry entry of the Type ``name``; raises ``ValueError``
        naming the name when no such Type exists. ``types`` defaults to
        the Type registry; the version-2 document reader passes the
        candidate registry built from the document, so the expansion
        helpers can run on it without touching the real one."""
        if types is None:
            types = self._types
        try:
            return types[name]
        except KeyError:
            raise ValueError(f"no Type named '{name}' exists") from None

    def add_type(self, name: str) -> None:
        """Create an empty Type named ``name`` in the Type registry.

        Raises ``ValueError`` naming the name when it is the reserved
        Globals name ``_globals`` or when a Type with that name exists
        already; nothing is changed then. A fresh Type has no entries and
        no Nested Types, so it has no Instances until entries are added.
        Emits one ``pm-type-update`` Broadcast carrying the new Type's
        :class:`PMTypeBluePrint` after it is created (D22); a failed
        validation emits nothing.

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
        self._broadcast_type_update(name)

    def remove_type(self, name: str) -> None:
        """Remove the Type ``name`` from the Type registry.

        The parameters of Instances are untouched (D13). Raises
        ``ValueError`` when no such Type exists, and — naming every Type
        that nests it — while any other Type still requires ``name`` as a
        Nested Type; nothing is removed then. Emits exactly one
        ``pm-type-update`` Broadcast with a ``None`` payload after the
        Type is removed (D22): nobody nests it, so no other Type is
        affected; a failed validation emits nothing.

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
        self.broadcast(
            ParameterBroadcastBluePrint(
                name=f"{self.name}.{name}", action=PM_TYPE_UPDATE, value=None
            )
        )

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
        expanded = self._expand_effective(type_name)
        return {
            path: {"unit": entry.unit, "from_type": from_type}
            for path, (entry, from_type) in expanded.items()
        }

    def _expand_effective(
        self,
        type_name: str,
        types: "Dict[str, _TypeDefinition] | None" = None,
    ) -> Dict[str, Tuple["_TypeEntry", str]]:
        """The effective parameter set of the Type ``type_name`` in raw
        form: every expanded path mapped to the :class:`_TypeEntry` that
        defines it and the name of the Type defining it. Raises the same
        errors as :meth:`_effective_parameters` (unknown Type, a cycle,
        a Nested Type missing from the registry, a path appearing twice).
        ``types`` defaults to the Type registry; the version-2 document
        reader passes the candidate registry built from the document, the
        way :meth:`add_nested_type` validates a candidate."""
        definition = self._require_type(type_name, types)
        # cycles first: the expansion below would not terminate
        cycle = self._nested_cycle(definition, types=types)
        if cycle is not None:
            raise ValueError(f"cycle in nested Types: {' -> '.join(cycle)}")
        # the cycle walk visited every Nested Type of the closure, so all
        # lookups below are known to exist
        expanded: Dict[str, Tuple[_TypeEntry, str]] = {}
        duplicated: List[str] = []
        self._collect_effective(definition, "", expanded, duplicated, types=types)
        if duplicated:
            paths = ", ".join(f"'{path}'" for path in sorted(duplicated))
            raise ValueError(
                f"parameter path(s) {paths} appear more than once in the "
                f"effective set of Type '{type_name}'"
            )
        return expanded

    def _effective_entries(self, type_name: str) -> Dict[str, _TypeEntry]:
        """The effective parameter set of the Type ``type_name`` carrying
        the full :class:`_TypeEntry` (default value, unit, Type Lock
        Target) of the entry that defines each path: what writing the set
        into the tree as parameters needs. Raises like
        :meth:`_effective_parameters`."""
        return {
            path: entry
            for path, (entry, _) in self._expand_effective(type_name).items()
        }

    def _nested_cycle(
        self,
        definition: "_TypeDefinition",
        types: Dict[str, "_TypeDefinition"] | None = None,
    ) -> "List[str] | None":
        """The chain of Type names of the first cycle among the Nested
        Types reachable from ``definition`` (the chain starts and ends
        with the same Type), or ``None`` when none is reachable. Raises
        ``ValueError`` naming both names when a Nested Type is not in
        ``types``. The walk follows each branch with its own chain, so
        nesting the same Type at several submodules is not a cycle.
        ``types`` defaults to the Type registry; ``add_nested_type``
        passes a copied registry holding a candidate definition so it can
        refuse a cycle before mutating anything."""
        if types is None:
            types = self._types

        def walk(defn: _TypeDefinition, chain: List[str]) -> List[str] | None:
            for nested_name in defn.nested.values():
                if nested_name in chain:
                    return chain[chain.index(nested_name):] + [nested_name]
                nested = types.get(nested_name)
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
        effective: Dict[str, Tuple[_TypeEntry, str]],
        duplicated: List[str],
        types: "Dict[str, _TypeDefinition] | None" = None,
    ) -> None:
        """Add every entry of ``definition`` — and, recursively, of its
        Nested Types under their submodule names — to ``effective`` as
        ``(entry, defining Type name)`` pairs, recording every path that
        appears more than once in ``duplicated`` instead of raising, so
        one error can name them all. ``types`` defaults to the Type
        registry; see :meth:`_expand_effective`."""
        if types is None:
            types = self._types
        for path, entry in definition.parameters.items():
            full_path = f"{prefix}{path}"
            if full_path in effective:
                duplicated.append(full_path)
            else:
                effective[full_path] = (entry, definition.name)
        for submodule, nested_name in definition.nested.items():
            self._collect_effective(
                types[nested_name],
                f"{prefix}{submodule}.",
                effective,
                duplicated,
                types=types,
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

    # ------------------------------------------------------------------
    # Type edits with Instance side effects (plan decisions D11, D13, D16)
    #
    # Every edit validates all its preconditions first and raises before
    # touching anything: on an error the Type registry and the parameter
    # tree are exactly as they were. The side effects target the Instances
    # that exist before the edit — they are computed while the registry
    # still holds the old shape, because after the edit no submodule
    # matches until it carries what is new — together with the Instances
    # of every Type whose effective parameter set contains the edited
    # Type through nesting. The affected parameter paths are collected
    # de-duplicated and each missing one is created once, through the
    # ordinary ``add_parameter`` path, as a ``ManagedParameter`` with the
    # entry's default value and unit. A parameter that already exists at
    # a target path is left alone: the submodule it lives in simply stops
    # being an Instance when its unit differs (D1).
    #
    # The Broadcasts go out only after the whole edit succeeded (D22):
    # one ``parameter-creation`` per created parameter, in creation
    # order, then the Type Locks applied to the submodules the edit
    # turned into new Instances (D17), each emitting one
    # ``pm-lock-update``, then one ``pm-type-update`` per affected Type —
    # the edited Type first, then every Type nesting it, whose effective
    # parameter set the edit changed too. The affected Types are the keys
    # of ``_nesting_prefixes``, which the side-effect computation already
    # walks. A refused edit emits nothing.
    # ------------------------------------------------------------------

    def _nesting_prefixes(self, type_name: str) -> Dict[str, List[str]]:
        """Map every Type whose effective parameter set contains the
        entries of ``type_name`` through nesting to the dotted submodule
        prefixes under which they sit in that set. ``type_name`` itself
        maps to ``[""]``; a Type requiring it directly at ``readout`` maps
        to ``["readout."]``, and so on transitively, with one prefix per
        nesting chain (a Type nesting it at several submodules maps to
        several). The walk follows the ``nested`` maps upwards, from the
        nested Types to the Types requiring them, and stops at a Type
        already on the current branch, so it terminates even on a
        registry that holds a cycle (which the public API refuses)."""
        prefixes: Dict[str, List[str]] = {type_name: [""]}

        def walk(name: str, prefix: str, branch: Tuple[str, ...]) -> None:
            for parent_name, definition in self._types.items():
                for submodule, nested_name in definition.nested.items():
                    if nested_name != name or parent_name in branch:
                        continue
                    extended = f"{submodule}.{prefix}"
                    known = prefixes.setdefault(parent_name, [])
                    if extended not in known:
                        known.append(extended)
                        walk(parent_name, extended, branch + (parent_name,))

        walk(type_name, "", (type_name,))
        return prefixes

    def _check_creation_targets(
        self, targets: List[Tuple[str, str]]
    ) -> None:
        """Validate the parameters a Type edit or :meth:`add_instance` is
        about to create, before anything is mutated. ``targets`` holds
        ``(Instance path, relative target path)`` pairs. An intermediate
        segment of a target may not be an existing parameter (a parameter
        cannot have child parameters) and the final segment may not be an
        existing Parameter Group (a Parameter Group cannot become a
        parameter); a target whose final segment is an existing parameter
        is fine — it is left alone. The Instance path itself is walked
        first: a segment of it that is an existing parameter blocks every
        target below it, while a Parameter Group missing along it is
        created on the way, so nothing below it can clash (this is how
        ``add_instance`` names Parameter Groups that do not exist yet).
        One de-duplicated target path may also not be a strict
        segment-prefix of another target of the same edit: creating the
        shorter parameter would take the Parameter Group the longer one
        needs, so the edit could never carry out its own pre-check.
        Raises ``ValueError`` naming every offending full path."""
        offending: Dict[str, str] = {}
        seen: set = set()
        for instance_path, relative_target in targets:
            full = f"{instance_path}.{relative_target}"
            if full in seen:
                continue
            seen.add(full)
            # walk the Instance path: every segment must be a Parameter
            # Group, a missing one is created on the way, and an existing
            # parameter blocks everything below it
            group: ParameterGroup | None = self
            blocked: str | None = None
            walked: List[str] = []
            for segment in instance_path.split("."):
                if not segment:
                    continue
                assert group is not None  # cleared only with an immediate break
                if segment in group.parameters:
                    blocked = ".".join([*walked, segment])
                    break
                submodule = group.submodules.get(segment)
                if submodule is None:
                    # missing Parameter Group on the Instance path: it is
                    # created on the way, so nothing below it can clash
                    group = None
                    break
                walked.append(segment)
                group = submodule
            if blocked is not None:
                offending[full] = (
                    f"'{blocked}' is a parameter, and cannot have "
                    "child parameters"
                )
                continue
            if group is None:
                continue
            segments = relative_target.split(".")
            for index, segment in enumerate(segments):
                last = index == len(segments) - 1
                if segment in group.parameters:
                    if not last:
                        blocked = f"{instance_path}.{'.'.join(segments[:index + 1])}"
                        offending[full] = (
                            f"'{blocked}' is a parameter, and cannot have "
                            "child parameters"
                        )
                    break
                if last:
                    if segment in group.submodules:
                        offending[full] = (
                            f"'{full}' is already a Parameter Group"
                        )
                    break
                submodule = group.submodules.get(segment)
                if submodule is None:
                    # missing Parameter Group: it is created on the way,
                    # so nothing deeper along this target can clash
                    break
                assert isinstance(submodule, ParameterGroup)
                group = submodule
        # the prefix check runs over the de-duplicated targets of this one
        # edit, whatever Instance or nesting chain produced them
        full_paths = sorted(seen)
        for index, shorter in enumerate(full_paths):
            for longer in full_paths[index + 1:]:
                if longer.startswith(f"{shorter}."):
                    blocked, blocker = longer, shorter
                elif shorter.startswith(f"{longer}."):
                    blocked, blocker = shorter, longer
                else:
                    continue
                offending.setdefault(
                    blocked,
                    f"'{blocker}' is also created by this edit, and a "
                    "parameter cannot have child parameters",
                )
        if offending:
            details = "; ".join(
                f"cannot create parameter '{path}': {reason}"
                for path, reason in offending.items()
            )
            raise ValueError(details)

    def _require_type_entry(self, type_name: str, path: str) -> _TypeEntry:
        """The Type ``type_name``'s own entry at ``path``. Raises
        ``ValueError`` naming the path — and the Type that defines it,
        when the path only reaches the effective parameter set through a
        Nested Type — when it is not an entry of the Type itself."""
        definition = self._require_type(type_name)
        entry = definition.parameters.get(path)
        if entry is not None:
            return entry
        expanded = self._expand_effective(type_name)
        if path in expanded:
            from_type = expanded[path][1]
            raise ValueError(
                f"parameter path '{path}' is not an entry of Type "
                f"'{type_name}' itself: it is only in the effective set "
                f"through the entry of Type '{from_type}'"
            )
        raise ValueError(
            f"parameter path '{path}' is not an entry of Type '{type_name}'"
        )

    def _instances_before_edit(self, affected: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """The Instances of every Type in ``affected``, computed while the
        registry still holds the shape the edit is about to change (D13):
        after the edit no submodule matches until it carries what is new,
        so the side effects must key off the Instances found now."""
        return {name: self.instances_of(name) for name in affected}

    def add_type_parameter(
        self, type_name: str, path: str, default: Any = None, unit: str = ""
    ) -> None:
        """Add an entry to the Type ``type_name`` (D11) and create the
        parameter at ``path`` — with the entry's default value and unit —
        in every Instance of the Type that lacks it, and in every Instance
        of a Type whose effective parameter set contains ``type_name``
        through nesting (D13). Parameters that already exist at a target
        path are left alone, whatever their unit; the missing Parameter
        Groups along a target path are created.

        Raises ``ValueError`` — leaving the registry and the parameter
        tree untouched — naming every offending path when no such Type
        exists, when ``path`` is empty or has an empty segment, when
        ``path`` is already in the Type's effective parameter set (naming
        the Type that defines it), when ``prefix + path`` is already in
        the effective parameter set of a Type nesting this one — naming
        every colliding path and the Type whose effective set holds it,
        since the duplicated path would break every query on that Type —
        or when a target path cannot be created because an
        intermediate segment is an existing parameter, the final segment
        is an existing Parameter Group, or another target of the same
        edit is a strict segment-prefix of it.

        After the edit succeeds it emits one ``parameter-creation``
        Broadcast per parameter it created, in creation order, followed by
        one ``pm-lock-update`` Broadcast per Type Lock it applied to a new
        Instance and one ``pm-type-update`` Broadcast per affected Type —
        the edited Type first, then every Type nesting it, whose effective
        parameter set the new entry extends (D17, D22, ADR-0003); a failed
        validation emits nothing. A new Instance — a submodule that is an
        Instance of an affected Type after the edit but was not one before
        — gets the existing Type Locks of that Type applied to its
        parameters at the Type's locked effective entries, parameters the
        edit kept included; skips are collected into one ``logger.warning``
        and the edit still succeeds.

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the entry.
        :param default: Default value the created parameters start with.
        :param unit: Unit of the entry and the created parameters.
        """
        # validate-then-mutate: every check below runs before the registry
        # or the tree is touched
        definition = self._require_type(type_name)
        if not path or any(segment == "" for segment in path.split(".")):
            raise ValueError(
                f"'{path}' is not a valid parameter path for a Type entry"
            )
        expanded = self._expand_effective(type_name)
        if path in expanded:
            from_type = expanded[path][1]
            raise ValueError(
                f"parameter path '{path}' is already in the effective set "
                f"of Type '{type_name}' (defined by Type '{from_type}')"
            )
        affected = self._nesting_prefixes(type_name)
        # the new path must not collide in the effective parameter set of
        # a Type nesting this one either — the same check the Nested Type
        # edit runs for its candidate sets (the edited Type's own case is
        # handled by the check above); every colliding path and the Type
        # whose effective set holds it are collected, so one error can
        # name them all (rule 3)
        collisions: List[str] = []
        for name in affected:
            current = set(self._expand_effective(name))
            for prefix in affected[name]:
                candidate = f"{prefix}{path}"
                if candidate in current:
                    described = (
                        f"'{candidate}' (in the effective set of "
                        f"Type '{name}')"
                    )
                    if described not in collisions:
                        collisions.append(described)
        if collisions:
            raise ValueError(
                f"cannot add '{path}' to Type '{type_name}': parameter "
                f"path(s) {', '.join(collisions)} would appear more than "
                "once"
            )
        instances_before = self._instances_before_edit(affected)
        targets = [
            (instance_path, f"{prefix}{path}")
            for name, prefixes in affected.items()
            for instance_path in instances_before[name]
            for prefix in prefixes
        ]
        self._check_creation_targets(targets)
        definition.parameters[path] = _TypeEntry(default=default, unit=unit)
        created: set = set()
        creations: List[Tuple[str, Any, str]] = []
        for instance_path, relative_target in targets:
            full = f"{instance_path}.{relative_target}"
            if full in created:
                continue
            created.add(full)
            if not self.has_param(full):
                self.add_parameter(full, initial_value=default, unit=unit)
                creations.append((full, default, unit))
        # broadcasts after the whole edit succeeded (D22): one
        # parameter-creation per created parameter in creation order,
        # then the Type Locks of the new Instances (each emitting its
        # pm-lock-update, D17), then one pm-type-update per affected Type
        for created_path, initial_value, created_unit in creations:
            self._broadcast_parameter_creation(
                created_path, initial_value, created_unit
            )
        self._apply_type_locks_to_new_instances(list(affected), instances_before)
        for name in affected:
            self._broadcast_type_update(name)

    def remove_type_parameter(self, type_name: str, path: str) -> None:
        """Remove the entry at ``path`` from the Type ``type_name``'s own
        entries (D13): the parameters of the Instances are untouched, and
        the submodules that no longer carry the whole shape simply stop
        being Instances (D1).

        Raises ``ValueError`` naming the path when no such Type exists,
        when ``path`` is not an entry of the Type itself — naming the
        Type that defines it, when the path only reaches the effective
        parameter set through a Nested Type — and when it is in no
        effective set at all. Nothing is removed then. Emits one
        ``pm-type-update`` Broadcast per affected Type — the edited Type
        first, then every Type nesting it, whose effective parameter set
        loses the path — after the entry is removed (D22); a failed
        validation emits nothing.

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the entry.
        """
        self._require_type_entry(type_name, path)
        affected = self._nesting_prefixes(type_name)
        del self._types[type_name].parameters[path]
        for name in affected:
            self._broadcast_type_update(name)

    def set_type_parameter_default(
        self, type_name: str, path: str, value: Any
    ) -> None:
        """Set the default value of the Type ``type_name``'s own entry at
        ``path`` (D13): the parameters the Instances already carry keep
        their values, and only parameters created later start with the
        new default.

        Raises ``ValueError`` naming the path under the same conditions
        as :meth:`remove_type_parameter`; nothing is changed then. Emits
        one ``pm-type-update`` Broadcast carrying the edited Type's fresh
        blueprint after the default is set (D22); no Broadcast names a
        nesting Type, since a Type's effective parameter set carries
        units and defining Types, not defaults, so their blueprints are
        unchanged. A failed validation emits nothing.

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the entry.
        :param value: The entry's new default value.
        """
        entry = self._require_type_entry(type_name, path)
        entry.default = value
        self._broadcast_type_update(type_name)

    def set_type_parameter_unit(
        self, type_name: str, path: str, unit: str
    ) -> None:
        """Set the unit of the Type ``type_name``'s own entry at ``path``
        and propagate it to that parameter in every Instance of the Type
        and of every Type whose effective parameter set contains
        ``type_name`` through nesting (D13); the target of a propagation
        is one of the Instance's parameters by construction, and a
        parameter already carrying the new unit is simply set again.

        Raises ``ValueError`` naming the path under the same conditions
        as :meth:`remove_type_parameter`; nothing is changed then. Emits
        one ``pm-type-update`` Broadcast per affected Type — the edited
        Type first, then every Type nesting it, whose effective parameter
        set carries the changed unit — after the unit is set and
        propagated (D22); a failed validation emits nothing.

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the entry.
        :param unit: The entry's and the Instances' new unit.
        """
        entry = self._require_type_entry(type_name, path)
        # the Instances exist before the edit; the propagation targets are
        # among their parameters by construction
        affected = self._nesting_prefixes(type_name)
        instances_before = self._instances_before_edit(affected)
        entry.unit = unit
        propagated: set = set()
        for name, prefixes in affected.items():
            for instance_path in instances_before[name]:
                for prefix in prefixes:
                    full = f"{instance_path}.{prefix}{path}"
                    if full in propagated:
                        continue
                    propagated.add(full)
                    if self.has_param(full):
                        self.parameter(full).unit = unit
        for name in affected:
            self._broadcast_type_update(name)

    def add_nested_type(
        self, type_name: str, submodule: str, nested_type: str
    ) -> None:
        """Require the Nested Type ``nested_type`` at the submodule
        ``submodule`` of the Type ``type_name`` (D11), and write the
        nested Type's effective parameter set under that submodule into
        every Instance of ``type_name`` — and of every Type nesting it —
        that lacks the parameters, with each entry's default value and
        unit (D13).

        Raises ``ValueError`` — leaving the registry and the parameter
        tree untouched — naming every offending name or path when a Type
        does not exist, when ``submodule`` is empty, has an empty segment
        or starts with the reserved Globals name ``_globals`` (D18), when
        the submodule already requires a Nested Type, when the nesting
        would close a cycle (``type_name == nested_type`` included), when
        the resulting effective parameter set of ``type_name`` or of any
        Type nesting it would contain a path twice, or when a target path
        cannot be created because an intermediate segment is an existing
        parameter, the final segment is an existing Parameter Group, or
        another target of the same edit is a strict segment-prefix of it.

        After the edit succeeds it emits one ``parameter-creation``
        Broadcast per parameter it created, in creation order, followed by
        one ``pm-lock-update`` Broadcast per Type Lock it applied to a new
        Instance and one ``pm-type-update`` Broadcast per affected Type —
        the edited Type first, then every Type nesting it, whose effective
        parameter set the nested entries extend (D17, D22, ADR-0003); a
        failed validation emits nothing. A new Instance — a submodule that
        is an Instance after the edit but was not one before — gets the
        existing Type Locks of its Type applied to its parameters at the
        Type's locked effective entries, parameters the edit kept included;
        the Nested Type's own chain joins the Types whose Type Locks are
        applied, since nesting it completes the submodules at its position
        into Instances of it; skips are collected into one
        ``logger.warning`` and the edit still succeeds.

        :param type_name: Name of the outer Type.
        :param submodule: Name of the submodule that requires the Nested
            Type.
        :param nested_type: Name of the Nested Type.
        """
        # validate-then-mutate: every check below runs before the registry
        # or the tree is touched
        missing = [
            f"no Type named '{name}' exists"
            for name in dict.fromkeys((type_name, nested_type))
            if name not in self._types
        ]
        if missing:
            raise ValueError("; ".join(missing))
        definition = self._types[type_name]
        if not submodule or any(segment == "" for segment in submodule.split(".")):
            raise ValueError(
                f"'{submodule}' is not a valid submodule name for a "
                "Nested Type"
            )
        if submodule.split(".")[0] == "_globals":
            raise ValueError(
                f"'{submodule}' is not a valid submodule name for a "
                "Nested Type: the Globals submodule name is reserved"
            )
        if submodule in definition.nested:
            raise ValueError(
                f"submodule '{submodule}' of Type '{type_name}' already "
                f"requires the Nested Type '{definition.nested[submodule]}'"
            )
        # the cycle check runs on a copied registry holding the candidate
        # definition, so a refusal leaves the real one untouched
        candidate = _TypeDefinition(
            name=definition.name,
            parameters=dict(definition.parameters),
            nested={**definition.nested, submodule: nested_type},
        )
        candidate_registry = dict(self._types)
        candidate_registry[type_name] = candidate
        cycle = self._nested_cycle(candidate, types=candidate_registry)
        if cycle is not None:
            raise ValueError(
                f"cannot nest Type '{nested_type}' at submodule "
                f"'{submodule}' of Type '{type_name}': cycle in nested "
                f"Types: {' -> '.join(cycle)}"
            )
        # the resulting effective parameter set of the edited Type and of
        # every Type nesting it must not contain a path twice; computed
        # against the current registry, which the mutation below follows
        affected = self._nesting_prefixes(type_name)
        # the Nested Type's own chain joins the Types whose Type Locks are
        # applied to new Instances (D17): nesting readout into qubit
        # completes the submodules at the readout position into Instances
        # of readout, whose Type Locks must be applied too; the creations
        # and the pm-type-updates keep using ``affected`` only
        lock_types = list(
            dict.fromkeys([*affected, *self._nesting_prefixes(nested_type)])
        )
        instances_before = {name: self.instances_of(name) for name in lock_types}
        nested_entries = self._effective_entries(nested_type)
        collisions: List[str] = []
        for name in affected:
            current = set(self._expand_effective(name))
            new_paths: List[str] = []
            for prefix in affected[name]:
                for entry_path in nested_entries:
                    new_path = f"{prefix}{submodule}.{entry_path}"
                    if new_path in current or new_path in new_paths:
                        described = (
                            f"'{new_path}' (in the effective set of "
                            f"Type '{name}')"
                        )
                        if described not in collisions:
                            collisions.append(described)
                    else:
                        new_paths.append(new_path)
        if collisions:
            raise ValueError(
                f"cannot nest Type '{nested_type}' at submodule "
                f"'{submodule}' of Type '{type_name}': parameter path(s) "
                f"{', '.join(collisions)} would appear more than once"
            )
        targets = [
            (instance_path, f"{prefix}{submodule}.{entry_path}", entry)
            for name, prefixes in affected.items()
            for instance_path in instances_before[name]
            for prefix in prefixes
            for entry_path, entry in nested_entries.items()
        ]
        self._check_creation_targets(
            [(instance_path, relative_target) for instance_path, relative_target, _ in targets]
        )
        definition.nested[submodule] = nested_type
        created: set = set()
        creations: List[Tuple[str, Any, str]] = []
        for instance_path, relative_target, entry in targets:
            full = f"{instance_path}.{relative_target}"
            if full in created:
                continue
            created.add(full)
            if not self.has_param(full):
                self.add_parameter(
                    full, initial_value=entry.default, unit=entry.unit
                )
                creations.append((full, entry.default, entry.unit))
        # broadcasts after the whole edit succeeded (D22): one
        # parameter-creation per created parameter in creation order,
        # then the Type Locks of the new Instances (each emitting its
        # pm-lock-update, D17), then one pm-type-update per affected Type,
        # the edited Type first
        for created_path, initial_value, created_unit in creations:
            self._broadcast_parameter_creation(
                created_path, initial_value, created_unit
            )
        self._apply_type_locks_to_new_instances(lock_types, instances_before)
        for name in affected:
            self._broadcast_type_update(name)

    def remove_nested_type(self, type_name: str, submodule: str) -> None:
        """Remove the Nested Type required at the submodule ``submodule``
        of the Type ``type_name`` (D13): the parameters of the Instances
        are untouched, and the submodules that no longer carry the whole
        shape simply stop being Instances (D1).

        Raises ``ValueError`` naming the Type and the submodule when no
        such Type exists or the submodule requires no Nested Type;
        nothing is removed then. Emits one ``pm-type-update`` Broadcast
        per affected Type — the edited Type first, then every Type nesting
        it, whose effective parameter set loses the nested paths — after
        the Nested Type is removed (D22); a failed validation emits
        nothing.

        :param type_name: Name of the Type.
        :param submodule: Name of the submodule that requires the Nested
            Type.
        """
        definition = self._require_type(type_name)
        if submodule not in definition.nested:
            raise ValueError(
                f"submodule '{submodule}' of Type '{type_name}' has no "
                "Nested Type"
            )
        affected = self._nesting_prefixes(type_name)
        del definition.nested[submodule]
        for name in affected:
            self._broadcast_type_update(name)

    # ------------------------------------------------------------------
    # Instances (plan decision D14)
    #
    # ``add_instance`` writes a Type's effective parameter set into one
    # named Parameter Group, creating the Parameter Groups on the way.
    # It validates everything first: the Type, the name, a unit conflict
    # on any existing parameter, and the creation targets through
    # ``_check_creation_targets``; on an error nothing is created. An
    # empty Type creates nothing and has no Instances (D12).
    #
    # After the whole call succeeded it emits one ``parameter-creation``
    # Broadcast per parameter it created, in creation order (D22,
    # ADR-0003), then applies the existing Type Locks of the Type and of
    # every Type nesting it to the submodules that are Instances only
    # after the call (D17) — each applied Lock emitting its
    # ``pm-lock-update``; it edits no Type, so it emits no
    # ``pm-type-update``. A refused call emits nothing.
    # ------------------------------------------------------------------

    def add_instance(self, type_name: str, name: str) -> None:
        """Create the Instance ``name`` of the Type ``type_name`` (D14):
        every effective parameter path of the Type that is missing under
        ``name`` — together with the Parameter Groups on the way — is
        created with the entry's default value and unit through the
        ordinary :meth:`add_parameter` path, and every parameter that
        exists at a target path already is kept untouched, with its own
        value and unit. ``name`` is a dotted submodule path relative to
        this Parameter Manager (``"q01"`` or ``"q01.readout"``), so
        nested Instances are allowed. After a successful call ``name``
        carries the whole effective set with the units the Type declares,
        so it is an Instance in :meth:`instances_of` — unless the Type is
        empty: an empty Type has no Instances (D12), creates nothing and
        raises nothing, and the submodule is not created for it.

        Raises ``ValueError`` — creating nothing — naming every offending
        path when no such Type exists, when ``name`` is empty or has an
        empty segment, when ``name`` starts with the reserved Globals
        name ``_globals`` (D18), when a parameter already exists at an
        effective path with a unit different from the one the Type
        declares (the unit-conflict scan runs over every effective path
        before anything is created, D14), or when a target path cannot be
        created because a segment of ``name`` or of the target is an
        existing parameter, or the final segment of a target is an
        existing Parameter Group.

        After the Instance is created it emits one ``parameter-creation``
        Broadcast per parameter it created, in creation order, followed by
        one ``pm-lock-update`` Broadcast per Type Lock it applied to the
        new Instance (D17, D22, ADR-0003); the call edits no Type, so it
        emits no ``pm-type-update``. A failed validation emits nothing.
        As a new Instance, ``name`` gets the existing Type Locks of this
        Type and of every Type nesting it applied to its parameters at
        their locked effective entries — a parameter the call kept (D14)
        included, since a Lock changes neither its own value nor its unit.
        A kept parameter that already carries a Lock on another Target, a
        stored Target that no longer exists and a Lock that would close a
        cycle are skipped, collected into one ``logger.warning``; the
        creation itself still succeeds. Submodules that were Instances
        before the call are untouched.

        :param type_name: Name of the Type.
        :param name: Dotted submodule path of the Instance, relative to
            this Parameter Manager.
        """
        # validate-then-mutate: every check below runs before the tree is
        # touched
        self._require_type(type_name)
        if not name or any(segment == "" for segment in name.split(".")):
            raise ValueError(
                f"'{name}' is not a valid submodule path for an Instance"
            )
        if name.split(".")[0] == "_globals":
            raise ValueError(
                f"'{name}' is not a valid submodule path for an Instance: "
                "the Globals submodule name is reserved"
            )
        effective = self._effective_entries(type_name)
        if not effective:
            # an empty Type has no Instances (D12): there is nothing to
            # create, and the submodule is not created for it
            return
        # the unit-conflict scan runs over every effective path before
        # anything is created (D14); every conflict is collected, so one
        # error can name them all (rule 3)
        conflicts: List[str] = []
        for path, entry in effective.items():
            full = f"{name}.{path}"
            if self.has_param(full):
                existing_unit = getattr(self.parameter(full), "unit", None)
                if existing_unit != entry.unit:
                    conflicts.append(
                        f"'{full}' carries unit '{existing_unit}', the "
                        f"Type declares '{entry.unit}'"
                    )
        if conflicts:
            raise ValueError(
                f"cannot add an Instance of Type '{type_name}' at "
                f"'{name}': " + "; ".join(conflicts)
            )
        self._check_creation_targets([(name, path) for path in effective])
        # the Instances of this Type and of every Type nesting it, before
        # anything is created: the submodules that are Instances only after
        # the call get the existing Type Locks applied (D17)
        lock_types = list(self._nesting_prefixes(type_name))
        instances_before = {name_: self.instances_of(name_) for name_ in lock_types}
        creations: List[Tuple[str, Any, str]] = []
        for path, entry in effective.items():
            full = f"{name}.{path}"
            if not self.has_param(full):
                self.add_parameter(
                    full, initial_value=entry.default, unit=entry.unit
                )
                creations.append((full, entry.default, entry.unit))
        # one parameter-creation per created parameter, in creation order,
        # then the Type Locks of the new Instances (each emitting its
        # pm-lock-update, D17); no pm-type-update: the call edits no Type
        for created_path, initial_value, created_unit in creations:
            self._broadcast_parameter_creation(
                created_path, initial_value, created_unit
            )
        self._apply_type_locks_to_new_instances(lock_types, instances_before)

    # ------------------------------------------------------------------
    # Globals (plan decision D18)
    #
    # The reserved Globals submodule ``_globals`` holds the default
    # Targets of Type Locks. It is created on demand and is never an
    # Instance; matching excludes it and everything under it (D12, the
    # walk in ``_iter_submodule_groups``), and ``add_parameter`` refuses
    # its name. The internal helper ``_ensure_global_target`` creates
    # ``_globals.<type>.<path>`` through the internal creation path —
    # the same one the public ``add_parameter`` ends in. A Globals
    # parameter is otherwise ordinary (D18): it can be set and read, it
    # may itself carry a Lock and be a Lock Target, and it is saved with
    # the profile. Removing one is allowed; :meth:`remove_parameter` then
    # drops the Locks pointing at it and clears the Type Lock it was the
    # stored Target of (D18).
    # ------------------------------------------------------------------

    def _ensure_global_target(self, type_name: str, path: str) -> str:
        """Create the Globals parameter ``_globals.<type_name>.<path>``
        for the Type ``type_name``'s own entry at ``path`` — on demand,
        with the entry's default value and unit — and return its dotted
        path relative to this Parameter Manager (D17, D18).

        This is the internal helper :meth:`lock_type_parameter` builds the
        default Target of a Type Lock declaration with.
        It bypasses the public :meth:`add_parameter` refusal of the
        Globals name through the internal creation path
        (:meth:`_create_managed_parameter`, the
        ``_get_parent(..., create_parent=True)`` +
        ``_add_own_parameter`` pair), creating the parameter as a
        :class:`ManagedParameter` whose ``path`` is the full dotted form
        with the instrument name, like :meth:`add_parameter` does. A
        parameter that exists at the target path already is kept
        untouched — its own value is not changed and nothing is emitted
        (created on demand, D18).

        Raises ``ValueError`` — before anything is touched — naming the
        offending name or path when no such Type exists, when ``path`` is
        not an entry of the Type itself (naming the Type that defines it
        when the path only reaches the effective parameter set through a
        Nested Type; own entries only, like
        :meth:`set_type_parameter_default`), when the parameter exists
        with a unit different from the entry's unit (naming the path and
        both units; unit conflicts are refused like D14), and — through
        the same :meth:`_check_creation_targets` validation the Type
        edits and :meth:`add_instance` run — when a segment of
        ``_globals.<type_name>.<path>`` on the way is an existing
        parameter rather than a Parameter Group, or when the target path
        is an existing Parameter Group.

        When it creates the parameter it emits exactly one
        ``parameter-creation`` Broadcast in the same shape the Type-edit
        side-effect creations use (D22, ADR-0003); it edits no Type, so
        it emits no ``pm-type-update``.

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the Type's own entry.
        :return: The path ``"_globals.<type_name>.<path>"``.
        """
        # validate-then-mutate: every check below runs before the tree is
        # touched (rule 3)
        entry = self._require_type_entry(type_name, path)
        global_path = f"_globals.{type_name}.{path}"
        if self.has_param(global_path):
            existing_unit = getattr(self.parameter(global_path), "unit", None)
            if existing_unit != entry.unit:
                raise ValueError(
                    f"cannot create the Globals parameter '{global_path}': "
                    f"it exists already with unit '{existing_unit}', the "
                    f"entry of Type '{type_name}' declares '{entry.unit}'"
                )
            # created on demand: an existing parameter is kept untouched,
            # with its own value, and emits nothing (D18)
            return global_path
        # a parameter on the way blocks the creation, and the target path
        # may not be an existing Parameter Group: the blocked-target
        # validation is the one ``_check_creation_targets`` already owns
        # for the Type edits and ``add_instance``. The single target here
        # is ``<type_name>.<path>`` under the reserved Globals submodule —
        # which is never an Instance (D18); the ``(Instance path,
        # relative target)`` pair the helper takes is reused only for its
        # walk, and missing Parameter Groups are created on the way
        self._check_creation_targets([("_globals", f"{type_name}.{path}")])
        self._create_managed_parameter(global_path, entry.default, entry.unit)
        self._broadcast_parameter_creation(global_path, entry.default, entry.unit)
        return global_path

    # ------------------------------------------------------------------
    # Type Locks (plan decision D17, task 3.2)
    #
    # A Type Lock is a rule on a Type entry naming a Target: declaring it
    # with ``lock_type_parameter`` stores the Target on the entry (the
    # default Target is the Globals parameter ``_globals.<type>.<path>``,
    # created on demand through ``_ensure_global_target``) and puts an
    # ordinary, locked Lock on the entry's parameter in every current
    # Instance. Instance parameters that carry a Lock on another Target
    # are skipped with a warning and returned; ``unlock_type_parameter``
    # removes only the rule, and the Locks it created stay until they are
    # removed individually. Every new Instance — created by
    # ``add_instance``, or completed by ``add_type_parameter`` /
    # ``add_nested_type`` — gets the existing Type Locks of its Type at
    # creation, pre-existing parameters included. The Locks themselves are
    # applied through the ordinary Lock API, so each state change emits
    # exactly one ``pm-lock-update`` (D10); the declaration and the removal
    # each emit one ``pm-type-update`` for the edited Type (D22).
    # ------------------------------------------------------------------

    def _classify_lock_application(
        self, param_path: str, target_full: str
    ) -> Tuple[str, "str | None"]:
        """Classify what applying the Target ``target_full`` (the full
        dotted form) to the parameter at ``param_path`` would do:
        ``"lock"`` (no Lock present), ``"relock"`` (an unlocked Lock
        remembering the same Target), ``"none"`` (already locked to the
        same Target) or ``"skip"`` together with the Target the
        parameter's Lock points at — a Lock on another Target is left
        alone (D17)."""
        param = self.parameter(param_path)
        lock = getattr(param, "lock", None)
        if lock is None:
            return "lock", None
        if lock.target == target_full:
            return ("none" if lock.locked else "relock"), None
        return "skip", lock.target

    def lock_type_parameter(
        self, type_name: str, path: str, target: str | None = None
    ) -> List[str]:
        """Declare the Type Lock of the entry ``path`` of the Type
        ``type_name`` (D17): the Target is stored on the entry — the
        parameter at ``target`` when given, the Globals parameter
        ``_globals.<type_name>.<path>`` otherwise — and an ordinary,
        locked Lock on that Target is put on the entry's parameter in
        every current Instance of the Type. The default Globals Target is
        created on demand with the entry's default value and unit, through
        :meth:`_ensure_global_target`.

        Instance parameters that already carry a Lock on another Target
        are skipped: they are left untouched, named together with their
        Target in one ``logger.warning``, and returned as a list of dotted
        paths relative to this Parameter Manager (empty when nothing was
        skipped). A parameter already locked to the same Target stays as
        it is; an unlocked Lock remembering the same Target is locked
        again. Declaring the Type Lock again therefore re-applies it to
        everyone ("lock all"); declaring it with a different Target stores
        the new one, and the Followers still locked to the old Target
        count as skipped.

        Raises ``ValueError`` — before anything is touched — naming every
        offending path when no such Type exists, when ``path`` is not an
        entry of the Type itself (naming the Type that defines it when the
        path only reaches the effective parameter set through a Nested
        Type; own entries only, like
        :meth:`set_type_parameter_default`), when an explicit ``target``
        does not exist as a parameter of this Parameter Manager, and when
        locking one of the Instance parameters would be a self-lock, close
        a cycle (walking Targets regardless of locked/unlocked state, D7)
        or hit a parameter that cannot carry a Lock.

        On success it emits the Globals parameter's ``parameter-creation``
        (when created), then one ``pm-lock-update`` per Lock it created or
        relocked — nothing for skipped or already-locked parameters — and
        finally one ``pm-type-update`` for the edited Type (D10, D22); the
        Types nesting it are not named, since their effective parameter
        set carries units and defining Types, not Targets. A failed
        validation emits nothing.

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the Type's own entry.
        :param target: Path of the Target, relative to this Parameter
            Manager; the default Globals Target when ``None``.
        :return: The skipped Instance parameter paths, in tree order.
        """
        # validate-then-mutate: every check below runs before the entry or
        # any Lock is touched (rule 3)
        entry = self._require_type_entry(type_name, path)
        if target is not None:
            # the explicit Target must be a parameter of this Parameter
            # Manager, resolved like lock() resolves it (D8)
            self._resolve_param(target)
            target_relative = target
        else:
            target_relative = f"_globals.{type_name}.{path}"
        target_full = self._full_path(target_relative)
        # classify every current Instance's parameter at the entry path; an
        # Instance always carries the parameter (D12)
        applications: List[Tuple[str, str]] = []
        skipped: List[Tuple[str, str]] = []
        offenders: List[str] = []
        for instance_path in self.instances_of(type_name):
            param_path = f"{instance_path}.{path}"
            action, locked_to = self._classify_lock_application(
                param_path, target_full
            )
            if action == "skip":
                skipped.append((param_path, locked_to))
                continue
            if action == "none":
                continue
            follower_full = self._full_path(param_path)
            if not isinstance(self.parameter(param_path), ManagedParameter):
                offenders.append(f"{follower_full} cannot carry a Lock")
                continue
            try:
                self._check_lock_allowed(follower_full, target_full)
            except ValueError as exc:
                offenders.append(str(exc))
                continue
            applications.append((param_path, action))
        if offenders:
            raise ValueError(
                f"cannot lock the Instance parameters of Type '{type_name}' "
                f"entry '{path}' to {target_full}: " + "; ".join(offenders)
            )
        # the default Target is the Globals parameter, created on demand;
        # its parameter-creation Broadcast goes out before the Lock updates
        if target is None:
            self._ensure_global_target(type_name, path)
        entry.target = target_full
        # apply the Locks in tree order; each state change emits exactly
        # one pm-lock-update through lock()/relock() (D10)
        for param_path, action in applications:
            if action == "lock":
                self.lock(param_path, target_relative)
            else:
                self.relock(param_path)
        if skipped:
            described = ", ".join(
                f"'{param_path}' (locked to {locked_to})"
                for param_path, locked_to in skipped
            )
            logger.warning(
                f"Type Lock of Type '{type_name}' entry '{path}' to "
                f"{target_full}: skipped Instance parameter(s) {described}, "
                "which carry a Lock on another Target"
            )
        # one pm-type-update for the edited Type, after the Lock updates;
        # the Types nesting it are not named — their effective parameter
        # set carries units and defining Types, not Targets (D22)
        self._broadcast_type_update(type_name)
        return [param_path for param_path, _ in skipped]

    def unlock_type_parameter(self, type_name: str, path: str) -> None:
        """Remove the Type Lock of the entry ``path`` of the Type
        ``type_name`` (D17): only the rule goes — the entry's stored Target
        is cleared and one ``pm-type-update`` Broadcast naming the Type
        goes out — while the Locks the declaration put on the Instance
        parameters stay until they are removed individually with
        :meth:`remove_lock`. Instances that stop matching keep their
        Locks either way.

        Raises ``ValueError`` naming the Type and the path when no such
        Type exists or ``path`` is not an entry of the Type itself; nothing
        is changed then. An entry that carries no Type Lock is a no-op
        logged at INFO level that emits nothing (like :meth:`unlock` and
        :meth:`relock`).

        :param type_name: Name of the Type.
        :param path: Relative parameter path of the Type's own entry.
        """
        entry = self._require_type_entry(type_name, path)
        if entry.target is None:
            logger.info(
                f"the entry '{path}' of Type '{type_name}' carries no Type "
                "Lock; nothing to do"
            )
            return
        entry.target = None
        self._broadcast_type_update(type_name)

    def _apply_type_locks_to_new_instances(
        self, lock_types: List[str], instances_before: Dict[str, List[str]]
    ) -> None:
        """Apply the existing Type Locks of the Types ``lock_types`` to the
        submodules that an edit just turned into new Instances (D17): a
        Parameter Group that is an Instance after the edit but was not one
        before gets a locked Lock on the entry's Target for every entry of
        the Type's effective parameter set that carries one — a parameter
        the edit kept (D14) included, since a Lock changes neither its own
        value nor its unit.

        Per parameter an unlocked Lock remembering the same Target is
        locked again, an already locked one is left as it is, and a Lock
        on another Target is skipped. A Target that no longer exists —
        not reachable through the public API, since
        :meth:`remove_parameter` clears the Type Lock whose stored Target
        it deletes (D18), but possible in a registry inserted by hand — a
        parameter that cannot carry a Lock and one whose Lock application
        would be a self-lock or close a cycle are skipped too — including
        a cycle that another application of the same batch creates, since
        every application is validated again against the state the earlier
        ones left when it runs. No Lock application raises: every
        ``ValueError`` the Lock API raises for one parameter is recorded
        as that parameter's skip reason. Every skip is collected into one
        ``logger.warning`` naming the Type, the entry path, the skipped
        parameter path and the reason; the edit itself still succeeds and
        the calling method keeps returning ``None``. Submodules that were
        Instances before the edit are untouched: only
        :meth:`lock_type_parameter` re-applies a Type Lock to everyone.

        Each applied Lock emits exactly one ``pm-lock-update`` through
        :meth:`lock` / :meth:`relock` (D10); the caller runs this after
        the ``parameter-creation`` Broadcasts and before the
        ``pm-type-update`` Broadcasts.

        :param lock_types: Names of the Types whose Type Locks are applied,
            the edited Type and the Types nesting it (and, for
            :meth:`add_nested_type`, the Nested Type and the Types nesting
            it).
        :param instances_before: The Instances of every Type in
            ``lock_types``, computed before the edit (see
            :meth:`_instances_before_edit`).
        """
        applications: List[Tuple[str, str, str, str, bool]] = []
        skipped: List[Tuple[str, str, str, str]] = []
        seen: set = set()
        for type_name in lock_types:
            locked_entries = {
                entry_path: entry
                for entry_path, entry in self._effective_entries(type_name).items()
                if entry.target is not None
            }
            if not locked_entries:
                continue
            for instance_path in self.instances_of(type_name):
                if instance_path in instances_before.get(type_name, []):
                    # an Instance before the edit: only lock_type_parameter
                    # re-applies a Type Lock to everyone
                    continue
                for entry_path, entry in locked_entries.items():
                    param_path = f"{instance_path}.{entry_path}"
                    if param_path in seen:
                        # the same defining entry reaches the parameter
                        # through several Types of the closure
                        continue
                    seen.add(param_path)
                    if self._param_by_full_path(entry.target) is None:
                        skipped.append(
                            (
                                type_name,
                                entry_path,
                                param_path,
                                f"the stored Target {entry.target} does "
                                "not exist",
                            )
                        )
                        continue
                    action, locked_to = self._classify_lock_application(
                        param_path, entry.target
                    )
                    if action == "skip":
                        skipped.append(
                            (
                                type_name,
                                entry_path,
                                param_path,
                                "it carries a Lock on another Target "
                                f"({locked_to})",
                            )
                        )
                        continue
                    if action == "none":
                        continue
                    param = self.parameter(param_path)
                    follower_full = self._full_path(param_path)
                    if not isinstance(param, ManagedParameter):
                        skipped.append(
                            (
                                type_name,
                                entry_path,
                                param_path,
                                f"{follower_full} cannot carry a Lock",
                            )
                        )
                        continue
                    try:
                        self._check_lock_allowed(follower_full, entry.target)
                    except ValueError as exc:
                        skipped.append(
                            (type_name, entry_path, param_path, str(exc))
                        )
                        continue
                    applications.append(
                        (
                            type_name,
                            entry_path,
                            param_path,
                            entry.target[len(self.name) + 1:],
                            action == "relock",
                        )
                    )
        for (
            type_name,
            entry_path,
            param_path,
            target_relative,
            is_relock,
        ) in applications:
            try:
                if is_relock:
                    self.relock(param_path)
                else:
                    self.lock(param_path, target_relative)
            except ValueError as exc:
                # the earlier applications of this batch changed the Lock
                # state the up-front classification validated against: the
                # Lock API refused this one, so it is skipped like any
                # other application that cannot run — the edit itself
                # still succeeds and no exception escapes
                skipped.append((type_name, entry_path, param_path, str(exc)))
        if skipped:
            described = "; ".join(
                f"'{param_path}' (entry '{entry_path}' of Type "
                f"'{type_name}') {reason}"
                for type_name, entry_path, param_path, reason in skipped
            )
            logger.warning(
                "skipped Instance parameter(s) while applying the Type "
                f"Locks to new Instances: {described}"
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
        """Load parameters, Types and Locks from a parameter json file
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
        """Load parameters, Types and Locks from a parameter dictionary
        (see :mod:`.serialize`).

        A dictionary without a top-level ``version`` key is the legacy flat
        parameter map and loads exactly as before: parameters only, and the
        Types and Locks of this Parameter Manager are untouched by the
        legacy reader.

        A version-2 profile document (the document :meth:`toParamDict`
        writes, plan decision D19) is validated as a whole before anything
        is loaded (plan decision D20). The schema is checked with
        :func:`serialize.validateParameterManagerV2`; every remaining
        problem is collected into one ``ValueError`` naming all of them
        (rule 3): every file key must belong to this Parameter Manager
        (the full-path form with the instrument name), every Type name
        must be valid (non-empty, not the reserved Globals name
        ``_globals``), every Nested Type must name a Type of the document,
        the document's Types must form no Nested Type cycle and hold no
        effective parameter path twice, every ``lock`` Target and every
        non-null Type Lock Target must be a ``parameters`` key of the
        document, and no ``lock`` may be a self-lock or close a cycle
        among the document's Locks (walking Targets regardless of
        locked/unlocked state, D7). A refused document changes nothing and
        emits nothing. Any other ``version`` value raises ``ValueError``
        naming it.

        After the validation the document loads in order (D20): first the
        Locks of every parameter it lists go away, so setting a stored own
        value on a currently locked Follower cannot raise (D6); then the
        parameters with the semantics the reader always had (an existing
        one is set to its stored own value and unit, a missing one is
        created — one under the Globals submodule through the internal
        creation path :meth:`_create_managed_parameter`, since the public
        :meth:`add_parameter` refuses the Globals name (D18) — and
        ``deleteMissing=True`` removes the parameters the document does
        not list, dropping their Locks and Type Locks exactly like
        :meth:`remove_parameter` does); then the Types, written straight
        into the registry as definitions — with ``deleteMissing=True``,
        every Type the document does not define is removed — with **no**
        Instance side effects (D20): no parameter is created for an
        Instance and no Type Lock is applied on load, so a partial
        Instance stays partial and an Instance's Locks come only from the
        document's ``lock`` entries; then the Locks, each set directly to
        the stored full-form Target and stored locked state (like
        :meth:`lock` creates it after the cycle check, not through a
        ``lock()``/``unlock()`` pair). A parameter the document lists
        without a ``lock`` entry ends with no Lock; parameters it does not
        list keep theirs when ``deleteMissing=False``.

        The Broadcasts go out once, after the whole load succeeded (D22,
        D10): one ``pm-type-update`` per Type the document wrote, then one
        with a ``None`` payload per Type removed, then one
        ``pm-lock-update`` per Lock that ended different from before the
        load (``None`` when it was removed), in tree order. The load
        emits nothing for the parameter values it sets, and it re-emits
        **no** ``parameter-creation``/``parameter-deletion`` Broadcasts
        for the parameters it creates and removes: the Server's
        literal-name detection does not see them either, so a GUI watching
        this Parameter Manager must refresh its structure after a profile
        load.

        :param paramDict: Parameter dictionary — a legacy flat map or a
            version-2 profile document.
        :param deleteMissing: If ``True``, delete parameters currently in
            the ParameterManager that are not listed in the file, and
            remove the Types the file does not define.
        """
        if "version" in paramDict:
            version = paramDict["version"]
            if version != 2:
                raise ValueError(
                    f"unsupported Parameter Manager profile version: "
                    f"{version!r} (this reader reads version 2 and the "
                    "legacy flat map, which carries no version key)"
                )
            self._load_v2_document(paramDict, deleteMissing)
            return

        # legacy flat parameter map: exactly the behaviour before the
        # version-2 profile document existed
        serialize.validateParamDict(paramDict)
        simple = serialize.isSimpleFormat(paramDict)

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

            elif pn.startswith("_globals."):
                # the public add_parameter refuses the Globals name (D18);
                # a saved Globals parameter round-trips through the
                # internal creation path
                self._create_managed_parameter(pn, val, unit)

            else:
                self.add_parameter(pn, initial_value=val, unit=unit)

        for pn in currentParams:
            if pn not in fileParams and deleteMissing:
                self.remove_parameter(pn)

    def _collect_v2_document_problems(self, document: Dict[str, Any]) -> List[str]:
        """Collect every validation problem of a version-2 profile
        document into one list of messages, so a refused document can be
        named in full (rule 3, D20). The schema leg has already run when
        this is called; nothing here changes any state."""
        problems: List[str] = []
        parameters = document["parameters"]
        document_types = document["types"]
        prefix = f"{self.name}."

        # every file key belongs to this Parameter Manager: the full
        # dotted form with the instrument name, like the writer stores it
        for key in parameters:
            if not key.startswith(prefix):
                problems.append(
                    f"parameter key '{key}' does not belong to this "
                    f"Parameter Manager ('{self.name}')"
                )

        # every Type name is valid: non-empty, not the reserved Globals
        # submodule name (D18)
        for type_name in document_types:
            if type_name == "_globals":
                problems.append(
                    f"'{type_name}' is not a valid Type name: "
                    "the Globals submodule name is reserved"
                )
            elif not type_name:
                problems.append("'' is not a valid Type name: it is empty")

        # the candidate registry built from the document, the way
        # add_nested_type validates a candidate: the expansion helpers run
        # on it without touching the real registry
        candidates = {
            type_name: _TypeDefinition(
                name=type_name,
                parameters={
                    path: _TypeEntry(
                        default=entry["default"],
                        unit=entry["unit"],
                        target=entry["target"],
                    )
                    for path, entry in spec["parameters"].items()
                },
                nested=dict(spec["nested"]),
            )
            for type_name, spec in document_types.items()
        }

        # every Nested Type names a Type of the document
        for type_name, definition in candidates.items():
            for nested_name in definition.nested.values():
                if nested_name not in candidates:
                    problems.append(
                        f"Type '{type_name}' nests '{nested_name}', which "
                        "is not among the document's Types"
                    )

        def closure_complete(name: str) -> bool:
            seen: set = set()
            stack = [name]
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                candidate = candidates.get(current)
                if candidate is None:
                    return False
                stack.extend(candidate.nested.values())
            return True

        # no Nested Type cycle and no effective path twice, per the
        # expansion helpers on the candidate registry; Types whose Nested
        # Type closure the document does not define completely are skipped,
        # the missing names are reported above
        reported: set = set()
        for type_name in candidates:
            if not closure_complete(type_name):
                continue
            try:
                self._expand_effective(type_name, types=candidates)
            except ValueError as exc:
                message = str(exc)
                if message not in reported:
                    reported.add(message)
                    problems.append(message)

        # every Lock Target and every non-null Type Lock Target is a
        # parameters key of the document (D20); every missing Target is
        # named with everything that refers to it
        missing_targets: Dict[str, List[str]] = {}
        for key, entry in parameters.items():
            lock = entry.get("lock")
            if lock is not None and lock["target"] not in parameters:
                missing_targets.setdefault(lock["target"], []).append(
                    f"the Lock on Follower '{key}'"
                )
        for type_name, spec in document_types.items():
            for path, entry in spec["parameters"].items():
                target = entry["target"]
                if target is not None and target not in parameters:
                    missing_targets.setdefault(target, []).append(
                        f"the Type Lock on '{type_name}.{path}'"
                    )
        for target, referees in missing_targets.items():
            problems.append(
                f"Target '{target}' is not a parameter of the document: "
                f"referred to by {', '.join(referees)}"
            )

        # no self-lock and no cycle among the document's Locks: the walk
        # follows each Target's Lock within the document regardless of
        # locked/unlocked state (D7)
        document_locks = {
            key: entry["lock"]
            for key, entry in parameters.items()
            if "lock" in entry
        }
        for follower_full, lock in document_locks.items():
            target_full = lock["target"]
            if target_full == follower_full:
                problems.append(f"cannot lock {follower_full} to itself")
                continue
            chain = [target_full]
            seen = {target_full}
            current = target_full
            while True:
                next_lock = document_locks.get(current)
                if next_lock is None:
                    break
                nxt = next_lock["target"]
                if nxt == follower_full or nxt in seen:
                    problems.append(
                        f"cannot lock {follower_full} to {target_full}: "
                        f"cycle in Lock targets: {' -> '.join(chain + [nxt])}"
                    )
                    break
                seen.add(nxt)
                chain.append(nxt)
                current = nxt

        return problems

    def _load_v2_document(self, document: Dict[str, Any], deleteMissing: bool) -> None:
        """Validate a version-2 profile document as a whole and load it in
        D20's order: the Locks of the listed parameters, the parameters,
        the Types without Instance side effects, the Locks — and emit the
        load's Broadcasts once, after it succeeded (D22, D10)."""
        serialize.validateParameterManagerV2(document)
        problems = self._collect_v2_document_problems(document)
        if problems:
            raise ValueError(
                "invalid version-2 Parameter Manager profile document: "
                + "; ".join(problems)
            )

        parameters = document["parameters"]
        document_types = document["types"]
        file_params = [key[len(self.name) + 1 :] for key in parameters]
        file_param_set = set(file_params)
        # the pre-load Lock state, for the diff the load reports at the end
        previous_locks = self.list_locks()

        # The methods reused below announce their own state changes
        # (remove_parameter drops Locks and clears Type Locks with one
        # Broadcast each, D10/D22). The load reports the whole transition
        # itself, once, after it succeeded, so the reused methods run with
        # the sinks detached; the sinks are back before the load's own
        # Broadcasts go out.
        saved_sinks = self._broadcast_sinks
        self._broadcast_sinks = []
        try:
            # (a) the Locks of every parameter the document lists go
            # first: setting a stored own value on a currently locked
            # Follower would raise otherwise (D6); the Locks are
            # re-created from the document in step (d)
            for pn in file_params:
                if self.has_param(pn):
                    param = self.parameter(pn)
                    if isinstance(param, ManagedParameter) and param.lock is not None:
                        param.lock = None
                        param._target = None

            # (b) the parameters, with the semantics the reader always had
            current_params = self.list()
            for pn in file_params:
                entry = parameters[f"{self.name}.{pn}"]
                val = entry["value"]
                unit = entry.get("unit", "")

                if self.has_param(pn):
                    self.parameter(pn)(val)
                    if unit is not None:
                        param = self.parameter(pn)
                        assert hasattr(param, "unit")
                        param.unit = unit

                elif pn.startswith("_globals."):
                    # the public add_parameter refuses the Globals name
                    # (D18); a saved Globals parameter round-trips through
                    # the internal creation path
                    self._create_managed_parameter(pn, val, unit)

                else:
                    self.add_parameter(pn, initial_value=val, unit=unit)

            if deleteMissing:
                for pn in current_params:
                    if pn not in file_param_set:
                        self.remove_parameter(pn)

            # (c) the Types, written straight into the registry with no
            # Instance side effects (D20): no parameter is created for an
            # Instance and no Type Lock is applied on load
            written_types: List[str] = []
            removed_types: List[str] = []
            if deleteMissing:
                for type_name in list(self._types):
                    if type_name not in document_types:
                        del self._types[type_name]
                        removed_types.append(type_name)
            for type_name, spec in document_types.items():
                self._types[type_name] = _TypeDefinition(
                    name=type_name,
                    parameters={
                        path: _TypeEntry(
                            default=entry["default"],
                            unit=entry["unit"],
                            target=entry["target"],
                        )
                        for path, entry in spec["parameters"].items()
                    },
                    nested=dict(spec["nested"]),
                )
                written_types.append(type_name)

            # (d) the Locks, each set directly to the stored full-form
            # Target and stored locked state — like lock() creates it
            # after the cycle check, not through a lock()/unlock() pair
            for pn in file_params:
                lock_entry = parameters[f"{self.name}.{pn}"].get("lock")
                if lock_entry is None:
                    continue
                param = self.parameter(pn)
                if not isinstance(param, ManagedParameter):
                    raise ValueError(f"{self._full_path(pn)} cannot carry a Lock")
                follower_full = self._full_path(pn)
                target_full = lock_entry["target"]
                self._check_lock_allowed(follower_full, target_full)
                target_param = self._param_by_full_path(target_full)
                assert target_param is not None, (
                    "the validated Target is not a parameter of this "
                    "Parameter Manager"
                )
                param._target = target_param
                param.lock = PMLockBluePrint(
                    target=target_full, locked=lock_entry["locked"]
                )
        finally:
            self._broadcast_sinks = saved_sinks

        # the load's Broadcasts, after the whole load succeeded (D22,
        # D10): one pm-type-update per Type written, one with a None
        # payload per Type removed, then one pm-lock-update per Lock that
        # ended different from before the load, in tree order. Values set
        # during the load and the created and removed parameters emit
        # nothing (see fromParamDict).
        for type_name in written_types:
            self._broadcast_type_update(type_name)
        for type_name in removed_types:
            self.broadcast(
                ParameterBroadcastBluePrint(
                    name=f"{self.name}.{type_name}",
                    action=PM_TYPE_UPDATE,
                    value=None,
                )
            )
        after_locks = self.list_locks()
        tree_paths = [rel_path for rel_path, _ in self._iter_params()]
        tree_set = set(tree_paths)
        ordered_paths = [
            rel_path
            for rel_path in tree_paths
            if rel_path in previous_locks or rel_path in after_locks
        ]
        # a Follower whose parameter the load removed is no longer in the
        # tree; its Lock still ended removed and is reported last
        ordered_paths += [
            rel_path for rel_path in previous_locks if rel_path not in tree_set
        ]
        for rel_path in ordered_paths:
            before = previous_locks.get(rel_path)
            after = after_locks.get(rel_path)
            if before != after:
                self._broadcast_lock_update(rel_path, after)

    def toParamDict(
        self, simpleFormat: bool = False, includeMeta: List[str] = ["unit"]
    ) -> Dict[str, Any]:
        """Return the state of this Parameter Manager as a version-2
        profile document (plan decision D19):
        ``{"version": 2, "parameters": {...}, "types": {...}}``.

        ``parameters`` maps every parameter's full dotted path (with the
        instrument name, like the legacy flat files) to a dict holding the
        parameter's **own** value — :meth:`ManagedParameter.own_value`
        for the parameters that can carry a Lock, so a locked Follower
        saves its own value and never the Target's (ADR-0002), the cached
        snapshot value for any plain ``Parameter`` — the metadata
        ``includeMeta`` selects (``unit`` by default; Globals parameters
        are saved like any other, D18), and, only on a parameter that
        carries a Lock in either state, a ``lock`` entry
        ``{"target": <full dotted Target path>, "locked": <bool>}``.

        ``types`` maps every Type of the Type registry to its own entries
        as ``{path: {"default": ..., "unit": ..., "target": ...}}`` — the
        stored full-form Target of the entry's Type Lock, or ``None`` —
        and its Nested Types as ``{submodule: type}``; with no Types it is
        ``{}``.

        The values are read from the qcodes snapshot with ``update=False``
        (the cache, never ``get``), like the legacy writer this replaces.

        ``simpleFormat`` is kept for signature compatibility but has no
        effect: a version-2 document always stores the per-parameter
        dict. ``includeMeta`` still selects the per-parameter metadata
        besides ``value``.

        :param simpleFormat: Ignored (kept for signature compatibility).
        :param includeMeta: List of parameter attributes to include
            besides value. All keys occurring in snapshots are valid.
        :return: The version-2 profile document.
        """
        params = serialize.toParamDict(
            [self], simpleFormat=False, includeMeta=includeMeta
        )
        for rel_path, param in self._iter_params():
            full_path = self._full_path(rel_path)
            if full_path not in params:
                continue
            if isinstance(param, ManagedParameter):
                # the snapshot of a locked Follower reports the Target's
                # value (ADR-0002); the profile stores the own value, so
                # unlocking exposes it again
                params[full_path]["value"] = param.own_value()
            lock = getattr(param, "lock", None)
            if lock is not None:
                params[full_path]["lock"] = {
                    "target": lock.target,
                    "locked": lock.locked,
                }
        return {
            "version": 2,
            "parameters": params,
            "types": {
                type_name: {
                    "parameters": {
                        path: {
                            "default": entry.default,
                            "unit": entry.unit,
                            "target": entry.target,
                        }
                        for path, entry in definition.parameters.items()
                    },
                    "nested": dict(definition.nested),
                }
                for type_name, definition in self._types.items()
            },
        }

    def toFile(
        self,
        filePath: str | None = None,
        name: str | None = None,
    ) -> None:
        """Save parameters from the instrument into a json file.
        The file holds the version-2 profile document :meth:`toParamDict`
        returns (plan decision D19), dumped with ``indent=2, sort_keys=True``.
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
