"""Tests for the Parameter Manager's version-2 persistence (plan tasks
4.1 and 4.2).

The writer part checks the document :meth:`ParameterManager.toParamDict`
produces (plan decision D19): ``version`` 2, ``parameters`` keyed by full
dotted paths with the own values, the per-Follower ``lock`` entries and the
``types`` section, the file dump format, and validity against
``schemas/parameter_manager_v2.json``. The reader part checks
:meth:`ParameterManager.fromParamDict`/:meth:`ParameterManager.fromFile`:
the legacy flat map still loads (parameters only), a version-2 document is
validated as a whole — refused with every problem named, state untouched —
and then loads in D20's order (the Locks of the listed parameters, the
parameters, the Types without Instance side effects, the Locks), with the
load's Broadcasts emitted once after it succeeded. All tests are unit tests
on a local Parameter Manager with no Server involved.
"""

import json
import re
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from instrumentserver import PM_V2_SCHEMA_PATH
from instrumentserver.blueprints import (
    PARAMETER_CREATION,
    PARAMETER_DELETION,
    PM_LOCK_UPDATE,
    PM_TYPE_UPDATE,
    PMLockBluePrint,
)
from instrumentserver.params import ManagedParameter, ParameterManager

FIXTURES = Path(__file__).parent / "fixtures"


def make_populated_manager(name="params"):
    """A local Parameter Manager with a nested parameter and Types with
    entries and a Nested Type, covering the writer's ``types`` section."""
    pm = ParameterManager(name=name)
    pm.add_parameter(name="my_param", initial_value=123, unit="M")
    pm.add_parameter(name="nested_param.child", initial_value=456, unit="a")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_type("readout")
    pm.add_type_parameter("readout", "power", default=-10, unit="dBm")
    pm.add_nested_type("qubit", "readout", "readout")
    return pm


# ---------------------------------------------------------------------------
# Writer: the version-2 document (D19)
# ---------------------------------------------------------------------------


def test_document_has_version_two_and_full_path_keys(tmp_path):
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path

    doc = pm.toParamDict()

    assert doc["version"] == 2
    assert set(doc["parameters"]) == {
        "params.my_param",
        "params.nested_param.child",
    }
    assert doc["parameters"]["params.my_param"] == {"value": 123, "unit": "M"}
    assert doc["parameters"]["params.nested_param.child"] == {
        "value": 456,
        "unit": "a",
    }


def test_simple_format_argument_is_ignored_by_the_writer(tmp_path):
    """A version-2 document always stores the per-parameter dict, whatever
    ``simpleFormat`` says."""
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path

    assert pm.toParamDict(simpleFormat=True) == pm.toParamDict()


def test_include_meta_selects_the_per_parameter_metadata(tmp_path):
    """``includeMeta`` still selects the per-parameter metadata besides
    ``value``; a Follower carries its ``lock`` entry whatever
    ``includeMeta`` selects."""
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")

    doc = pm.toParamDict(includeMeta=[])
    assert doc["parameters"]["params.my_param"] == {"value": 123}
    assert doc["parameters"]["params.q01.IF"]["lock"] == {
        "target": "params.q01Data.IF",
        "locked": True,
    }

    doc = pm.toParamDict(includeMeta=["unit", "label"])
    entry = doc["parameters"]["params.my_param"]
    assert entry["value"] == 123
    assert entry["unit"] == "M"
    assert "label" in entry


def test_locked_follower_saves_its_own_value_and_the_lock(tmp_path):
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")

    # pull on get: the live Follower answers with the Target's value
    assert pm.get("q01.IF") == 42e6

    doc = pm.toParamDict()
    entry = doc["parameters"]["params.q01.IF"]
    assert entry["value"] == 101735237.0
    assert entry["lock"] == {"target": "params.q01Data.IF", "locked": True}
    # the Target itself carries no Lock and so no lock entry
    assert "lock" not in doc["parameters"]["params.q01Data.IF"]


def test_unlocked_follower_stores_locked_false(tmp_path):
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")
    pm.unlock("q01.IF")

    entry = pm.toParamDict()["parameters"]["params.q01.IF"]
    assert entry["value"] == 101735237.0
    assert entry["lock"] == {"target": "params.q01Data.IF", "locked": False}


