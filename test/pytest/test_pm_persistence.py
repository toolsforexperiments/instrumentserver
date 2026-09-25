"""Tests for the Parameter Manager's version-2 persistence (plan task 4.1).

The writer part checks the document :meth:`ParameterManager.toParamDict`
produces (plan decision D19): ``version`` 2, ``parameters`` keyed by full
dotted paths with the own values, the per-Follower ``lock`` entries and the
``types`` section, the file dump format, and validity against
``schemas/parameter_manager_v2.json``. The reader part checks the
:meth:`ParameterManager.fromParamDict` shim: the legacy flat map still
loads, a version-2 document loads its parameters back (Globals included,
``deleteMissing`` semantics unchanged) while its ``lock`` entries and
``types`` section are ignored for now, and unsupported versions or invalid
documents are refused. All tests are unit tests on a local Parameter
Manager with no Server involved.
"""

import json
import re

import pytest
from jsonschema import ValidationError, validate

from instrumentserver import PM_V2_SCHEMA_PATH
from instrumentserver.params import ManagedParameter, ParameterManager


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
# Reader shim: legacy flat map, version-2 parameters, refusals
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
