"""Tests for the Type registry and definitions (plan task 2.1), the
duck-typed Instance matching (plan task 2.2), the Type edits with
Instance side effects (plan task 2.3), ``add_instance`` (plan task 2.4)
and the ``pm-type-update`` and side-effect creation Broadcasts (plan task
2.5).

The definition and editing methods are exercised through the public API:
``add_type`` / ``add_type_parameter`` / ``add_nested_type`` and friends.
The states the public API refuses to build — Nested Type cycles, Nested
Types missing from the registry, effective sets with a duplicated path —
are still inserted into the registry by hand with the ``put_type``
helper.
Covered: creating, listing, getting and removing Types (with the
reserved Globals name and duplicate-name refusals), the effective
parameter set expansion of Nested Types (cycle refusal, collision
refusal), the content of the ``PMTypeBluePrint`` ``get_type`` returns,
its round-trip through the blueprint serialization, the Instance matching
queries ``instances_of`` and ``types_of`` (existence and unit, any depth,
never the root, never the Globals submodule, ordering of the claiming
Types), the six editing methods with their D13 Instance side effects, and
``add_instance`` (creating the missing effective entries with defaults
and units, keeping existing ones with value and unit, dotted names, the
three-tier Type of the mock, the up-front unit-conflict scan, blocked
targets, the Globals refusal, unknown and empty Types) — every refusal
leaving the registry and the parameter tree byte-identical.
The Broadcast part checks, on a local Parameter Manager with a sink, that
every Type-editing method emits ``pm-type-update`` (one per affected
Type, the edited one first; ``None`` on ``remove_type``) after the
mutation, that the parameters created as side effects are re-emitted as
``parameter-creation`` in creation order before the Type updates, and
that read-only queries and refused calls emit nothing. The last part
exercises the Type API through a client proxy against a live Server:
every method callable over the wire, ``get_type``/``list_types``
deserialising, and a SubClient receiving ``pm-type-update`` and the
per-parameter ``parameter-creation`` Broadcasts of an ``add_instance``
issued from a second client, whose creations the first client's proxy
shows after ``update()``.
"""

import copy
import re

import pytest

from instrumentserver.blueprints import (
    PARAMETER_CREATION,
    PM_TYPE_UPDATE,
    ParameterBroadcastBluePrint,
    PMTypeBluePrint,
    deserialize_obj,
)
from instrumentserver.client.proxy import Client
from instrumentserver.params import (
    ManagedParameter,
    ParameterManager,
    _TypeDefinition,
    _TypeEntry,
)


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """A fresh Parameter Manager in an empty working directory."""
    monkeypatch.chdir(tmp_path)
    return ParameterManager(name="parameter_manager")


def put_type(pm, name, parameters=None, nested=None):
    """Insert a ``_TypeDefinition`` into the registry directly: for the
    states the public editing API refuses to build (Nested Type cycles,
    missing Nested Types, effective sets with a duplicated path)."""
    pm._types[name] = _TypeDefinition(
        name=name,
        parameters={
            path: _TypeEntry(**entry) for path, entry in (parameters or {}).items()
        },
        nested=dict(nested or {}),
    )


def put_three_tier_registry(pm):
    """The mock's three-tier case: ``qubit`` nests ``readout`` at its
    submodule ``readout``, which nests ``pulse_window`` at its submodule
    ``pw``."""
    pm.add_type("pulse_window")
    pm.add_type_parameter("pulse_window", "duration", default=None, unit="s")
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type_parameter("readout", "window", default=None, unit="s")
    pm.add_nested_type("readout", "pw", "pulse_window")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_nested_type("qubit", "readout", "readout")


# ---------------------------------------------------------------------------
# Definitions: add_type, list_types, remove_type
# ---------------------------------------------------------------------------


def test_add_type_creates_an_empty_type(pm):
    pm.add_type("qubit")

    assert pm.list_types() == ["qubit"]
    bp = pm.get_type("qubit")
    assert bp.name == "qubit"
    assert bp.parameters == {}
    assert bp.nested == {}
    # an empty Type has no effective paths and no Instances
    assert bp.effective == {}


def test_add_type_refuses_the_reserved_globals_name(pm):
    with pytest.raises(ValueError, match="'_globals' is not a valid Type name"):
        pm.add_type("_globals")

    assert pm.list_types() == []


def test_the_type_registry_lives_on_the_root_only(pm):
    pm.add_parameter("q01.IF")

    assert hasattr(pm, "_types")
    # the Parameter Group q01 carries no registry and no Type methods (D15)
    assert not hasattr(pm.q01, "_types")
    assert not hasattr(pm.q01, "add_type")


def test_add_type_refuses_a_duplicate_name_and_changes_nothing(pm):
    pm.add_type("qubit")

    with pytest.raises(ValueError, match="a Type named 'qubit' already exists"):
        pm.add_type("qubit")

    # the refused call left the original Type untouched
    assert pm.list_types() == ["qubit"]
    assert pm.get_type("qubit").parameters == {}


def test_list_types_lists_every_type(pm):
    assert pm.list_types() == []

    pm.add_type("qubit")
    pm.add_type("readout")

    assert sorted(pm.list_types()) == ["qubit", "readout"]


def test_remove_type_removes_the_type(pm):
    pm.add_type("qubit")
    pm.add_type("readout")

    pm.remove_type("qubit")

    assert pm.list_types() == ["readout"]
    with pytest.raises(ValueError, match="no Type named 'qubit' exists"):
        pm.get_type("qubit")


def test_remove_type_with_an_unknown_name_raises_naming_it(pm):
    with pytest.raises(ValueError, match="no Type named 'qubit' exists"):
        pm.remove_type("qubit")

    assert pm.list_types() == []


def test_remove_type_refused_while_nested_in_another_type(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape("cannot remove Type 'readout': nested in Type(s) 'qubit'"),
    ):
        pm.remove_type("readout")

    # the refused removal left both Types in the registry, untouched
    assert sorted(pm.list_types()) == ["qubit", "readout"]
    assert pm.get_type("readout").parameters == {
        "IF": {"default": None, "unit": "Hz", "target": None}
    }


def test_remove_type_names_every_type_nesting_it(pm):
    pm.add_type("readout")
    pm.add_type("qubit")
    pm.add_type("qubit2")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_nested_type("qubit2", "readout", "readout")

    with pytest.raises(ValueError) as excinfo:
        pm.remove_type("readout")

    # every offending Type, not the first (rule 3)
    assert str(excinfo.value) == (
        "cannot remove Type 'readout': nested in Type(s) 'qubit', 'qubit2'"
    )
    assert sorted(pm.list_types()) == ["qubit", "qubit2", "readout"]


def test_remove_type_removes_a_type_that_nests_other_types(pm):
    # qubit nests readout but is nested by nobody: removing it is allowed,
    # and the Nested Type readout stays in the registry untouched
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    pm.remove_type("qubit")

    assert pm.list_types() == ["readout"]
    assert pm.get_type("readout").parameters == {
        "IF": {"default": None, "unit": "Hz", "target": None}
    }


def test_get_type_with_an_unknown_name_raises_naming_it(pm):
    with pytest.raises(ValueError, match="no Type named 'qubit' exists"):
        pm.get_type("qubit")


# ---------------------------------------------------------------------------
# Effective set: _effective_parameters
# ---------------------------------------------------------------------------


def test_effective_set_expands_nested_types_recursively(pm):
    put_three_tier_registry(pm)

    assert pm._effective_parameters("qubit") == {
        "IF": {"unit": "Hz", "from_type": "qubit"},
        "octave_gain": {"unit": "dB", "from_type": "qubit"},
        "readout.IF": {"unit": "Hz", "from_type": "readout"},
        "readout.window": {"unit": "s", "from_type": "readout"},
        "readout.pw.duration": {"unit": "s", "from_type": "pulse_window"},
    }


def test_effective_set_of_the_middle_tier(pm):
    put_three_tier_registry(pm)

    assert pm._effective_parameters("readout") == {
        "IF": {"unit": "Hz", "from_type": "readout"},
        "window": {"unit": "s", "from_type": "readout"},
        "pw.duration": {"unit": "s", "from_type": "pulse_window"},
    }


def test_the_same_type_nested_twice_is_not_a_cycle(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "ro1", "readout")
    pm.add_nested_type("qubit", "ro2", "readout")

    assert pm._effective_parameters("qubit") == {
        "ro1.IF": {"unit": "Hz", "from_type": "readout"},
        "ro2.IF": {"unit": "Hz", "from_type": "readout"},
    }


def test_effective_set_refuses_a_cycle(pm):
    put_type(pm, "qubit", nested={"readout": "readout"})
    put_type(pm, "readout", nested={"qubit": "qubit"})

    with pytest.raises(
        ValueError,
        match=re.escape("cycle in nested Types: qubit -> readout -> qubit"),
    ):
        pm._effective_parameters("qubit")

    # get_type expands the effective set too, so it refuses the cycle as
    # well, walking from its own Type
    with pytest.raises(
        ValueError,
        match=re.escape("cycle in nested Types: readout -> qubit -> readout"),
    ):
        pm.get_type("readout")


def test_effective_set_refuses_a_type_nested_in_itself(pm):
    put_type(pm, "loop", nested={"self": "loop"})

    with pytest.raises(
        ValueError, match=re.escape("cycle in nested Types: loop -> loop")
    ):
        pm._effective_parameters("loop")


def test_effective_set_refuses_a_nested_type_missing_from_the_registry(pm):
    put_type(pm, "qubit", nested={"readout": "readout"})

    with pytest.raises(
        ValueError,
        match=re.escape("Type 'qubit' nests 'readout', which does not exist"),
    ):
        pm._effective_parameters("qubit")


def test_effective_set_refuses_a_duplicated_path_and_names_it(pm):
    # the Type's own entry "readout.IF" collides with the entry "IF" of
    # the Nested Type required at the submodule "readout"
    put_type(
        pm,
        "qubit",
        parameters={"readout.IF": {"default": None, "unit": "Hz"}},
        nested={"readout": "readout"},
    )
    put_type(pm, "readout", parameters={"IF": {"default": None, "unit": "Hz"}})

    with pytest.raises(
        ValueError,
        match=re.escape(
            "parameter path(s) 'readout.IF' appear more than once in the "
            "effective set of Type 'qubit'"
        ),
    ):
        pm._effective_parameters("qubit")