def test_parameter_without_a_lock_has_no_lock_key(tmp_path):
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path

    for path, entry in pm.toParamDict()["parameters"].items():
        assert "lock" not in entry, path


def test_globals_parameter_is_saved(tmp_path):
    """A Globals parameter is saved like any other (D18), with its own
    value and unit."""
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    # declaring the Type Lock creates the default Globals Target on demand
    pm.lock_type_parameter("qubit", "octave_gain")
    pm.set("_globals.qubit.octave_gain", 33)

    entry = pm.toParamDict()["parameters"]["params._globals.qubit.octave_gain"]
    assert entry == {"value": 33, "unit": "dB"}


def test_types_section_holds_every_type_with_entries_and_nested(tmp_path):
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path

    types = pm.toParamDict()["types"]
    assert types == {
        "qubit": {
            "parameters": {
                "IF": {"default": None, "unit": "Hz", "target": None},
                "octave_gain": {"default": 10, "unit": "dB", "target": None},
            },
            "nested": {"readout": "readout"},
        },
        "readout": {
            "parameters": {
                "power": {"default": -10, "unit": "dBm", "target": None},
            },
            "nested": {},
        },
    }


def test_type_lock_target_is_stored_in_full_form(tmp_path):
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    pm.lock_type_parameter("qubit", "octave_gain")

    doc = pm.toParamDict()
    entry = doc["types"]["qubit"]["parameters"]["octave_gain"]
    assert entry["target"] == "params._globals.qubit.octave_gain"
    # declaring the Type Lock created the default Globals Target on demand;
    # with no Instance, no parameter entry carries a lock
    assert doc["parameters"]["params._globals.qubit.octave_gain"]["value"] == 10
    for parameter_entry in doc["parameters"].values():
        assert "lock" not in parameter_entry


def test_no_types_give_an_empty_types_section(tmp_path):
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="my_param", initial_value=123, unit="M")

    assert pm.toParamDict()["types"] == {}


def test_written_file_is_valid_against_the_v2_schema(tmp_path):
    """The file a toFile call writes is valid against
    schemas/parameter_manager_v2.json — with Followers in both Lock
    states, a Globals parameter and a full types section in it."""
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")
    pm.lock_type_parameter("qubit", "octave_gain")
    pm.unlock("q01.IF")

    file_path = tmp_path / "parameter_manager-params.json"
    pm.toFile(str(file_path))
    with open(file_path) as f:
        written = json.load(f)

    with open(PM_V2_SCHEMA_PATH) as f:
        schema = json.load(f)
    validate(written, schema)


def test_file_is_dumped_with_indent_two_and_sorted_keys(tmp_path):
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")

    doc = pm.toParamDict()
    file_path = tmp_path / "parameter_manager-params.json"
    pm.toFile(str(file_path))

    assert file_path.read_text() == json.dumps(doc, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Reader shim (4.1): legacy flat map, version-2 parameters, refusals
# ---------------------------------------------------------------------------


def test_legacy_flat_file_still_loads(tmp_path):
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="old", initial_value=0, unit="u")

    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps({"params.legacy": {"value": 5, "unit": "V"}}))
    pm.fromFile(str(legacy_path))

    assert pm.legacy() == 5
    assert pm.legacy.unit == "V"
    # deleteMissing semantics of the legacy reader are unchanged
    assert not pm.has_param("old")


def test_legacy_simple_format_file_still_loads(tmp_path):
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path

    legacy_path = tmp_path / "legacy_simple.json"
    legacy_path.write_text(json.dumps({"params.sp": 7}))
    pm.fromFile(str(legacy_path))

    assert pm.sp() == 7


