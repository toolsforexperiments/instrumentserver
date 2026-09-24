"""Tests for the Type registry and definitions (plan task 2.1).

The public ``add_type`` / ``remove_type`` / ``list_types`` / ``get_type``
methods are exercised directly. The editing methods for entries and Nested
Types arrive with plan task 2.3, so the tests that need Types with entries
or nesting insert their ``_TypeDefinition`` registry records by hand.
Covered: creating, listing, getting and removing Types (with the reserved
Globals name and duplicate-name refusals), the effective parameter set
expansion of Nested Types (cycle refusal, collision refusal), and the
content of the ``PMTypeBluePrint`` ``get_type`` returns, including its
round-trip through the blueprint serialization.
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