def test_effective_set_names_every_duplicated_path(pm):
    put_type(
        pm,
        "qubit",
        parameters={
            "readout.IF": {"default": None, "unit": "Hz"},
            "readout.window": {"default": None, "unit": "s"},
        },
        nested={"readout": "readout"},
    )
    put_type(
        pm,
        "readout",
        parameters={
            "IF": {"default": None, "unit": "Hz"},
            "window": {"default": None, "unit": "s"},
        },
    )

    with pytest.raises(ValueError) as excinfo:
        pm._effective_parameters("qubit")

    # every offending path, not the first (rule 3)
    message = str(excinfo.value)
    assert "parameter path(s) 'readout.IF', 'readout.window' appear more than once" in message
    assert message.endswith("effective set of Type 'qubit'")


# ---------------------------------------------------------------------------
# Blueprint content: get_type and PMTypeBluePrint
# ---------------------------------------------------------------------------


def test_get_type_returns_the_full_blueprint(pm):
    put_three_tier_registry(pm)

    bp = pm.get_type("qubit")

    assert isinstance(bp, PMTypeBluePrint)
    assert bp.name == "qubit"
    assert bp.parameters == {
        "IF": {"default": None, "unit": "Hz", "target": None},
        "octave_gain": {"default": 10, "unit": "dB", "target": None},
    }
    assert bp.nested == {"readout": "readout"}
    assert bp.effective == {
        "IF": {"unit": "Hz", "from_type": "qubit"},
        "octave_gain": {"unit": "dB", "from_type": "qubit"},
        "readout.IF": {"unit": "Hz", "from_type": "readout"},
        "readout.window": {"unit": "s", "from_type": "readout"},
        "readout.pw.duration": {"unit": "s", "from_type": "pulse_window"},
    }


def test_pm_type_blueprint_round_trips_through_serialization():
    bp = PMTypeBluePrint(
        name="qubit",
        parameters={
            "IF": {"default": None, "unit": "Hz", "target": None},
            "octave_gain": {"default": 10, "unit": "dB", "target": None},
        },
        nested={"readout": "readout"},
        effective={
            "IF": {"unit": "Hz", "from_type": "qubit"},
            "octave_gain": {"unit": "dB", "from_type": "qubit"},
        },
    )

    round_tripped = deserialize_obj(bp.toJson())

    assert isinstance(round_tripped, PMTypeBluePrint)
    assert round_tripped == bp


# ---------------------------------------------------------------------------
# Instance matching: instances_of and types_of (plan task 2.2)
# ---------------------------------------------------------------------------


def put_three_tier_tree(pm):
    """The parameter tree matching the three-tier registry: ``q01`` is an
    Instance of ``qubit``, ``q01.readout`` of ``readout``, and
    ``q01.readout.pw`` of ``pulse_window``. Every parameter carries a
    value of its own, which matching must ignore."""
    pm.add_parameter("q01.IF", initial_value=5e9, unit="Hz")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")
    pm.add_parameter("q01.readout.IF", initial_value=10e6, unit="Hz")
    pm.add_parameter("q01.readout.window", initial_value=2e-6, unit="s")
    pm.add_parameter("q01.readout.pw.duration", initial_value=500e-9, unit="s")


def put_globals_parameter(pm, path, unit=""):
    """Create a parameter under the reserved Globals submodule the way the
    internal default-Target helper will (the public ``add_parameter``
    refuses Globals from plan task 3.1 on)."""
    parent = pm._get_parent(path, create_parent=True)
    parent._add_own_parameter(path.split(".")[-1], unit=unit)


def test_instances_of_finds_the_three_tier_instances(pm):
    put_three_tier_registry(pm)
    put_three_tier_tree(pm)

    assert pm.instances_of("qubit") == ["q01"]
    assert pm.instances_of("readout") == ["q01.readout"]
    assert pm.instances_of("pulse_window") == ["q01.readout.pw"]


def test_types_of_orders_innermost_first(pm):
    put_three_tier_registry(pm)
    put_three_tier_tree(pm)

    # the deepest Instance claims first: pulse_window (1 effective path)
    # before readout (3) before qubit (5)
    assert pm.types_of("q01.readout.pw.duration") == [
        "pulse_window",
        "readout",
        "qubit",
    ]
    assert pm.types_of("q01.readout.IF") == ["readout", "qubit"]
    assert pm.types_of("q01.IF") == ["qubit"]
    assert pm.types_of("q01.octave_gain") == ["qubit"]


def test_a_type_claiming_through_two_instances_is_ordered_by_its_innermost_instance(pm):
    # one Type claiming a parameter through more than one Instance is
    # listed once, ordered by its innermost Instance
    pm.add_type("zzz")
    pm.add_type_parameter("zzz", "x", default=None, unit="Hz")
    pm.add_type_parameter("zzz", "a.x", default=None, unit="Hz")
    pm.add_type("aaa")
    pm.add_type_parameter("aaa", "a.x", default=None, unit="Hz")
    pm.add_type_parameter("aaa", "top", default=None, unit="s")
    pm.add_parameter("a.x", unit="Hz")
    pm.add_parameter("a.top", unit="s")
    pm.add_parameter("a.a.x", unit="Hz")
    pm.add_parameter("a.a.a.x", unit="Hz")

    # both a and a.a carry the whole zzz shape (x and a.x with unit Hz)
    assert pm.instances_of("zzz") == ["a", "a.a"]
    # aaa is carried by a alone (a.a lacks a.top)
    assert pm.instances_of("aaa") == ["a"]
    # zzz claims a.a.x through a.a (innermost) and through a; aaa claims
    # it only through a: the innermost Instance puts zzz first, although
    # the Type-name tie-break alone would put aaa first
    assert pm.types_of("a.a.x") == ["zzz", "aaa"]


def test_q01_readout_is_an_instance_of_readout_on_its_own(pm):
    # the parent carries only the readout shape, not the full qubit shape:
    # the nested Parameter Group matches readout regardless of its parent
    put_three_tier_registry(pm)
    pm.add_parameter("q02.readout.IF", initial_value=10e6, unit="Hz")
    pm.add_parameter("q02.readout.window", initial_value=2e-6, unit="s")
    pm.add_parameter("q02.readout.pw.duration", initial_value=500e-9, unit="s")

    assert pm.instances_of("readout") == ["q02.readout"]
    assert pm.instances_of("qubit") == []
    assert pm.types_of("q02.readout.IF") == ["readout"]


def test_a_unit_mismatch_excludes_the_submodule(pm):
    # every effective path exists, but octave_gain carries the wrong unit:
    # a match requires existence and unit (D12), so the whole submodule is
    # no Instance
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.IF", unit="Hz")
    pm.add_parameter("q01.octave_gain", unit="Hz")

    assert pm.instances_of("qubit") == []
    assert pm.types_of("q01.IF") == []


def test_a_unit_mismatch_at_one_level_leaves_the_deeper_instances(pm):
    # q03.readout.window carries the wrong unit: neither q03 (for qubit)
    # nor q03.readout (for readout) matches, but q03.readout.pw still
    # matches pulse_window on its own
    put_three_tier_registry(pm)
    pm.add_parameter("q03.IF", unit="Hz")
    pm.add_parameter("q03.octave_gain", unit="dB")
    pm.add_parameter("q03.readout.IF", unit="Hz")
    pm.add_parameter("q03.readout.window", unit="Hz")
    pm.add_parameter("q03.readout.pw.duration", unit="s")

    assert pm.instances_of("qubit") == []
    assert pm.instances_of("readout") == []
    assert pm.instances_of("pulse_window") == ["q03.readout.pw"]
    assert pm.types_of("q03.readout.pw.duration") == ["pulse_window"]