def test_legacy_flat_file_creates_a_globals_parameter_on_load(tmp_path):
    """A legacy flat file holding a ``_globals.*`` key creates the Globals
    parameter on load, through the internal creation path: create-on-load
    is the intended behaviour for both file formats (D18; TEST_AUDIT.md,
    "Profiles — loading Globals parameters")."""
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path

    legacy_path = tmp_path / "legacy_globals.json"
    legacy_path.write_text(
        json.dumps({"params._globals.x.y": {"value": 1, "unit": "u"}})
    )
    pm.fromFile(str(legacy_path))

    assert pm.has_param("_globals.x.y")
    assert pm.get("_globals.x.y") == 1
    param = pm.parameter("_globals.x.y")
    assert param.unit == "u"
    assert isinstance(param, ManagedParameter)
    assert param.path == "params._globals.x.y"


def test_version_two_file_round_trips_through_from_file(tmp_path, monkeypatch):
    """A version-2 file written by toFile loads its parameters back —
    values and units — through fromFile."""
    monkeypatch.chdir(tmp_path)
    pm = make_populated_manager()
    pm.toFile(name="params")

    pm2 = ParameterManager(name="params")

    assert pm2.my_param() == 123
    assert pm2.my_param.unit == "M"
    assert pm2.nested_param.child() == 456
    assert pm2.nested_param.child.unit == "a"


def test_globals_parameter_round_trips_through_the_internal_path(tmp_path):
    """A saved Globals parameter loads back: the reader creates it through
    the internal creation path, since the public add_parameter refuses the
    Globals name (D18; TEST_AUDIT.md, "Profiles — loading Globals
    parameters")."""
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    pm.lock_type_parameter("qubit", "octave_gain")
    pm.set("_globals.qubit.octave_gain", 33)
    pm.toFile(tmp_path, "globals")

    pm2 = ParameterManager(name="params")
    pm2.fromFile(str(tmp_path / "parameter_manager-globals.json"))

    assert pm2.has_param("_globals.qubit.octave_gain")
    assert pm2.get("_globals.qubit.octave_gain") == 33
    assert pm2.parameter("_globals.qubit.octave_gain").unit == "dB"


def test_delete_missing_semantics_are_unchanged_on_a_version_two_load(tmp_path):
    pm = ParameterManager(name="params")
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="a", initial_value=1, unit="u")
    pm.add_parameter(name="b", initial_value=2, unit="v")
    pm.toFile(tmp_path, "dm")

    pm.add_parameter(name="c", initial_value=3, unit="w")
    pm.fromFile(str(tmp_path / "parameter_manager-dm.json"))
    assert pm.a() == 1
    assert pm.b() == 2
    assert not pm.has_param("c")

    pm.add_parameter(name="c", initial_value=3, unit="w")
    with open(tmp_path / "parameter_manager-dm.json") as f:
        doc = json.load(f)
    pm.fromParamDict(doc, deleteMissing=False)
    assert pm.has_param("c")
    assert pm.c() == 3


def test_the_shim_ignores_the_lock_and_types_sections(tmp_path):
    """The reader shim loads only the parameters map: the file may carry
    ``lock`` entries and a ``types`` section, the parameters load with
    their own values and units, and nothing about the Locks or Types is
    pinned here (task 4.2 restores them)."""
    pm = make_populated_manager()
    pm.workingDirectory = tmp_path
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")
    pm.lock_type_parameter("qubit", "octave_gain")
    pm.unlock("q01.IF")
    pm.toFile(tmp_path, "shim")

    pm2 = ParameterManager(name="params")
    pm2.fromFile(str(tmp_path / "parameter_manager-shim.json"))

    assert pm2.get("q01.IF") == 101735237.0
    assert pm2.parameter("q01.IF").unit == "Hz"
    assert pm2.get("q01Data.IF") == 42e6
    assert pm2.has_param("_globals.qubit.octave_gain")


def test_unsupported_version_raises_value_error_naming_it():
    pm = ParameterManager(name="params")

    with pytest.raises(ValueError, match=re.escape("3")):
        pm.fromParamDict({"version": 3, "parameters": {}, "types": {}})
    with pytest.raises(ValueError, match=re.escape("'2'")):
        pm.fromParamDict({"version": "2", "parameters": {}, "types": {}})
    # nothing was loaded into the Parameter Manager
    assert pm.list() == []


