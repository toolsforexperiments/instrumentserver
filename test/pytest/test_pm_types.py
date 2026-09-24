"""Tests for the Type registry and definitions (plan task 2.1) and for
the duck-typed Instance matching (plan task 2.2).

The public ``add_type`` / ``remove_type`` / ``list_types`` / ``get_type``
methods are exercised directly. The editing methods for entries and Nested
Types arrive with plan task 2.3, so the tests that need Types with entries
or nesting insert their ``_TypeDefinition`` registry records by hand.
Covered: creating, listing, getting and removing Types (with the reserved
Globals name and duplicate-name refusals), the effective parameter set
expansion of Nested Types (cycle refusal, collision refusal), the content
of the ``PMTypeBluePrint`` ``get_type`` returns, its round-trip through
the blueprint serialization, and the Instance matching queries
``instances_of`` and ``types_of`` (existence and unit, any depth, never
the root, never the Globals submodule, ordering of the claiming Types).
"""

import re

import pytest

from instrumentserver.blueprints import PMTypeBluePrint, deserialize_obj
from instrumentserver.params import ParameterManager, _TypeDefinition, _TypeEntry


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """A fresh Parameter Manager in an empty working directory."""
    monkeypatch.chdir(tmp_path)
    return ParameterManager(name="parameter_manager")


def put_type(pm, name, parameters=None, nested=None):
    """Insert a ``_TypeDefinition`` into the registry directly: the public
    editing API for entries and Nested Types arrives with plan task 2.3."""
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
    put_type(
        pm,
        "qubit",
        parameters={
            "IF": {"default": None, "unit": "Hz"},
            "octave_gain": {"default": 10, "unit": "dB"},
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
        nested={"pw": "pulse_window"},
    )
    put_type(
        pm,
        "pulse_window",
        parameters={"duration": {"default": None, "unit": "s"}},
    )


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
    put_type(pm, "readout", parameters={"IF": {"default": None, "unit": "Hz"}})
    put_type(pm, "qubit", nested={"readout": "readout"})

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
    put_type(pm, "readout")
    put_type(pm, "qubit", nested={"readout": "readout"})
    put_type(pm, "qubit2", nested={"readout": "readout"})

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
    put_type(pm, "readout", parameters={"IF": {"default": None, "unit": "Hz"}})
    put_type(pm, "qubit", nested={"readout": "readout"})

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
    put_type(pm, "readout", parameters={"IF": {"default": None, "unit": "Hz"}})
    put_type(pm, "qubit", nested={"ro1": "readout", "ro2": "readout"})

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
    put_type(
        pm,
        "qubit",
        parameters={
            "IF": {"default": None, "unit": "Hz"},
            "octave_gain": {"default": 10, "unit": "dB"},
        },
    )
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
    put_type(pm, "qubit", parameters={"IF": {"default": None, "unit": "Hz"}})
    pm.add_parameter("q01.IF", unit="Hz")
    # extra parameters and extra Parameter Groups change nothing
    pm.add_parameter("q01.extra", unit="dB")
    pm.add_parameter("q01.sub.extra", unit="s")

    assert pm.instances_of("qubit") == ["q01"]
    assert pm.types_of("q01.IF") == ["qubit"]


def test_two_types_on_one_submodule(pm):
    put_type(
        pm,
        "readout",
        parameters={
            "IF": {"default": None, "unit": "Hz"},
            "window": {"default": None, "unit": "s"},
        },
    )
    put_type(pm, "ro_small", parameters={"IF": {"default": None, "unit": "Hz"}})
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
    put_type(pm, "ro_b", parameters={"IF": {"default": None, "unit": "Hz"}})
    put_type(pm, "ro_a", parameters={"IF": {"default": None, "unit": "Hz"}})
    pm.add_parameter("q01.readout.IF", unit="Hz")

    assert pm.types_of("q01.readout.IF") == ["ro_a", "ro_b"]


def test_an_empty_type_has_no_instances(pm):
    pm.add_type("empty")
    pm.add_parameter("q01.anything", unit="Hz")

    assert pm.instances_of("empty") == []


def test_the_root_is_never_an_instance(pm):
    put_type(pm, "flat", parameters={"IF": {"default": None, "unit": "Hz"}})
    pm.add_parameter("IF", unit="Hz")
    pm.add_parameter("under_group.IF", unit="Hz")

    # the root carries the shape but is not a submodule: only under_group
    # is an Instance, and the root parameter is claimed by nothing
    assert pm.instances_of("flat") == ["under_group"]
    assert pm.types_of("IF") == []


def test_nothing_under_the_globals_submodule_matches(pm):
    put_type(pm, "qubit", parameters={"IF": {"default": None, "unit": "Hz"}})
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
    put_type(
        pm,
        "qubit",
        parameters={
            "IF": {"default": None, "unit": "Hz"},
            "octave_gain": {"default": 10, "unit": "dB"},
        },
    )
    pm.add_parameter("q01.IF", initial_value=1, unit="Hz")
    pm.add_parameter("q01.octave_gain", initial_value=999, unit="dB")
    pm.add_parameter("q02.IF", initial_value=5e9, unit="Hz")
    pm.add_parameter("q02.octave_gain", initial_value=0, unit="dB")

    # the values differ wildly between the two Instances; both match
    assert sorted(pm.instances_of("qubit")) == ["q01", "q02"]


def test_a_type_nested_at_two_submodules_matches_only_whole_carriers(pm):
    put_type(pm, "readout", parameters={"IF": {"default": None, "unit": "Hz"}})
    put_type(pm, "qubit", nested={"ro1": "readout", "ro2": "readout"})
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