def test_extra_parameters_do_not_matter(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_parameter("q01.IF", unit="Hz")
    # extra parameters and extra Parameter Groups change nothing
    pm.add_parameter("q01.extra", unit="dB")
    pm.add_parameter("q01.sub.extra", unit="s")

    assert pm.instances_of("qubit") == ["q01"]
    assert pm.types_of("q01.IF") == ["qubit"]


def test_two_types_on_one_submodule(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type_parameter("readout", "window", default=None, unit="s")
    pm.add_type("ro_small")
    pm.add_type_parameter("ro_small", "IF", default=None, unit="Hz")
    pm.add_parameter("q01.readout.IF", unit="Hz")
    pm.add_parameter("q01.readout.window", unit="s")

    # one submodule can be an Instance of several Types at once
    assert pm.instances_of("readout") == ["q01.readout"]
    assert pm.instances_of("ro_small") == ["q01.readout"]
    # the same Instance claims both, so the larger effective set wins (D16)
    assert pm.types_of("q01.readout.IF") == ["readout", "ro_small"]


def test_types_of_breaks_a_tie_by_type_name(pm):
    # two Types of the same size on the same Instance: the order falls
    # back to the Type name (the registry holds ro_b first)
    pm.add_type("ro_b")
    pm.add_type_parameter("ro_b", "IF", default=None, unit="Hz")
    pm.add_type("ro_a")
    pm.add_type_parameter("ro_a", "IF", default=None, unit="Hz")
    pm.add_parameter("q01.readout.IF", unit="Hz")

    assert pm.types_of("q01.readout.IF") == ["ro_a", "ro_b"]


def test_an_empty_type_has_no_instances(pm):
    pm.add_type("empty")
    pm.add_parameter("q01.anything", unit="Hz")

    assert pm.instances_of("empty") == []


def test_the_root_is_never_an_instance(pm):
    pm.add_type("flat")
    pm.add_type_parameter("flat", "IF", default=None, unit="Hz")
    pm.add_parameter("IF", unit="Hz")
    pm.add_parameter("under_group.IF", unit="Hz")

    # the root carries the shape but is not a submodule: only under_group
    # is an Instance, and the root parameter is claimed by nothing
    assert pm.instances_of("flat") == ["under_group"]
    assert pm.types_of("IF") == []


def test_nothing_under_the_globals_submodule_matches(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    # a Parameter Group directly under Globals and one deeper inside it
    # both carry the whole shape with the right unit — and still match
    # nothing, because matching excludes the Globals subtree (D12)
    put_globals_parameter(pm, "_globals.qubit.IF", unit="Hz")
    put_globals_parameter(pm, "_globals.deep.qubit.IF", unit="Hz")
    pm.add_parameter("q09.IF", unit="Hz")

    assert pm.instances_of("qubit") == ["q09"]
    assert pm.types_of("_globals.qubit.IF") == []
    assert pm.types_of("_globals.deep.qubit.IF") == []


def test_values_are_irrelevant_to_matching(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.IF", initial_value=1, unit="Hz")
    pm.add_parameter("q01.octave_gain", initial_value=999, unit="dB")
    pm.add_parameter("q02.IF", initial_value=5e9, unit="Hz")
    pm.add_parameter("q02.octave_gain", initial_value=0, unit="dB")

    # the values differ wildly between the two Instances; both match
    assert sorted(pm.instances_of("qubit")) == ["q01", "q02"]


def test_a_type_nested_at_two_submodules_matches_only_whole_carriers(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "ro1", "readout")
    pm.add_nested_type("qubit", "ro2", "readout")
    pm.add_parameter("q01.ro1.IF", unit="Hz")
    pm.add_parameter("q01.ro2.IF", unit="Hz")
    # q02 carries only one of the two nested halves
    pm.add_parameter("q02.ro1.IF", unit="Hz")

    # qubit's effective set is ro1.IF and ro2.IF: only q01 carries both
    assert pm.instances_of("qubit") == ["q01"]
    # each half is an Instance of readout on its own, q02.ro1 included
    assert sorted(pm.instances_of("readout")) == [
        "q01.ro1",
        "q01.ro2",
        "q02.ro1",
    ]
    assert pm.types_of("q01.ro1.IF") == ["readout", "qubit"]
    assert pm.types_of("q02.ro1.IF") == ["readout"]


def test_instances_of_with_an_unknown_type_raises_naming_it(pm):
    with pytest.raises(ValueError, match="no Type named 'qubit' exists"):
        pm.instances_of("qubit")


def test_types_of_with_an_unknown_path_raises_naming_it(pm):
    pm.add_parameter("q01.IF", unit="Hz")

    with pytest.raises(ValueError, match="Parameter 'nope' does not exist"):
        pm.types_of("nope")
    # a Parameter Group path is not a parameter path
    with pytest.raises(ValueError, match="Parameter 'q01' does not exist"):
        pm.types_of("q01")


def test_types_of_returns_empty_for_an_unclaimed_parameter(pm):
    pm.add_parameter("q01.extra", unit="s")
    # with an empty registry nothing claims anything
    assert pm.types_of("q01.extra") == []

    put_three_tier_registry(pm)
    put_three_tier_tree(pm)

    # the extra parameter is in no Type's effective set
    assert pm.types_of("q01.extra") == []


# ---------------------------------------------------------------------------
# Type edits with Instance side effects (plan task 2.3, D13)
# ---------------------------------------------------------------------------


def test_add_type_parameter_creates_the_parameter_in_every_instance_lacking_it(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", initial_value=11, unit="dB")
    pm.add_parameter("q02.octave_gain", initial_value=12, unit="dB")
    # a unit mismatch: q03 is no Instance (D12) and gets nothing
    pm.add_parameter("q03.octave_gain", initial_value=13, unit="Hz")
    assert pm.instances_of("qubit") == ["q01", "q02"]

    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")

    # created with the entry's default value and unit (D13)
    assert pm.get("q01.IF") == 5e9
    assert pm.get("q02.IF") == 5e9
    assert pm.parameter("q01.IF").unit == "Hz"
    assert pm.parameter("q02.IF").unit == "Hz"
    assert not pm.has_param("q03.IF")
    # both Instances still match, now against the grown effective set
    assert pm.instances_of("qubit") == ["q01", "q02"]
    assert pm.get_type("qubit").parameters["IF"] == {
        "default": 5e9,
        "unit": "Hz",
        "target": None,
    }


def test_add_type_parameter_leaves_an_existing_parameter_at_the_path_alone(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    # q01 carries an extra IF with its own value and unit: extra parameters
    # do not matter to matching, and the new entry must not overwrite it
    pm.add_parameter("q01.IF", initial_value=1, unit="V")
    pm.add_parameter("q01.octave_gain", initial_value=11, unit="dB")
    pm.add_parameter("q02.octave_gain", initial_value=12, unit="dB")
    assert pm.instances_of("qubit") == ["q01", "q02"]

    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")

    # the existing parameter is left alone, whatever its unit
    assert pm.get("q01.IF") == 1
    assert pm.parameter("q01.IF").unit == "V"
    # q01 stops being an Instance: its IF does not carry the declared unit
    assert pm.instances_of("qubit") == ["q02"]


def test_add_type_parameter_on_an_empty_type_creates_nothing(pm):
    # an empty Type has no Instances (D12), so the edit has no side
    # effects: only submodules that already carry the whole shape become
    # Instances on the next matching query
    pm.add_type("qubit")
    pm.add_parameter("q01.anything", unit="Hz")

    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")

    assert not pm.has_param("q01.IF")
    assert pm.list() == ["q01.anything"]
    assert pm.instances_of("qubit") == []


def test_add_type_parameter_reaches_the_instances_of_types_nesting_it(pm):
    # qubit nests the empty readout, super nests qubit at q: adding the
    # first readout entry must write readout.window into every qubit- and
    # super-Instance, creating the missing readout Parameter Groups on the
    # way; without the outer reach, q01 and s01 would silently stop
    # matching after the edit
    pm.add_type("readout")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_type("super")
    pm.add_type_parameter("super", "top", default=1, unit="")
    pm.add_nested_type("super", "q", "qubit")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")
    pm.add_parameter("s01.top", initial_value=1, unit="")
    pm.add_parameter("s01.q.octave_gain", initial_value=10, unit="dB")
    assert pm.instances_of("qubit") == ["q01", "s01.q"]
    assert pm.instances_of("super") == ["s01"]
    assert pm.instances_of("readout") == []

    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")

    # each affected path is created once, although readout, qubit and
    # super all reach it (their pairs de-duplicate to the same paths)
    assert pm.has_param("q01.readout.window")
    assert pm.has_param("s01.q.readout.window")
    assert pm.get("q01.readout.window") == 2e-6
    assert pm.parameter("s01.q.readout.window").unit == "s"
    assert pm.instances_of("readout") == ["q01.readout", "s01.q.readout"]
    # every Instance still matches its Type against the grown sets
    assert pm.instances_of("qubit") == ["q01", "s01.q"]
    assert pm.instances_of("super") == ["s01"]


def test_add_type_parameter_writes_every_prefix_of_a_type_nested_twice(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "ro1", "readout")
    pm.add_nested_type("qubit", "ro2", "readout")
    pm.add_parameter("q01.ro1.IF", unit="Hz")
    pm.add_parameter("q01.ro2.IF", unit="Hz")
    assert pm.instances_of("qubit") == ["q01"]

    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")

    # the entry is written under every submodule that requires readout
    assert pm.has_param("q01.ro1.window")
    assert pm.has_param("q01.ro2.window")
    assert pm.get("q01.ro1.window") == 2e-6
    assert pm.instances_of("qubit") == ["q01"]


def test_add_type_parameter_refuses_a_path_the_type_already_defines(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "parameter path 'IF' is already in the effective set of "
            "Type 'qubit' (defined by Type 'qubit')"
        ),
    ):
        pm.add_type_parameter("qubit", "IF", default=1, unit="V")

    assert pm.get_type("qubit").parameters["IF"] == {
        "default": None,
        "unit": "Hz",
        "target": None,
    }


def test_add_type_parameter_refuses_a_path_defined_by_a_nested_type(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "parameter path 'readout.IF' is already in the effective set "
            "of Type 'qubit' (defined by Type 'readout')"
        ),
    ):
        pm.add_type_parameter("qubit", "readout.IF")

    assert pm.get_type("qubit").parameters == {}


def test_add_type_parameter_refuses_a_path_that_collides_in_a_nesting_type(pm):
    # qubit nests the empty readout and owns the entry readout.window:
    # adding window to readout would duplicate the path in qubit's
    # effective set and break every query on qubit
    pm.add_type("readout")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_type_parameter("qubit", "readout.window", default=None, unit="s")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "cannot add 'window' to Type 'readout': parameter path(s) "
            "'readout.window' (in the effective set of Type 'qubit') "
            "would appear more than once"
        ),
    ):
        pm.add_type_parameter("readout", "window")

    # refused before any mutation
    assert pm.get_type("readout").parameters == {}
    assert pm.get_type("qubit").parameters == {
        "readout.window": {"default": None, "unit": "s", "target": None}
    }


def test_add_type_parameter_names_every_nesting_type_collision(pm):
    # one nester nesting the edited Type at two submodules, owning an
    # entry under each: both colliding paths are named (rule 3)
    pm.add_type("inner")
    pm.add_type("outer")
    pm.add_nested_type("outer", "a", "inner")
    pm.add_nested_type("outer", "b", "inner")
    pm.add_type_parameter("outer", "a.x", default=None, unit="Hz")
    pm.add_type_parameter("outer", "b.x", default=None, unit="Hz")

    with pytest.raises(ValueError) as excinfo:
        pm.add_type_parameter("inner", "x")

    message = str(excinfo.value)
    assert "'a.x' (in the effective set of Type 'outer')" in message
    assert "'b.x' (in the effective set of Type 'outer')" in message
    # refused before any mutation
    assert pm.get_type("inner").parameters == {}
    assert pm.get_type("outer").parameters == {
        "a.x": {"default": None, "unit": "Hz", "target": None},
        "b.x": {"default": None, "unit": "Hz", "target": None},
    }


def test_add_type_parameter_refuses_a_target_blocked_by_a_parameter(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", unit="dB")
    pm.add_parameter("q02.octave_gain", unit="dB")

    with pytest.raises(ValueError) as excinfo:
        pm.add_type_parameter("qubit", "octave_gain.x", default=1, unit="s")

    # every offending path, not the first (rule 3)
    message = str(excinfo.value)
    assert "cannot create parameter 'q01.octave_gain.x'" in message
    assert "cannot create parameter 'q02.octave_gain.x'" in message
    assert "'q01.octave_gain' is a parameter, and cannot have child parameters" in message
    assert "'q02.octave_gain' is a parameter, and cannot have child parameters" in message
    # nothing was mutated
    assert pm.get_type("qubit").parameters == {
        "octave_gain": {"default": 10, "unit": "dB", "target": None}
    }
    assert pm.list() == ["q01.octave_gain", "q02.octave_gain"]


def test_add_type_parameter_refuses_a_target_blocked_by_a_parameter_group(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", unit="dB")
    # the group q01.IF occupies the target path of the new entry
    pm.add_parameter("q01.IF.sub", unit="s")
    pm.add_parameter("q02.octave_gain", unit="dB")

    with pytest.raises(
        ValueError,
        match=re.escape("cannot create parameter 'q01.IF': 'q01.IF' is already a Parameter Group"),
    ):
        pm.add_type_parameter("qubit", "IF", default=1, unit="Hz")

    assert pm.get_type("qubit").parameters == {
        "octave_gain": {"default": 10, "unit": "dB", "target": None}
    }
    assert not pm.has_param("q02.IF")


def test_add_type_parameter_refuses_a_path_with_empty_segments(pm):
    pm.add_type("qubit")

    with pytest.raises(ValueError, match="is not a valid parameter path"):
        pm.add_type_parameter("qubit", "")
    with pytest.raises(ValueError, match="is not a valid parameter path"):
        pm.add_type_parameter("qubit", "x..y")

    assert pm.get_type("qubit").parameters == {}
    assert pm.list() == []


def test_remove_type_parameter_leaves_the_instance_parameters_untouched(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.IF", initial_value=5e9, unit="Hz")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")

    pm.remove_type_parameter("qubit", "IF")

    # the parameter stays on the Instance, with value and unit (D13)
    assert pm.has_param("q01.IF")
    assert pm.get("q01.IF") == 5e9
    assert pm.parameter("q01.IF").unit == "Hz"
    # the registry lost the entry; the shrunken shape still matches q01,
    # whose removed parameter simply became an untyped row
    assert pm.get_type("qubit").parameters == {
        "octave_gain": {"default": 10, "unit": "dB", "target": None}
    }
    assert pm.instances_of("qubit") == ["q01"]
    assert pm.types_of("q01.IF") == []
    assert pm.types_of("q01.octave_gain") == ["qubit"]


def test_remove_type_parameter_refuses_a_path_only_reached_through_a_nested_type(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "parameter path 'readout.IF' is not an entry of Type 'qubit' "
            "itself: it is only in the effective set through the entry of "
            "Type 'readout'"
        ),
    ):
        pm.remove_type_parameter("qubit", "readout.IF")

    assert pm.get_type("qubit").nested == {"readout": "readout"}
    assert pm.get_type("readout").parameters == {
        "IF": {"default": None, "unit": "Hz", "target": None}
    }


def test_remove_type_parameter_refuses_an_unknown_path(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")

    with pytest.raises(
        ValueError,
        match=re.escape("parameter path 'nope' is not an entry of Type 'qubit'"),
    ):
        pm.remove_type_parameter("qubit", "nope")

    assert pm.get_type("qubit").parameters == {
        "IF": {"default": None, "unit": "Hz", "target": None}
    }


def test_set_type_parameter_default_changes_only_the_registry(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_parameter("q01.IF", initial_value=5e9, unit="Hz")

    pm.set_type_parameter_default("qubit", "IF", 6e9)

    assert pm.get_type("qubit").parameters["IF"]["default"] == 6e9
    # the Instance keeps its value (D13): only parameters created later
    # start with the new default
    assert pm.get("q01.IF") == 5e9
    assert pm.instances_of("qubit") == ["q01"]


def test_set_type_parameter_default_refuses_paths_that_are_not_its_own_entries(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "'readout.IF' is not an entry of Type 'qubit' itself"
        ),
    ):
        pm.set_type_parameter_default("qubit", "readout.IF", 1)
    with pytest.raises(
        ValueError,
        match=re.escape("'nope' is not an entry of Type 'qubit'"),
    ):
        pm.set_type_parameter_default("qubit", "nope", 1)

    assert pm.get_type("readout").parameters["IF"]["default"] is None


def test_set_type_parameter_unit_propagates_to_every_instance(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_type("super")
    pm.add_type_parameter("super", "top", default=1, unit="")
    pm.add_nested_type("super", "q", "qubit")
    pm.add_parameter("q01.octave_gain", unit="dB")
    pm.add_parameter("q01.readout.IF", unit="Hz")
    pm.add_parameter("s01.top", unit="")
    pm.add_parameter("s01.q.octave_gain", unit="dB")
    pm.add_parameter("s01.q.readout.IF", unit="Hz")

    pm.set_type_parameter_unit("readout", "IF", "V")

    # the entry and every Instance's parameter carry the new unit — the
    # same parameter, whether reached through readout, qubit or super
    assert pm.get_type("readout").parameters["IF"]["unit"] == "V"
    assert pm.parameter("q01.readout.IF").unit == "V"
    assert pm.parameter("s01.q.readout.IF").unit == "V"
    # the Instances still match, now against the new unit
    assert pm.instances_of("readout") == ["q01.readout", "s01.q.readout"]
    assert pm.instances_of("qubit") == ["q01", "s01.q"]
    assert pm.instances_of("super") == ["s01"]
    # untouched parameters keep their unit
    assert pm.parameter("q01.octave_gain").unit == "dB"


def test_set_type_parameter_unit_refuses_paths_that_are_not_its_own_entries(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "'readout.IF' is not an entry of Type 'qubit' itself"
        ),
    ):
        pm.set_type_parameter_unit("qubit", "readout.IF", "V")
    with pytest.raises(
        ValueError,
        match=re.escape("'nope' is not an entry of Type 'qubit'"),
    ):
        pm.set_type_parameter_unit("qubit", "nope", "V")

    assert pm.get_type("readout").parameters["IF"]["unit"] == "Hz"


def test_add_nested_type_writes_the_nested_entries_into_the_instances(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")
    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")
    assert pm.instances_of("qubit") == ["q01"]

    pm.add_nested_type("qubit", "readout", "readout")

    # the nested entries are written under the submodule with their
    # defaults and units (D13)
    assert pm.has_param("q01.readout.IF")
    assert pm.get("q01.readout.IF") == 10e6
    assert pm.get("q01.readout.window") == 2e-6
    assert pm.parameter("q01.readout.window").unit == "s"
    assert pm.get_type("qubit").nested == {"readout": "readout"}
    assert pm.instances_of("qubit") == ["q01"]
    assert pm.instances_of("readout") == ["q01.readout"]


def test_add_nested_type_reaches_the_instances_of_outer_types(pm):
    # qubit is empty when super nests it, so the super-Instance s01 has no
    # q group at all: nesting readout into qubit must create
    # s01.q.readout.IF through the missing Parameter Groups
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")
    pm.add_type("qubit")
    pm.add_type("super")
    pm.add_type_parameter("super", "top", default=1, unit="")
    pm.add_nested_type("super", "q", "qubit")
    pm.add_parameter("s01.top", initial_value=1, unit="")
    assert pm.instances_of("qubit") == []
    assert pm.instances_of("super") == ["s01"]

    pm.add_nested_type("qubit", "readout", "readout")

    assert pm.has_param("s01.q.readout.IF")
    assert pm.get("s01.q.readout.IF") == 10e6
    assert pm.parameter("s01.q.readout.IF").unit == "Hz"
    assert pm.instances_of("qubit") == ["s01.q"]
    assert pm.instances_of("super") == ["s01"]
    assert pm.instances_of("readout") == ["s01.q.readout"]


def test_add_nested_type_builds_the_three_tier_case(pm):
    # a Nested Type that itself nests a Type, built entirely through the
    # public API: nesting readout into qubit writes readout's whole
    # effective set, pulse_window's entries included
    pm.add_type("pulse_window")
    pm.add_type_parameter("pulse_window", "duration", default=None, unit="s")
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_nested_type("readout", "pw", "pulse_window")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")

    pm.add_nested_type("qubit", "readout", "readout")

    assert pm.has_param("q01.readout.IF")
    assert pm.get("q01.readout.IF") is None
    assert pm.parameter("q01.readout.IF").unit == "Hz"
    assert pm.has_param("q01.readout.pw.duration")
    assert pm.get("q01.readout.pw.duration") is None
    assert pm.parameter("q01.readout.pw.duration").unit == "s"
    assert pm.instances_of("qubit") == ["q01"]
    assert pm.instances_of("readout") == ["q01.readout"]
    assert pm.instances_of("pulse_window") == ["q01.readout.pw"]


def test_add_nested_type_leaves_an_existing_parameter_at_the_target_alone(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    # q01 carries a readout.IF of its own, with another value and unit
    pm.add_parameter("q01.readout.IF", initial_value=1, unit="V")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")
    assert pm.instances_of("qubit") == ["q01"]

    pm.add_nested_type("qubit", "readout", "readout")

    # the existing parameter is left alone, whatever its unit
    assert pm.get("q01.readout.IF") == 1
    assert pm.parameter("q01.readout.IF").unit == "V"
    # q01 stops being an Instance: its readout.IF does not carry the unit
    # the entry declares
    assert pm.instances_of("qubit") == []


def test_add_nested_type_accepts_a_dotted_submodule_name(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")

    pm.add_nested_type("qubit", "ro.deep", "readout")

    assert pm.get_type("qubit").nested == {"ro.deep": "readout"}
    assert pm._effective_parameters("qubit")["ro.deep.IF"] == {
        "unit": "Hz",
        "from_type": "readout",
    }
    # the entries are written under the dotted submodule, with the entry
    # default and unit
    assert pm.get("q01.ro.deep.IF") == 10e6
    assert pm.parameter("q01.ro.deep.IF").unit == "Hz"
    assert pm.instances_of("qubit") == ["q01"]

    # removing the Nested Type is symmetric
    pm.remove_nested_type("qubit", "ro.deep")
    assert pm.get_type("qubit").nested == {}
    # the created parameter stays (D13)
    assert pm.has_param("q01.ro.deep.IF")


def test_add_nested_type_refuses_a_self_nesting(pm):
    pm.add_type("loop")

    with pytest.raises(
        ValueError,
        match=re.escape("cycle in nested Types: loop -> loop"),
    ):
        pm.add_nested_type("loop", "self", "loop")

    assert pm.get_type("loop").nested == {}


def test_add_nested_type_refuses_a_longer_cycle(pm):
    pm.add_type("readout")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape("cycle in nested Types: readout -> qubit -> readout"),
    ):
        pm.add_nested_type("readout", "qubit", "qubit")

    assert pm.get_type("readout").nested == {}
    assert pm.get_type("qubit").nested == {"readout": "readout"}


def test_add_nested_type_refuses_an_occupied_submodule(pm):
    pm.add_type("readout")
    pm.add_type("pulse_window")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "submodule 'readout' of Type 'qubit' already requires the "
            "Nested Type 'readout'"
        ),
    ):
        pm.add_nested_type("qubit", "readout", "pulse_window")

    assert pm.get_type("qubit").nested == {"readout": "readout"}


def test_add_nested_type_refuses_a_target_blocked_by_a_parameter_group(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.octave_gain", unit="dB")
    # the Parameter Group q01.readout.IF occupies the target path of the
    # nested entry IF
    pm.add_parameter("q01.readout.IF.sub", unit="s")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "cannot create parameter 'q01.readout.IF': 'q01.readout.IF' "
            "is already a Parameter Group"
        ),
    ):
        pm.add_nested_type("qubit", "readout", "readout")

    # nothing was mutated
    assert pm.get_type("qubit").nested == {}
    assert pm.list() == ["q01.readout.IF.sub", "q01.octave_gain"]


def test_add_nested_type_refuses_conflicting_creation_targets(pm):
    # the Nested Type's effective set holds b and the strict extension
    # b.c: the one edit would create the parameter q01.s.b and need it as
    # a Parameter Group for q01.s.b.c — refused before anything is
    # mutated, after which the creation would have raised mid-way
    pm.add_type("leaf")
    pm.add_type_parameter("leaf", "c", default=1, unit="V")
    pm.add_type("branched")
    pm.add_type_parameter("branched", "b", default=2, unit="A")
    pm.add_nested_type("branched", "b", "leaf")
    pm.add_type("outer")
    pm.add_type_parameter("outer", "top", default=0, unit="")
    pm.add_parameter("q01.top", initial_value=0, unit="")
    assert pm.instances_of("outer") == ["q01"]

    with pytest.raises(ValueError) as excinfo:
        pm.add_nested_type("outer", "s", "branched")

    # the offending pair is named, both paths (rule 3)
    message = str(excinfo.value)
    assert "cannot create parameter 'q01.s.b.c'" in message
    assert "'q01.s.b' is also created by this edit" in message
    # refused before any mutation
    assert pm.get_type("outer").nested == {}
    assert pm.list() == ["q01.top"]


def test_add_nested_type_refuses_a_submodule_name_with_empty_segments(pm):
    pm.add_type("readout")
    pm.add_type("qubit")

    with pytest.raises(
        ValueError,
        match=re.escape("'' is not a valid submodule name for a Nested Type"),
    ):
        pm.add_nested_type("qubit", "", "readout")
    with pytest.raises(
        ValueError,
        match=re.escape("'x..y' is not a valid submodule name for a Nested Type"),
    ):
        pm.add_nested_type("qubit", "x..y", "readout")

    assert pm.get_type("qubit").nested == {}


def test_add_nested_type_refuses_a_duplicated_effective_path(pm):
    # qubit's own entry readout.IF would collide with the readout entry,
    # both in qubit's effective set and in the one of super, which nests
    # qubit at q
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "readout.IF", default=None, unit="Hz")
    pm.add_type("super")
    pm.add_nested_type("super", "q", "qubit")

    with pytest.raises(ValueError) as excinfo:
        pm.add_nested_type("qubit", "readout", "readout")

    # every offending path, not the first (rule 3)
    message = str(excinfo.value)
    assert "'readout.IF' (in the effective set of Type 'qubit')" in message
    assert "'q.readout.IF' (in the effective set of Type 'super')" in message
    assert pm.get_type("qubit").nested == {}
    assert pm.get_type("qubit").parameters == {
        "readout.IF": {"default": None, "unit": "Hz", "target": None}
    }


def test_add_nested_type_refuses_the_globals_submodule(pm):
    pm.add_type("readout")
    pm.add_type("qubit")

    with pytest.raises(
        ValueError,
        match=re.escape("the Globals submodule name is reserved"),
    ):
        pm.add_nested_type("qubit", "_globals", "readout")

    assert pm.get_type("qubit").nested == {}


def test_add_nested_type_with_an_unknown_type_raises_naming_it(pm):
    pm.add_type("readout")

    with pytest.raises(ValueError, match="no Type named 'qubit' exists"):
        pm.add_nested_type("qubit", "readout", "readout")
    # both missing names appear in one error (rule 3)
    with pytest.raises(ValueError) as excinfo:
        pm.add_nested_type("qubit", "ro", "pulse_window")
    assert "no Type named 'qubit' exists" in str(excinfo.value)
    assert "no Type named 'pulse_window' exists" in str(excinfo.value)

    assert pm.list_types() == ["readout"]


def test_remove_nested_type_leaves_the_parameters_untouched(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=None, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_parameter("q01.octave_gain", unit="dB")
    pm.add_parameter("q01.readout.IF", unit="Hz")

    pm.remove_nested_type("qubit", "readout")

    # every parameter stays (D13); the shrunken shape still matches q01,
    # whose readout parameter simply became an untyped row
    assert pm.has_param("q01.readout.IF")
    assert pm.parameter("q01.readout.IF").unit == "Hz"
    assert pm.get_type("qubit").nested == {}
    assert pm.instances_of("qubit") == ["q01"]
    assert pm.instances_of("readout") == ["q01.readout"]
    assert pm.types_of("q01.readout.IF") == ["readout"]


def test_remove_nested_type_refuses_a_submodule_without_one(pm):
    pm.add_type("qubit")

    with pytest.raises(
        ValueError,
        match=re.escape("submodule 'readout' of Type 'qubit' has no Nested Type"),
    ):
        pm.remove_nested_type("qubit", "readout")


def test_remove_type_leaves_the_parameters_untouched(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_parameter("q01.IF", initial_value=5e9, unit="Hz")

    pm.remove_type("qubit")

    # deleting the Type touches no parameters (D13); the row is untyped
    assert pm.has_param("q01.IF")
    assert pm.get("q01.IF") == 5e9
    assert pm.types_of("q01.IF") == []


def test_a_failed_validation_leaves_the_tree_and_registry_byte_identical(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")
    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")
    pm.add_parameter("q01.readout.IF", initial_value=10e6, unit="Hz")
    pm.add_parameter("q01.readout.window", initial_value=2e-6, unit="s")
    pm.add_parameter("q02.octave_gain", initial_value=11, unit="dB")
    pm.add_parameter("q02.readout.IF", initial_value=20e6, unit="Hz")
    # a Nested Type whose effective set holds b and the strict extension
    # b.c, built through the public API while it has no Instances
    pm.add_type("leaf")
    pm.add_type_parameter("leaf", "c", default=1, unit="V")
    pm.add_type("branched")
    pm.add_type_parameter("branched", "b", default=2, unit="A")
    pm.add_nested_type("branched", "b", "leaf")
    # an empty Nested Type whose nester owns an entry under it, at two
    # submodules: adding the entry to the empty Type collides twice
    pm.add_type("bare")
    pm.add_type("holder")
    pm.add_type_parameter("holder", "bare.window", default=None, unit="s")
    pm.add_nested_type("holder", "bare", "bare")
    pm.add_nested_type("holder", "bare2", "bare")
    pm.add_type_parameter("holder", "bare2.window", default=None, unit="s")
    # an outer Type with an Instance, for the refused nesting below
    pm.add_type("outer")
    pm.add_type_parameter("outer", "top", default=0, unit="")
    pm.add_parameter("q01.top", initial_value=0, unit="")
    # shapes and parameters for the add_instance refusals below
    pm.add_type("sensor")
    pm.add_type_parameter("sensor", "sub.x", default=1, unit="V")
    pm.add_type_parameter("sensor", "sub.y", default=2, unit="A")
    pm.add_parameter("q03.octave_gain", initial_value=1, unit="V")
    pm.add_parameter("q04.sub", initial_value=0, unit="V")
    pm.add_parameter("q05.readout.window.sub", initial_value=0, unit="s")

    def state():
        return (
            sorted(pm.list()),
            {path: pm.get(path) for path in pm.list()},
            {path: pm.parameter(path).unit for path in pm.list()},
            copy.deepcopy(pm._types),
        )

    before = state()
    failing_calls = [
        lambda: pm.add_type_parameter("qubit", "octave_gain"),
        lambda: pm.add_type_parameter("qubit", "readout.IF"),
        lambda: pm.add_type_parameter("nope", "x"),
        lambda: pm.add_type_parameter("qubit", ""),
        # q02.octave_gain is a parameter and blocks the target path
        lambda: pm.add_type_parameter("qubit", "octave_gain.x", default=1, unit="s"),
        # the path collides in the effective set of holder, which nests
        # the empty bare at bare and bare2 and owns an entry under each:
        # both colliding paths are named
        lambda: pm.add_type_parameter("bare", "window"),
        lambda: pm.remove_type_parameter("qubit", "readout.IF"),
        lambda: pm.remove_type_parameter("qubit", "nope"),
        lambda: pm.set_type_parameter_default("qubit", "readout.IF", 1),
        lambda: pm.set_type_parameter_default("qubit", "nope", 1),
        lambda: pm.set_type_parameter_unit("qubit", "readout.IF", "V"),
        lambda: pm.set_type_parameter_unit("qubit", "nope", "V"),
        lambda: pm.add_nested_type("qubit", "readout", "readout"),
        lambda: pm.add_nested_type("qubit", "readout", "nope"),
        lambda: pm.add_nested_type("qubit", "_globals", "readout"),
        lambda: pm.add_nested_type("qubit", "ro", "nope"),
        lambda: pm.add_nested_type("nope", "s", "readout"),
        lambda: pm.add_nested_type("readout", "qubit", "qubit"),
        lambda: pm.add_nested_type("readout", "self", "readout"),
        # q01.octave_gain is a parameter and blocks the nested targets
        lambda: pm.add_nested_type("qubit", "octave_gain", "readout"),
        # the edit would create q01.s.b and need it as a Parameter Group
        # for q01.s.b.c: the targets of one edit conflict with each other
        lambda: pm.add_nested_type("outer", "s", "branched"),
        lambda: pm.add_nested_type("qubit", "", "readout"),
        lambda: pm.add_nested_type("qubit", "x..y", "readout"),
        lambda: pm.remove_nested_type("qubit", "pw"),
        lambda: pm.remove_nested_type("nope", "readout"),
        # add_instance refusals (task 2.4): an unknown Type, an invalid
        # name, the reserved Globals name, a unit conflict (q03.octave_gain
        # carries unit V where qubit declares dB), a target blocked by a
        # parameter (q04.sub), a target occupied by a Parameter Group
        # (q05.readout.window), and the conflicting targets b / b.c of
        # branched
        lambda: pm.add_instance("nope", "q01"),
        lambda: pm.add_instance("qubit", ""),
        lambda: pm.add_instance("qubit", "x..y"),
        lambda: pm.add_instance("qubit", "_globals"),
        lambda: pm.add_instance("qubit", "_globals.deep"),
        lambda: pm.add_instance("qubit", "q03"),
        lambda: pm.add_instance("sensor", "q04"),
        lambda: pm.add_instance("qubit", "q05"),
        lambda: pm.add_instance("branched", "q06"),
    ]
    for call in failing_calls:
        with pytest.raises(ValueError):
            call()
        # the refused call left list, every value and unit, and the Type
        # registry byte-identical
        assert state() == before


# ---------------------------------------------------------------------------
# add_instance (plan task 2.4, D14)
# ---------------------------------------------------------------------------


def test_add_instance_creates_the_missing_entries_with_defaults_and_units(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")

    pm.add_instance("qubit", "q01")

    # every effective path is created with the entry default and unit
    assert pm.get("q01.IF") == 5e9
    assert pm.parameter("q01.IF").unit == "Hz"
    assert pm.get("q01.octave_gain") == 10
    assert pm.parameter("q01.octave_gain").unit == "dB"
    # created through the ordinary add_parameter path: ManagedParameters
    # that can carry a Lock, with the full dotted path
    assert isinstance(pm.parameter("q01.IF"), ManagedParameter)
    assert pm.parameter("q01.IF").path == "parameter_manager.q01.IF"
    # after the call the submodule carries the whole shape (D14)
    assert pm.instances_of("qubit") == ["q01"]


def test_add_instance_keeps_existing_entries_with_value_and_unit(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.IF", initial_value=6e9, unit="Hz")

    pm.add_instance("qubit", "q01")

    # the existing parameter keeps its own value and unit
    assert pm.get("q01.IF") == 6e9
    assert pm.parameter("q01.IF").unit == "Hz"
    # the missing one is created
    assert pm.get("q01.octave_gain") == 10
    assert pm.instances_of("qubit") == ["q01"]


def test_add_instance_accepts_a_dotted_name(pm):
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")

    pm.add_instance("readout", "q02.ro")

    # the Parameter Groups on the way are created
    assert pm.get("q02.ro.IF") == 10e6
    assert pm.parameter("q02.ro.IF").unit == "Hz"
    assert pm.instances_of("readout") == ["q02.ro"]


def test_add_instance_builds_the_three_tier_case(pm):
    put_three_tier_registry(pm)

    pm.add_instance("qubit", "q01")

    # every effective path of the whole nesting chain is created with the
    # entry default and unit
    assert pm.get("q01.IF") is None
    assert pm.parameter("q01.IF").unit == "Hz"
    assert pm.get("q01.octave_gain") == 10
    assert pm.parameter("q01.octave_gain").unit == "dB"
    assert pm.get("q01.readout.IF") is None
    assert pm.parameter("q01.readout.IF").unit == "Hz"
    assert pm.get("q01.readout.window") is None
    assert pm.parameter("q01.readout.window").unit == "s"
    assert pm.get("q01.readout.pw.duration") is None
    assert pm.parameter("q01.readout.pw.duration").unit == "s"
    # q01 matches at every tier
    assert pm.instances_of("qubit") == ["q01"]
    assert pm.instances_of("readout") == ["q01.readout"]
    assert pm.instances_of("pulse_window") == ["q01.readout.pw"]


def test_add_instance_refuses_a_unit_conflict_naming_every_conflicting_path(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.IF", initial_value=1, unit="V")
    pm.add_parameter("q01.octave_gain", initial_value=2, unit="W")

    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("qubit", "q01")

    # every conflicting path with both units, not the first (rule 3)
    message = str(excinfo.value)
    assert "cannot add an Instance of Type 'qubit' at 'q01'" in message
    assert "'q01.IF' carries unit 'V', the Type declares 'Hz'" in message
    assert "'q01.octave_gain' carries unit 'W', the Type declares 'dB'" in message
    # the scan refuses before anything is created (D14)
    assert pm.list() == ["q01.IF", "q01.octave_gain"]
    assert pm.instances_of("qubit") == []


def test_add_instance_refuses_a_unit_conflict_on_a_nested_effective_path(pm):
    # the conflict sits on readout.IF: an effective path of qubit reached
    # through the Nested Type, so the scan must walk the expanded set
    put_three_tier_registry(pm)
    pm.add_parameter("q01.readout.IF", initial_value=1, unit="V")

    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("qubit", "q01")

    # the full dotted path relative to the Parameter Manager, with both units
    message = str(excinfo.value)
    assert "cannot add an Instance of Type 'qubit' at 'q01'" in message
    assert "'q01.readout.IF' carries unit 'V', the Type declares 'Hz'" in message
    # the scan refuses before anything is created (D14)
    assert pm.list() == ["q01.readout.IF"]
    assert pm.instances_of("qubit") == []


def test_add_instance_refuses_a_target_blocked_by_a_parameter(pm):
    pm.add_type("sensor")
    pm.add_type_parameter("sensor", "sub.x", default=1, unit="V")
    pm.add_type_parameter("sensor", "sub.y", default=2, unit="A")
    pm.add_parameter("q01.sub", initial_value=0, unit="V")

    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("sensor", "q01")

    # every offending target path, not the first (rule 3)
    message = str(excinfo.value)
    assert "cannot create parameter 'q01.sub.x'" in message
    assert "cannot create parameter 'q01.sub.y'" in message
    assert "'q01.sub' is a parameter, and cannot have child parameters" in message
    # nothing was created
    assert pm.list() == ["q01.sub"]


def test_add_instance_refuses_a_name_blocked_by_a_parameter(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    # the root parameter q01 takes the place the Instance needs
    pm.add_parameter("q01", initial_value=0, unit="s")

    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("qubit", "q01")

    message = str(excinfo.value)
    assert "cannot create parameter 'q01.IF'" in message
    assert "'q01' is a parameter, and cannot have child parameters" in message
    # a deeper name is blocked by the same parameter
    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("qubit", "q01.ro")
    assert "cannot create parameter 'q01.ro.IF'" in str(excinfo.value)

    assert pm.list() == ["q01"]


def test_add_instance_refuses_a_target_blocked_by_a_parameter_group(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    # the Parameter Group q01.IF occupies the target path of the entry IF
    pm.add_parameter("q01.IF.sub", unit="s")

    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("qubit", "q01")

    message = str(excinfo.value)
    assert "cannot create parameter 'q01.IF'" in message
    assert "'q01.IF' is already a Parameter Group" in message
    # nothing was created
    assert pm.list() == ["q01.IF.sub"]


def test_add_instance_refuses_conflicting_creation_targets(pm):
    # the Type's effective set holds b and the strict extension b.c
    # (buildable while the Type has no Instances): the one call would
    # create q01.b and need it as a Parameter Group for q01.b.c
    pm.add_type("leaf")
    pm.add_type_parameter("leaf", "c", default=1, unit="V")
    pm.add_type("branched")
    pm.add_type_parameter("branched", "b", default=2, unit="A")
    pm.add_nested_type("branched", "b", "leaf")

    with pytest.raises(ValueError) as excinfo:
        pm.add_instance("branched", "q01")

    message = str(excinfo.value)
    assert "cannot create parameter 'q01.b.c'" in message
    assert "'q01.b' is also created by this edit" in message
    # nothing was created
    assert pm.list() == []


def test_add_instance_refuses_the_globals_submodule(pm):
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "'_globals' is not a valid submodule path for an Instance: "
            "the Globals submodule name is reserved"
        ),
    ):
        pm.add_instance("qubit", "_globals")
    # anything under the Globals submodule is refused too, naming its own
    # offending name (D18)
    with pytest.raises(
        ValueError,
        match=re.escape(
            "'_globals.q01' is not a valid submodule path for an Instance: "
            "the Globals submodule name is reserved"
        ),
    ):
        pm.add_instance("qubit", "_globals.q01")

    # nothing was created
    assert pm.list() == []


def test_add_instance_refuses_the_globals_submodule_on_an_empty_type(pm):
    # the name refusals are unconditional: even an empty Type, which
    # creates nothing anyway, refuses the reserved Globals name (D18)
    pm.add_type("empty")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "'_globals' is not a valid submodule path for an Instance: "
            "the Globals submodule name is reserved"
        ),
    ):
        pm.add_instance("empty", "_globals")
    with pytest.raises(
        ValueError,
        match=re.escape(
            "'_globals.q01' is not a valid submodule path for an Instance: "
            "the Globals submodule name is reserved"
        ),
    ):
        pm.add_instance("empty", "_globals.q01")

    # nothing was created
    assert pm.list() == []


def test_add_instance_refuses_a_name_with_empty_segments(pm):
    pm.add_type("qubit")

    with pytest.raises(
        ValueError,
        match=re.escape("'' is not a valid submodule path for an Instance"),
    ):
        pm.add_instance("qubit", "")
    with pytest.raises(
        ValueError,
        match=re.escape("'x..y' is not a valid submodule path for an Instance"),
    ):
        pm.add_instance("qubit", "x..y")

    assert pm.list() == []


def test_add_instance_with_an_unknown_type_raises_naming_it(pm):
    with pytest.raises(ValueError, match="no Type named 'qubit' exists"):
        pm.add_instance("qubit", "q01")

    assert pm.list() == []


def test_add_instance_on_an_empty_type_creates_nothing(pm):
    pm.add_type("empty")

    pm.add_instance("empty", "q01")

    # no parameter and no Parameter Group was created; an empty Type has
    # no Instances (D12), so q01 is not listed either
    assert pm.list() == []
    assert "q01" not in pm.submodules
    assert pm.instances_of("empty") == []


# ---------------------------------------------------------------------------
# pm-type-update and side-effect creation Broadcasts (plan task 2.5, D22)
#
# One pm-type-update per affected Type — the edited Type first, then every
# Type nesting it, whose effective parameter set the edit changed —
# carrying that Type's fresh PMTypeBluePrint; remove_type emits exactly
# one with a None payload. The parameters a Type edit or add_instance
# creates as side effects are re-emitted as one parameter-creation each,
# in creation order, before the Type updates. Read-only queries, refused
# calls and kept parameters emit nothing.
# ---------------------------------------------------------------------------


@pytest.fixture
def pm_with_sink(pm):
    """The Type API fixture with a Broadcast sink attached, recording
    every Broadcast the Parameter Manager emits."""
    received = []
    pm.add_broadcast_sink(received.append)
    return pm, received


def put_nested_instance(pm):
    """``readout`` (entry IF) nested in ``qubit``, with the Instance q01
    carrying the whole shape: an edit to readout reaches qubit's effective
    parameter set too, so both Types are affected."""
    pm.add_type("readout")
    pm.add_type_parameter("readout", "IF", default=10e6, unit="Hz")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_nested_type("qubit", "readout", "readout")
    pm.add_parameter("q01.readout.IF", initial_value=10e6, unit="Hz")
    pm.add_parameter("q01.octave_gain", initial_value=10, unit="dB")


def test_add_type_emits_one_pm_type_update_with_the_fresh_blueprint(pm_with_sink):
    pm, received = pm_with_sink

    pm.add_type("qubit")

    assert len(received) == 1
    bp = received[0]
    assert isinstance(bp, ParameterBroadcastBluePrint)
    assert bp.name == "parameter_manager.qubit"
    assert bp.action == PM_TYPE_UPDATE
    assert isinstance(bp.value, PMTypeBluePrint)
    assert bp.value == PMTypeBluePrint(
        name="qubit", parameters={}, nested={}, effective={}
    )


def test_remove_type_emits_one_none_payload(pm_with_sink):
    pm, received = pm_with_sink
    pm.add_type("readout")
    pm.add_type("qubit")
    pm.add_nested_type("qubit", "readout", "readout")
    received.clear()

    pm.remove_type("qubit")

    # qubit nests readout, not the other way round: removing it affects no
    # other Type, so exactly one Broadcast with a None payload goes out
    assert len(received) == 1
    bp = received[0]
    assert bp.name == "parameter_manager.qubit"
    assert bp.action == PM_TYPE_UPDATE
    assert bp.value is None


def test_add_type_parameter_emits_the_creation_then_the_type_updates(pm_with_sink):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    received.clear()

    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")

    # the side-effect creation first, then one pm-type-update per affected
    # Type: the edited readout first, then qubit, whose effective set the
    # new entry extends
    assert len(received) == 3
    creation, readout_update, qubit_update = received
    assert creation.name == "parameter_manager.q01.readout.window"
    assert creation.action == PARAMETER_CREATION
    assert creation.value == 2e-6
    assert creation.unit == "s"
    assert readout_update.name == "parameter_manager.readout"
    assert readout_update.action == PM_TYPE_UPDATE
    assert isinstance(readout_update.value, PMTypeBluePrint)
    assert readout_update.value.parameters["window"] == {
        "default": 2e-6,
        "unit": "s",
        "target": None,
    }
    assert qubit_update.name == "parameter_manager.qubit"
    assert qubit_update.action == PM_TYPE_UPDATE
    assert qubit_update.value.effective["readout.window"] == {
        "unit": "s",
        "from_type": "readout",
    }


def test_pm_type_update_reaches_every_type_of_a_three_tier_nesting_chain(
    pm_with_sink,
):
    # the walk must follow the nesting chain transitively: pulse_window is
    # nested in readout, which is nested in qubit, so an edit to
    # pulse_window affects all three Types — a walk stopping at the direct
    # nesters would miss qubit
    pm, received = pm_with_sink
    put_three_tier_registry(pm)
    received.clear()

    pm.add_type_parameter("pulse_window", "amp", default=1, unit="V")

    # no Instances exist, so no parameter-creation goes out: exactly one
    # pm-type-update per affected Type, the edited pulse_window first,
    # then outwards along the chain
    assert len(received) == 3
    pulse_update, readout_update, qubit_update = received
    assert [bp.action for bp in received] == [PM_TYPE_UPDATE] * 3
    assert isinstance(pulse_update.value, PMTypeBluePrint)
    assert pulse_update.name == "parameter_manager.pulse_window"
    assert pulse_update.value.parameters["amp"] == {
        "default": 1,
        "unit": "V",
        "target": None,
    }
    assert isinstance(readout_update.value, PMTypeBluePrint)
    assert readout_update.name == "parameter_manager.readout"
    assert readout_update.value.effective["pw.amp"] == {
        "unit": "V",
        "from_type": "pulse_window",
    }
    assert isinstance(qubit_update.value, PMTypeBluePrint)
    assert qubit_update.name == "parameter_manager.qubit"
    assert qubit_update.value.effective["readout.pw.amp"] == {
        "unit": "V",
        "from_type": "pulse_window",
    }


def test_add_type_parameter_emits_no_creation_for_kept_parameters(pm_with_sink):
    # q01.readout.window exists already: the edit writes the entry into the
    # registry only, and the kept parameter emits no parameter-creation
    # (D22); readout's own Instance target and qubit's prefixed target are
    # the same path, so nothing is created at all
    pm, received = pm_with_sink
    put_nested_instance(pm)
    pm.add_parameter("q01.readout.window", initial_value=3e-6, unit="s")
    received.clear()

    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")

    assert [bp.action for bp in received] == [PM_TYPE_UPDATE] * 2
    readout_update, qubit_update = received
    assert readout_update.name == "parameter_manager.readout"
    assert qubit_update.name == "parameter_manager.qubit"
    # the kept parameter kept its own value (D13)
    assert pm.get("q01.readout.window") == 3e-6


def test_remove_type_parameter_emits_updates_for_the_edited_and_nesting_types(
    pm_with_sink,
):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    pm.add_type_parameter("readout", "window", default=2e-6, unit="s")
    received.clear()

    pm.remove_type_parameter("readout", "window")

    # no parameter is removed (D13), so no creations: one pm-type-update
    # per affected Type, the edited readout first
    assert len(received) == 2
    readout_update, qubit_update = received
    assert readout_update.name == "parameter_manager.readout"
    assert readout_update.action == PM_TYPE_UPDATE
    assert "window" not in readout_update.value.parameters
    assert qubit_update.name == "parameter_manager.qubit"
    assert qubit_update.action == PM_TYPE_UPDATE
    assert "readout.window" not in qubit_update.value.effective


def test_set_type_parameter_default_emits_one_update_for_the_edited_type(
    pm_with_sink,
):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    received.clear()

    pm.set_type_parameter_default("readout", "IF", 20e6)

    # only the edited Type is named: a nesting Type's blueprint is
    # unchanged, since the effective parameter set carries units and
    # defining Types, not defaults
    assert len(received) == 1
    update = received[0]
    assert update.name == "parameter_manager.readout"
    assert update.action == PM_TYPE_UPDATE
    assert update.value.parameters["IF"]["default"] == 20e6


def test_set_type_parameter_unit_emits_updates_for_every_affected_type(pm_with_sink):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    received.clear()

    pm.set_type_parameter_unit("readout", "IF", "V")

    # the unit reaches every Instance and the effective parameter set of
    # every Type nesting the edited one, so both Types are named
    assert len(received) == 2
    readout_update, qubit_update = received
    assert readout_update.name == "parameter_manager.readout"
    assert readout_update.value.effective["IF"]["unit"] == "V"
    assert qubit_update.name == "parameter_manager.qubit"
    assert qubit_update.value.effective["readout.IF"]["unit"] == "V"
    # the propagation itself happened (D13)
    assert pm.parameter("q01.readout.IF").unit == "V"


def test_add_nested_type_emits_the_creation_then_the_type_updates(pm_with_sink):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    pm.add_type("pulse_window")
    pm.add_type_parameter("pulse_window", "duration", default=None, unit="s")
    received.clear()

    pm.add_nested_type("readout", "pw", "pulse_window")

    assert len(received) == 3
    creation, readout_update, qubit_update = received
    assert creation.name == "parameter_manager.q01.readout.pw.duration"
    assert creation.action == PARAMETER_CREATION
    assert creation.value is None
    assert creation.unit == "s"
    assert readout_update.name == "parameter_manager.readout"
    assert readout_update.action == PM_TYPE_UPDATE
    assert readout_update.value.nested == {"pw": "pulse_window"}
    assert qubit_update.name == "parameter_manager.qubit"
    assert qubit_update.action == PM_TYPE_UPDATE
    assert qubit_update.value.effective["readout.pw.duration"] == {
        "unit": "s",
        "from_type": "pulse_window",
    }


def test_add_nested_type_emits_no_creation_for_kept_parameters(pm_with_sink):
    # the nested entry's parameter exists already at the target path: the
    # edit writes the Nested Type into the registry only, and the kept
    # parameter emits no parameter-creation (D22)
    pm, received = pm_with_sink
    put_nested_instance(pm)
    pm.add_type("pulse_window")
    pm.add_type_parameter("pulse_window", "duration", default=None, unit="s")
    pm.add_parameter("q01.readout.pw.duration", initial_value=500e-9, unit="s")
    received.clear()

    pm.add_nested_type("readout", "pw", "pulse_window")

    assert [bp.action for bp in received] == [PM_TYPE_UPDATE] * 2
    readout_update, qubit_update = received
    assert readout_update.name == "parameter_manager.readout"
    assert qubit_update.name == "parameter_manager.qubit"
    # the kept parameter kept its own value (D13)
    assert pm.get("q01.readout.pw.duration") == 500e-9


def test_remove_nested_type_emits_updates_for_the_edited_and_nesting_types(
    pm_with_sink,
):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    pm.add_type("pulse_window")
    pm.add_type_parameter("pulse_window", "duration", default=None, unit="s")
    pm.add_nested_type("readout", "pw", "pulse_window")
    received.clear()

    pm.remove_nested_type("readout", "pw")

    assert len(received) == 2
    readout_update, qubit_update = received
    assert readout_update.name == "parameter_manager.readout"
    assert readout_update.action == PM_TYPE_UPDATE
    assert readout_update.value.nested == {}
    assert qubit_update.name == "parameter_manager.qubit"
    assert qubit_update.action == PM_TYPE_UPDATE
    assert "readout.pw.duration" not in qubit_update.value.effective


def test_add_instance_emits_one_creation_per_created_parameter(pm_with_sink):
    pm, received = pm_with_sink
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    received.clear()

    pm.add_instance("qubit", "q01")

    # one parameter-creation per created parameter, in creation order;
    # add_instance edits no Type, so no pm-type-update goes out (D22)
    assert len(received) == 2
    first, second = received
    assert first.name == "parameter_manager.q01.IF"
    assert first.action == PARAMETER_CREATION
    assert first.value == 5e9
    assert first.unit == "Hz"
    assert second.name == "parameter_manager.q01.octave_gain"
    assert second.action == PARAMETER_CREATION
    assert second.value == 10
    assert second.unit == "dB"


def test_add_instance_emits_nothing_for_kept_parameters(pm_with_sink):
    pm, received = pm_with_sink
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_parameter("q01.IF", initial_value=6e9, unit="Hz")
    received.clear()

    pm.add_instance("qubit", "q01")

    # the kept q01.IF emits nothing; only the created octave_gain does
    assert len(received) == 1
    assert received[0].name == "parameter_manager.q01.octave_gain"
    assert received[0].action == PARAMETER_CREATION


def test_add_instance_of_an_empty_type_emits_nothing(pm_with_sink):
    pm, received = pm_with_sink
    pm.add_type("empty")
    received.clear()

    pm.add_instance("empty", "q01")

    # an empty Type creates nothing, so nothing is broadcast
    assert received == []
    assert pm.list() == []


def test_read_only_type_queries_emit_nothing(pm_with_sink):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    received.clear()

    assert pm.list_types() == ["readout", "qubit"]
    assert isinstance(pm.get_type("qubit"), PMTypeBluePrint)
    assert pm.instances_of("qubit") == ["q01"]
    assert pm.types_of("q01.octave_gain") == ["qubit"]

    assert received == []


def test_failed_type_validations_emit_nothing(pm_with_sink):
    pm, received = pm_with_sink
    put_nested_instance(pm)
    received.clear()

    # definitions
    with pytest.raises(ValueError):
        pm.add_type("_globals")
    with pytest.raises(ValueError):
        pm.add_type("readout")  # duplicate name
    with pytest.raises(ValueError):
        pm.remove_type("nope")
    with pytest.raises(ValueError):
        pm.remove_type("readout")  # nested in qubit
    # edits
    with pytest.raises(ValueError):
        pm.add_type_parameter("readout", "IF")  # already in the effective set
    with pytest.raises(ValueError):
        pm.add_type_parameter("nope", "x")
    with pytest.raises(ValueError):
        pm.remove_type_parameter("readout", "nope")
    with pytest.raises(ValueError):
        pm.set_type_parameter_default("readout", "nope", 1)
    with pytest.raises(ValueError):
        pm.set_type_parameter_unit("readout", "nope", "V")
    # nesting
    with pytest.raises(ValueError):
        pm.add_nested_type("readout", "self", "readout")
    with pytest.raises(ValueError):
        pm.add_nested_type("qubit", "readout", "readout")  # occupied submodule
    with pytest.raises(ValueError):
        pm.add_nested_type("qubit", "_globals", "readout")
    with pytest.raises(ValueError):
        pm.remove_nested_type("readout", "pw")  # no Nested Type there
    # instances
    with pytest.raises(ValueError):
        pm.add_instance("nope", "q09")
    with pytest.raises(ValueError):
        pm.add_instance("qubit", "_globals")
    with pytest.raises(ValueError):
        pm.add_instance("qubit", "")
    pm.add_parameter("q09.octave_gain", initial_value=1, unit="V")
    with pytest.raises(ValueError):
        pm.add_instance("qubit", "q09")  # unit conflict on q09.octave_gain
    pm.add_parameter("q10.octave_gain.sub", initial_value=0, unit="s")
    with pytest.raises(ValueError):
        pm.add_instance("qubit", "q10")  # target q10.octave_gain is a Parameter Group

    assert received == []


def test_type_broadcast_payloads_are_snapshots_of_their_time(pm_with_sink):
    # every pm-type-update carries a blueprint built at emit time: a sink
    # that keeps payloads must not see an earlier Type grow when entries
    # are added later
    pm, received = pm_with_sink

    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=5e9, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")

    assert len(received) == 3
    first, second, third = (bp.value for bp in received)
    assert isinstance(first, PMTypeBluePrint)
    assert first.parameters == {}
    assert list(second.parameters) == ["IF"]
    assert list(third.parameters) == ["IF", "octave_gain"]


# ---------------------------------------------------------------------------
# Type API and Broadcasts through a client proxy against a live Server
# (plan task 2.5)
#
# The Server registers itself as a Broadcast sink on the Parameter Manager
# (task 0.3), so every Type-editing method call over the wire also emits
# its Broadcasts on the PUB socket. The server-side Parameter Manager is
# shared by all tests of this module, so every test removes the parameters
# and Types it created again.
# ---------------------------------------------------------------------------

PROXY_TYPE = "ptype_qubit"
PROXY_NESTED_TYPE = "ptype_readout"
PROXY_INSTANCE = "ptype_q01"


def _cleanup_proxy_types(params):
    """Remove every parameter and Type the proxy tests create, so the
    module's shared server-side Parameter Manager starts each test clean.
    ``remove_type`` refuses while a Type nests another, so the nested map
    is emptied and the outer Type is removed first."""
    for path in list(params.list()):
        if path.split(".")[0].startswith("ptype_"):
            params.remove_parameter(path)
    for name in (PROXY_TYPE, PROXY_NESTED_TYPE):
        if name in params.list_types():
            bp = params.get_type(name)
            for submodule in list(bp.nested):
                params.remove_nested_type(name, submodule)
            params.remove_type(name)


def test_every_type_method_is_callable_through_the_proxy(param_manager):
    cli, params = param_manager
    _cleanup_proxy_types(params)
    try:
        params.add_type(PROXY_NESTED_TYPE)
        params.add_type_parameter(PROXY_NESTED_TYPE, "IF", default=10e6, unit="Hz")
        params.add_type(PROXY_TYPE)
        params.add_type_parameter(PROXY_TYPE, "octave_gain", default=10, unit="dB")
        params.add_nested_type(PROXY_TYPE, "ro", PROXY_NESTED_TYPE)

        assert sorted(params.list_types()) == [PROXY_TYPE, PROXY_NESTED_TYPE]

        params.set_type_parameter_default(PROXY_NESTED_TYPE, "IF", 20e6)
        params.set_type_parameter_unit(PROXY_NESTED_TYPE, "IF", "V")

        params.add_instance(PROXY_NESTED_TYPE, PROXY_INSTANCE)
        assert params.instances_of(PROXY_NESTED_TYPE) == [PROXY_INSTANCE]
        assert params.types_of(f"{PROXY_INSTANCE}.IF") == [PROXY_NESTED_TYPE]
        # the proxy method call does not refresh the proxy itself: after
        # update() the created Instance shows up with the entry default
        # and the propagated unit
        params.update()
        assert params.ptype_q01.IF() == 20e6
        assert params.ptype_q01.IF.unit == "V"

        # the removals work over the wire too
        params.remove_type_parameter(PROXY_NESTED_TYPE, "IF")
        assert params.get_type(PROXY_NESTED_TYPE).parameters == {}
        params.remove_nested_type(PROXY_TYPE, "ro")
        assert params.get_type(PROXY_TYPE).nested == {}
        params.remove_type(PROXY_TYPE)
        params.remove_type(PROXY_NESTED_TYPE)
        assert params.list_types() == []
    finally:
        _cleanup_proxy_types(params)


def test_get_type_and_list_types_deserialise_over_the_wire(param_manager):
    cli, params = param_manager
    _cleanup_proxy_types(params)
    try:
        params.add_type(PROXY_NESTED_TYPE)
        params.add_type_parameter(PROXY_NESTED_TYPE, "IF", default=10e6, unit="Hz")
        params.add_type(PROXY_TYPE)
        params.add_type_parameter(PROXY_TYPE, "octave_gain", default=10, unit="dB")
        params.add_nested_type(PROXY_TYPE, "ro", PROXY_NESTED_TYPE)

        types = params.list_types()
        assert isinstance(types, list)
        assert sorted(types) == [PROXY_TYPE, PROXY_NESTED_TYPE]

        bp = params.get_type(PROXY_TYPE)
        assert isinstance(bp, PMTypeBluePrint)
        assert bp.name == PROXY_TYPE
        assert bp.parameters == {
            "octave_gain": {"default": 10, "unit": "dB", "target": None},
        }
        assert bp.nested == {"ro": PROXY_NESTED_TYPE}
        assert bp.effective == {
            "octave_gain": {"unit": "dB", "from_type": PROXY_TYPE},
            "ro.IF": {"unit": "Hz", "from_type": PROXY_NESTED_TYPE},
        }

        nested_bp = params.get_type(PROXY_NESTED_TYPE)
        assert isinstance(nested_bp, PMTypeBluePrint)
        assert nested_bp.parameters == {
            "IF": {"default": 10e6, "unit": "Hz", "target": None},
        }
    finally:
        _cleanup_proxy_types(params)


def test_subclient_sees_pm_type_update_and_creations_from_a_second_client(
    param_manager, server_port, capture_broadcasts, wait_for_broadcasts
):
    cli, params = param_manager
    _cleanup_proxy_types(params)
    second_cli = Client(port=server_port)
    try:
        second_params = second_cli.find_or_create_instrument(
            "parameter_manager", "instrumentserver.params.ParameterManager"
        )
        with capture_broadcasts(["parameter_manager"], server_port + 1) as received:
            # a Type edit from the second client: the SubClient sees the
            # pm-type-update with the fresh blueprint
            second_params.add_type(PROXY_NESTED_TYPE)
            wait_for_broadcasts(received)
            assert len(received) == 1
            bp = received[0]
            assert isinstance(bp, ParameterBroadcastBluePrint)
            assert bp.name == f"parameter_manager.{PROXY_NESTED_TYPE}"
            assert bp.action == PM_TYPE_UPDATE
            assert isinstance(bp.value, PMTypeBluePrint)
            assert bp.value.parameters == {}

            second_params.add_type_parameter(
                PROXY_NESTED_TYPE, "IF", default=5, unit="Hz"
            )
            wait_for_broadcasts(received, n=2)
            assert len(received) == 2
            assert received[1].action == PM_TYPE_UPDATE
            assert received[1].value.parameters == {
                "IF": {"default": 5, "unit": "Hz", "target": None},
            }
            received.clear()

            # add_instance from the second client: exactly one
            # parameter-creation per created parameter, and no
            # pm-type-update, since the call edits no Type
            second_params.add_instance(PROXY_NESTED_TYPE, PROXY_INSTANCE)
            wait_for_broadcasts(received)
            assert len(received) == 1
            creation = received[0]
            assert creation.action == PARAMETER_CREATION
            assert creation.name == f"parameter_manager.{PROXY_INSTANCE}.IF"
            assert creation.value == 5
            assert creation.unit == "Hz"
    finally:
        second_cli.disconnect()
        _cleanup_proxy_types(params)


def test_the_first_clients_proxy_shows_the_created_parameters_after_update(
    param_manager, server_port
):
    cli, params = param_manager
    _cleanup_proxy_types(params)
    second_cli = Client(port=server_port)
    try:
        second_params = second_cli.find_or_create_instrument(
            "parameter_manager", "instrumentserver.params.ParameterManager"
        )
        # the second client adds the Type, one entry and an Instance
        second_params.add_type(PROXY_TYPE)
        second_params.add_type_parameter(PROXY_TYPE, "IF", default=5, unit="Hz")
        second_params.add_instance(PROXY_TYPE, PROXY_INSTANCE)

        # the first client's proxy predates the creations
        assert PROXY_INSTANCE not in params.submodules

        # update() invalidates the cached blueprint and rebuilds the proxy
        params.update()
        assert PROXY_INSTANCE in params.submodules
        assert params.ptype_q01.IF() == 5
        assert params.ptype_q01.IF.unit == "Hz"
    finally:
        second_cli.disconnect()
        _cleanup_proxy_types(params)