def test_invalid_document_is_refused_by_the_schema():
    pm = ParameterManager(name="params")
    pm.add_parameter(name="a", initial_value=1, unit="u")
    pm.add_parameter(name="b", initial_value=2, unit="v")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    good = pm.toParamDict()

    lock_missing_locked = json.loads(json.dumps(good))
    lock_missing_locked["parameters"]["params.a"]["lock"] = {"target": "params.b"}
    with pytest.raises(ValidationError):
        pm.fromParamDict(lock_missing_locked)

    entry_without_value = json.loads(json.dumps(good))
    del entry_without_value["parameters"]["params.b"]["value"]
    with pytest.raises(ValidationError):
        pm.fromParamDict(entry_without_value)

    # a per-parameter key the v2 schema does not know is refused by the
    # parameters.json leg of validateParameterManagerV2
    bad_vals = json.loads(json.dumps(good))
    bad_vals["parameters"]["params.a"]["vals"] = 42
    with pytest.raises(ValidationError):
        pm.fromParamDict(bad_vals)

    # the top-level keys of the version-2 document are required
    without_types = json.loads(json.dumps(good))
    del without_types["types"]
    with pytest.raises(ValidationError):
        pm.fromParamDict(without_types)

    # a Type entry carries exactly default, unit and target
    type_entry_missing_target = json.loads(json.dumps(good))
    del type_entry_missing_target["types"]["qubit"]["parameters"]["IF"]["target"]
    with pytest.raises(ValidationError):
        pm.fromParamDict(type_entry_missing_target)

    # the refused documents changed nothing
    assert pm.a() == 1
    assert pm.b() == 2
    assert pm.list_types() == ["qubit"]


# ---------------------------------------------------------------------------
# Reader (4.2): the version-2 load in D20's order
# ---------------------------------------------------------------------------


def make_lock_and_type_manager(name="params"):
    """A Parameter Manager exercising the whole version-2 document: Types
    (one nesting another), Type Locks with the default Globals Target and
    an explicit Target, Locks locked and unlocked, a chain, own values
    differing from the Target values, and a Globals parameter. The Types
    are completed before the parameters exist, so no submodule carries
    the whole shape and none is an Instance (D12)."""
    pm = ParameterManager(name=name)
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")
    pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
    pm.add_type("readout")
    pm.add_type_parameter("readout", "power", default=-10, unit="dBm")
    pm.add_nested_type("qubit", "readout", "readout")
    # the Type Lock with the default Globals Target, which creates the
    # Globals parameter on demand
    pm.lock_type_parameter("qubit", "octave_gain")
    pm.add_parameter(name="q01.IF", initial_value=101735237.0, unit="Hz")
    pm.add_parameter(name="q01Data.IF", initial_value=42e6, unit="Hz")
    pm.add_parameter(name="q02.IF", initial_value=101735238.0, unit="Hz")
    pm.add_parameter(name="q03.sp", initial_value=1.5, unit="V")
    # the Type Lock with an explicit Target
    pm.lock_type_parameter("qubit", "IF", target="q01Data.IF")
    # a locked chain q03.sp -> q02.IF -> q01.IF -> q01Data.IF, with the
    # last hop unlocked, and own values differing from the Target's
    pm.lock("q01.IF", "q01Data.IF")
    pm.lock("q02.IF", "q01.IF")
    pm.lock("q03.sp", "q02.IF")
    pm.unlock("q03.sp")
    return pm


def test_legacy_fixture_file_loads_values_and_units():
    """The checked-in legacy fixture (a flat map with a nested path and a
    unit) loads through fromFile with values and units."""
    pm = ParameterManager(name="parameter_manager")
    pm.fromFile(str(FIXTURES / "parameter_manager-legacy.json"))

    assert pm.my_param() == 123
    assert pm.my_param.unit == "M"
    assert pm.nested_param.child() == 456
    assert pm.nested_param.child.unit == "a"


