"""Tests for instrumentserver.config.loadConfig."""

from pathlib import Path

import pytest

from instrumentserver.config import GUIFIELD, loadConfig


def _write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------


def test_minimal_config(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule
""",
    )
    path, serverConfig, fullConfig, tempFile, pollingRates, ipAddresses = loadConfig(
        cfg
    )
    tempFile.close()

    assert "my_ins" in serverConfig
    assert "my_ins" in fullConfig
    assert pollingRates == {}
    assert ipAddresses == {}
    # returned path is a string
    assert isinstance(path, str)


def test_temp_file_is_readable(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
""",
    )
    tempFilePath, _, _, tempFile, _, _ = loadConfig(cfg)
    tempFile.seek(0)
    content = tempFile.read()
    assert len(content) > 0
    tempFile.close()


# ---------------------------------------------------------------------------
# SERVERFIELDS defaults
# ---------------------------------------------------------------------------


def test_initialize_defaults_to_true(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
""",
    )
    _, serverConfig, _, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    assert serverConfig["my_ins"]["initialize"] is True


def test_initialize_explicit_false(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
    initialize: false
""",
    )
    _, serverConfig, _, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    assert serverConfig["my_ins"]["initialize"] is False


def test_initialize_null_raises(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
    initialize:
""",
    )
    with pytest.raises(AttributeError):
        loadConfig(cfg)


# ---------------------------------------------------------------------------
# GUI field defaults
# ---------------------------------------------------------------------------


def test_gui_defaults_to_generic_instrument(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
""",
    )
    _, _, fullConfig, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    assert fullConfig["my_ins"]["gui"]["type"] == GUIFIELD["type"]


def test_gui_generic_alias_maps_to_full_path(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
    gui:
      type: generic
""",
    )
    _, _, fullConfig, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    assert fullConfig["my_ins"]["gui"]["type"] == GUIFIELD["type"]


def test_gui_null_raises(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
    gui:
""",
    )
    with pytest.raises(AttributeError):
        loadConfig(cfg)


# ---------------------------------------------------------------------------
# Error: missing instruments key
# ---------------------------------------------------------------------------


def test_missing_instruments_key_raises(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
my_ins:
  type: some.Type
""",
    )
    with pytest.raises(AttributeError):
        loadConfig(cfg)


# ---------------------------------------------------------------------------
# pollingRate
# ---------------------------------------------------------------------------


def test_polling_rate_parsed(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
    pollingRate:
      param1: 100
      param2: 200
""",
    )
    _, _, _, tempFile, pollingRates, _ = loadConfig(cfg)
    tempFile.close()
    assert pollingRates == {"my_ins.param1": 100, "my_ins.param2": 200}


def test_polling_rate_empty_is_ignored(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
    pollingRate:
""",
    )
    _, _, _, tempFile, pollingRates, _ = loadConfig(cfg)
    tempFile.close()
    assert pollingRates == {}


# ---------------------------------------------------------------------------
# networking
# ---------------------------------------------------------------------------


def test_networking_parsed(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
networking:
  externalBroadcast: tcp://192.168.1.1:5556
  listeningAddress: 192.168.1.1
""",
    )
    _, _, _, tempFile, _, ipAddresses = loadConfig(cfg)
    tempFile.close()
    assert ipAddresses["externalBroadcast"] == "tcp://192.168.1.1:5556"
    assert ipAddresses["listeningAddress"] == "192.168.1.1"


def test_no_networking_section_gives_empty_dict(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.Type
""",
    )
    _, _, _, tempFile, _, ipAddresses = loadConfig(cfg)
    tempFile.close()
    assert ipAddresses == {}


# ---------------------------------------------------------------------------
# gui_defaults merging
# ---------------------------------------------------------------------------


def test_gui_defaults_default_section(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.module.MyClass
gui_defaults:
  __default__:
    parameters-hide:
      - IDN
""",
    )
    _, _, fullConfig, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    kwargs = fullConfig["my_ins"]["gui"].get("kwargs", {})
    assert "parameters-hide" in kwargs
    assert "IDN" in kwargs["parameters-hide"]


def test_gui_defaults_class_section(tmp_path):
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.module.MyClass
gui_defaults:
  MyClass:
    parameters-hide:
      - power_level
""",
    )
    _, _, fullConfig, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    kwargs = fullConfig["my_ins"]["gui"].get("kwargs", {})
    assert "parameters-hide" in kwargs
    assert "power_level" in kwargs["parameters-hide"]


def test_gui_defaults_merging_order(tmp_path):
    """__default__ + class + instance patterns all appear in merged result."""
    cfg = _write_config(
        tmp_path,
        """\
instruments:
  my_ins:
    type: some.module.MyClass
    gui:
      kwargs:
        parameters-hide:
          - instance_param
gui_defaults:
  __default__:
    parameters-hide:
      - default_param
  MyClass:
    parameters-hide:
      - class_param
""",
    )
    _, _, fullConfig, tempFile, _, _ = loadConfig(cfg)
    tempFile.close()
    hide = fullConfig["my_ins"]["gui"]["kwargs"]["parameters-hide"]
    assert "default_param" in hide
    assert "class_param" in hide
    assert "instance_param" in hide