def test_legacy_load_leaves_types_and_locks_untouched():
    """The legacy flat map loads parameters only. The locked parameter is
    not listed (a legacy load sets every listed parameter, and a locked
    Follower refuses set, D6), so with ``deleteMissing=False`` the load
    touches neither the Lock nor the Types."""
    pm = ParameterManager(name="params")
    pm.add_parameter("a", initial_value=1, unit="u")
    pm.add_parameter("b", initial_value=2, unit="v")
    pm.lock("a", "b")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")

    pm.fromParamDict({"params.b": {"value": 22, "unit": "v"}}, deleteMissing=False)

    assert pm.get("b") == 22
    assert pm.parameter("a").own_value() == 1
    assert pm.get_lock("a") == PMLockBluePrint(target="params.b", locked=True)
    assert pm.list_types() == ["qubit"]


def test_version_two_document_round_trips_exactly(tmp_path):
    """A manager with Types, Type Locks, Locks in both states, a chain and
    a Globals parameter saves, loads into a fresh manager, and both
    produce the same document; the loaded Followers pull on get and keep
    their own values."""
    pm = make_lock_and_type_manager()
    pm.toFile(str(tmp_path / "parameter_manager-rt.json"))

    pm2 = ParameterManager(name="params")
    pm2.fromFile(str(tmp_path / "parameter_manager-rt.json"))

    assert pm2.toParamDict() == pm.toParamDict()
    # no Instance side effects: q01 carries only IF and is not completed
    # into an Instance by the loaded Type (D20)
    assert not pm2.has_param("q01.octave_gain")
    assert pm2.instances_of("qubit") == []
    # pull on get through the chain: q03.sp is unlocked (its own value),
    # q02.IF is locked and reads q01.IF, which is locked and reads the
    # Target q01Data.IF (D7)
    assert pm2.get("q02.IF") == 42e6
    assert pm2.parameter("q02.IF").own_value() == 101735238.0
    assert pm2.get("q03.sp") == 1.5
    assert pm2.get_lock("q03.sp") == PMLockBluePrint(
        target="params.q02.IF", locked=False
    )
    assert pm2.get_lock("q01.IF") == PMLockBluePrint(
        target="params.q01Data.IF", locked=True
    )


def test_missing_targets_are_all_named_and_change_nothing():
    """A document whose Lock Target and Type Lock Target point at absent
    keys is refused with every missing Target named — both kinds, in one
    message — leaving the previous state intact and emitting nothing."""
    pm = ParameterManager(name="params")
    pm.add_parameter("a", initial_value=1, unit="u")
    pm.add_parameter("b", initial_value=2, unit="v")
    pm.add_parameter("q01.IF", initial_value=1e9, unit="Hz")
    pm.lock("a", "b")
    pm.add_type("qubit")
    pm.add_type_parameter("qubit", "IF", default=None, unit="Hz")

    before_list = pm.list()
    before_values = {path: pm.get(path) for path in before_list}
    before_locks = pm.list_locks()
    before_types = pm.list_types()
    before_type = pm.get_type("qubit")

    received = []
    pm.add_broadcast_sink(received.append)

    doc = {
        "version": 2,
        "parameters": {
            "params.a": {
                "value": 10,
                "unit": "u",
                "lock": {"target": "params.ghost1", "locked": True},
            },
            "params.b": {"value": 20, "unit": "v"},
            "params.q01.IF": {"value": 2e9, "unit": "Hz"},
        },
        "types": {
            "qubit": {
                "parameters": {
                    "IF": {
                        "default": None,
                        "unit": "Hz",
                        "target": "params.ghost2",
                    }
                },
                "nested": {},
            }
        },
    }
    with pytest.raises(ValueError) as excinfo:
        pm.fromParamDict(doc)

    message = str(excinfo.value)
    assert "params.ghost1" in message
    assert "params.ghost2" in message
    assert "the Lock on Follower 'params.a'" in message
    assert "the Type Lock on 'qubit.IF'" in message

    # the previous state is untouched and nothing was emitted
    assert pm.list() == before_list
    assert {path: pm.get(path) for path in before_list} == before_values
    assert pm.list_locks() == before_locks
    assert pm.list_types() == before_types
    assert pm.get_type("qubit") == before_type
    assert received == []


def test_nested_types_missing_from_the_document_are_refused_up_front():
    """A Nested Type that no Type of the document defines is refused
    before anything is loaded, with every offender named."""
    pm = ParameterManager(name="params")
    doc = {
        "version": 2,
        "parameters": {},
        "types": {
            "qubit": {"parameters": {}, "nested": {"readout": "ghost_readout"}},
            "pulse": {"parameters": {}, "nested": {"win": "ghost_window"}},
        },
    }
    with pytest.raises(ValueError) as excinfo:
        pm.fromParamDict(doc)

    message = str(excinfo.value)
    assert "ghost_readout" in message
    assert "ghost_window" in message
    assert pm.list() == []
    assert pm.list_types() == []


def test_a_nested_type_cycle_in_the_document_is_refused_up_front():
    pm = ParameterManager(name="params")
    doc = {
        "version": 2,
        "parameters": {},
        "types": {
            "qubit": {"parameters": {}, "nested": {"readout": "readout"}},
            "readout": {"parameters": {}, "nested": {"qubit": "qubit"}},
        },
    }
    with pytest.raises(ValueError) as excinfo:
        pm.fromParamDict(doc)

    assert "qubit -> readout -> qubit" in str(excinfo.value)
    assert pm.list_types() == []


def test_a_duplicated_effective_path_in_the_document_is_refused_up_front():
    """A Type whose own entry collides with a Nested Type's entry in its
    effective set is refused before anything is loaded."""
    pm = ParameterManager(name="params")
    doc = {
        "version": 2,
        "parameters": {},
        "types": {
            "readout": {
                "parameters": {
                    "power": {"default": -10, "unit": "dBm", "target": None}
                },
                "nested": {},
            },
            "qubit": {
                "parameters": {
                    "readout.power": {
                        "default": None,
                        "unit": "dBm",
                        "target": None,
                    }
                },
                "nested": {"readout": "readout"},
            },
        },
    }
    with pytest.raises(ValueError) as excinfo:
        pm.fromParamDict(doc)

    assert "readout.power" in str(excinfo.value)
    assert pm.list_types() == []


def test_a_lock_cycle_in_the_document_is_refused_up_front():
    pm = ParameterManager(name="params")
    pm.add_parameter("a", initial_value=1, unit="u")
    pm.add_parameter("b", initial_value=2, unit="v")
    pm.lock("a", "b")  # the in-session Lock the refused load must not disturb
    doc = {
        "version": 2,
        "parameters": {
            "params.a": {
                "value": 1,
                "unit": "u",
                "lock": {"target": "params.b", "locked": True},
            },
            "params.b": {
                "value": 2,
                "unit": "v",
                "lock": {"target": "params.a", "locked": True},
            },
        },
        "types": {},
    }
    with pytest.raises(ValueError) as excinfo:
        pm.fromParamDict(doc)

    message = str(excinfo.value)
    assert "params.a" in message
    assert "params.b" in message
    assert "cycle in Lock targets" in message
    assert pm.get_lock("a") == PMLockBluePrint(target="params.b", locked=True)
    assert pm.get_lock("b") is None


def test_a_self_lock_in_the_document_is_refused_up_front():
    pm = ParameterManager(name="params")
    pm.add_parameter("a", initial_value=1, unit="u")
    doc = {
        "version": 2,
        "parameters": {
            "params.a": {
                "value": 1,
                "unit": "u",
                "lock": {"target": "params.a", "locked": True},
            }
        },
        "types": {},
    }
    with pytest.raises(ValueError, match="cannot lock params.a to itself"):
        pm.fromParamDict(doc)

    assert pm.get_lock("a") is None


def test_a_key_of_another_instrument_is_refused_up_front():
    pm = ParameterManager(name="params")
    pm.add_parameter("a", initial_value=1, unit="u")
    doc = {
        "version": 2,
        "parameters": {"other.a": {"value": 1, "unit": "u"}},
        "types": {},
    }
    with pytest.raises(
        ValueError, match="does not belong to this Parameter Manager"
    ):
        pm.fromParamDict(doc)

    assert pm.a() == 1


def test_partial_instances_are_not_completed_and_get_no_type_lock():
    """The Types load with no Instance side effects (D20): a submodule
    carrying one entry of a two-entry Type is not completed, is no
    Instance, and gets no Lock from the entry's Type Lock."""
    pm = ParameterManager(name="params")
    doc = {
        "version": 2,
        "parameters": {
            "params._globals.qubit.IF": {"value": 1e9, "unit": "Hz"},
            "params.q01.IF": {"value": 2e9, "unit": "Hz"},
        },
        "types": {
            "qubit": {
                "parameters": {
                    "IF": {
                        "default": None,
                        "unit": "Hz",
                        "target": "params._globals.qubit.IF",
                    },
                    "gain": {"default": 10, "unit": "dB", "target": None},
                },
                "nested": {},
            }
        },
    }
    pm.fromParamDict(doc)

    assert pm.list_types() == ["qubit"]
    assert not pm.has_param("q01.gain")
    assert pm.instances_of("qubit") == []
    # the Type Lock is stored on the entry but not applied on load
    assert pm.get_lock("q01.IF") is None
    assert pm.get_type("qubit").parameters["IF"]["target"] == (
        "params._globals.qubit.IF"
    )


def test_a_listed_parameter_without_a_lock_entry_loses_its_lock():
    pm = ParameterManager(name="params")
    pm.add_parameter("a", initial_value=1, unit="u")
    pm.add_parameter("b", initial_value=2, unit="v")
    pm.lock("a", "b")
    doc = {
        "version": 2,
        "parameters": {
            "params.a": {"value": 1, "unit": "u"},
            "params.b": {"value": 2, "unit": "v"},
        },
        "types": {},
    }
    pm.fromParamDict(doc, deleteMissing=False)

    assert pm.get_lock("a") is None
    assert pm.list_locks() == {}


def test_a_locked_follower_loads_its_own_value_and_the_files_lock_state():
    """Setting the stored own value on a currently locked Follower cannot
    raise (D6): the listed Locks go first, and the Follower ends with the
    file's Lock state."""
    pm = ParameterManager(name="params")
    pm.add_parameter("q01.IF", initial_value=1.0, unit="Hz")
    pm.add_parameter("q01Data.IF", initial_value=2.0, unit="Hz")
    pm.lock("q01.IF", "q01Data.IF")
    doc = {
        "version": 2,
        "parameters": {
            "params.q01.IF": {
                "value": 9.0,
                "unit": "Hz",
                "lock": {"target": "params.q01Data.IF", "locked": False},
            },
            "params.q01Data.IF": {"value": 2.0, "unit": "Hz"},
        },
        "types": {},
    }
    pm.fromParamDict(doc)

    assert pm.parameter("q01.IF").own_value() == 9.0
    assert pm.get_lock("q01.IF") == PMLockBluePrint(
        target="params.q01Data.IF", locked=False
    )
    assert pm.get("q01.IF") == 9.0


def make_deletion_manager(name="params"):
    pm = ParameterManager(name=name)
    pm.add_parameter("a", initial_value=1, unit="u")
    pm.add_parameter("b", initial_value=2, unit="v")
    pm.add_parameter("c", initial_value=3, unit="w")
    pm.add_parameter("d", initial_value=4, unit="x")
    pm.lock("c", "a")  # c is not in the document: its Lock goes with it
    pm.lock("a", "d")  # re-created from the document with a new Target
    pm.add_type("kept")
    pm.add_type_parameter("kept", "k", default=1, unit="u")
    pm.add_type("dropped")
    pm.add_type_parameter("dropped", "x", default=2, unit="v")
    return pm


DELETE_MISSING_DOC = {
    "version": 2,
    "parameters": {
        "params.a": {
            "value": 1,
            "unit": "u",
            "lock": {"target": "params.b", "locked": True},
        },
        "params.b": {"value": 2, "unit": "v"},
    },
    "types": {
        "kept": {
            "parameters": {"k": {"default": 1, "unit": "u", "target": None}},
            "nested": {},
        }
    },
}


def test_delete_missing_removes_absent_parameters_types_and_locks():
    pm = make_deletion_manager()
    received = []
    pm.add_broadcast_sink(received.append)
    pm.fromParamDict(DELETE_MISSING_DOC, deleteMissing=True)

    assert not pm.has_param("c")
    assert not pm.has_param("d")
    assert pm.list_types() == ["kept"]
    assert pm.get_lock("a") == PMLockBluePrint(target="params.b", locked=True)
    assert pm.list_locks() == {"a": PMLockBluePrint(target="params.b", locked=True)}
    # the load's Broadcasts: one pm-type-update per Type written, one with
    # None per Type removed, then one pm-lock-update per Lock that ended
    # different (c's Lock ended removed with its parameter)
    assert [(bp.action, bp.name) for bp in received] == [
        (PM_TYPE_UPDATE, "params.kept"),
        (PM_TYPE_UPDATE, "params.dropped"),
        (PM_LOCK_UPDATE, "params.a"),
        (PM_LOCK_UPDATE, "params.c"),
    ]
    assert received[0].value is not None
    assert received[1].value is None
    assert received[2].value == PMLockBluePrint(target="params.b", locked=True)
    assert received[3].value is None


def test_delete_missing_false_keeps_absent_parameters_types_and_locks():
    pm = make_deletion_manager()
    received = []
    pm.add_broadcast_sink(received.append)
    pm.fromParamDict(DELETE_MISSING_DOC, deleteMissing=False)

    assert pm.has_param("c")
    assert pm.has_param("d")
    assert sorted(pm.list_types()) == ["dropped", "kept"]
    # c keeps its Lock; a's Lock is re-created from the document
    assert pm.get_lock("c") == PMLockBluePrint(target="params.a", locked=True)
    assert pm.get_lock("a") == PMLockBluePrint(target="params.b", locked=True)
    # nothing was removed, so no None payload went out; c's unchanged Lock
    # emits nothing
    assert [(bp.action, bp.name) for bp in received] == [
        (PM_TYPE_UPDATE, "params.kept"),
        (PM_LOCK_UPDATE, "params.a"),
    ]


def test_one_load_emits_type_updates_then_lock_updates_and_nothing_for_values():
    """The Broadcasts of one load, in order: the pm-type-updates of the
    Types written, then the pm-lock-updates of the Locks that ended
    different, in tree order — and nothing for the values, the created
    parameters or a refused load."""
    pm = ParameterManager(name="params")
    received = []
    pm.add_broadcast_sink(received.append)

    doc = {
        "version": 2,
        "parameters": {
            "params._globals.qubit.octave_gain": {"value": 10, "unit": "dB"},
            "params.q01.octave_gain": {
                "value": 12,
                "unit": "dB",
                "lock": {
                    "target": "params._globals.qubit.octave_gain",
                    "locked": True,
                },
            },
            "params.q02.octave_gain": {
                "value": 13,
                "unit": "dB",
                "lock": {
                    "target": "params._globals.qubit.octave_gain",
                    "locked": False,
                },
            },
        },
        "types": {
            "qubit": {
                "parameters": {
                    "octave_gain": {
                        "default": 10,
                        "unit": "dB",
                        "target": "params._globals.qubit.octave_gain",
                    }
                },
                "nested": {},
            }
        },
    }
    pm.fromParamDict(doc)

    assert [(bp.action, bp.name) for bp in received] == [
        (PM_TYPE_UPDATE, "params.qubit"),
        (PM_LOCK_UPDATE, "params.q01.octave_gain"),
        (PM_LOCK_UPDATE, "params.q02.octave_gain"),
    ]
    assert received[0].value.name == "qubit"
    assert received[1].value == PMLockBluePrint(
        target="params._globals.qubit.octave_gain", locked=True
    )
    assert received[2].value == PMLockBluePrint(
        target="params._globals.qubit.octave_gain", locked=False
    )
    # the values and the created parameters emit nothing from the
    # Parameter Manager (D22 keeps the reader's behaviour)
    assert not any(
        bp.action in (PARAMETER_CREATION, PARAMETER_DELETION) for bp in received
    )

    # a refused load emits nothing
    received.clear()
    refused = {
        "version": 2,
        "parameters": {
            "params.a": {
                "value": 1,
                "unit": "u",
                "lock": {"target": "params.ghost", "locked": True},
            }
        },
        "types": {},
    }
    with pytest.raises(ValueError):
        pm.fromParamDict(refused)
    assert received == []
