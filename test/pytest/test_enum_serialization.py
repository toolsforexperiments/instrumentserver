"""Tests for serializing ``Enum``/``IntFlag`` valued parameters.

Regression coverage for the infinite-recursion bug triggered when a station
snapshot contains an ``IntFlag`` value (e.g. the Yokogawa GS200 status/event
registers, whose ``get_parser`` returns ``IntFlag`` instances).

Starting with Python 3.11, ``Flag``/``IntFlag`` members are *iterable*, and a
single-bit member iterates to a one-element sequence containing *itself*::

    >>> list(StatusByte.EAV)
    [<StatusByte.EAV: 4>]
    >>> list(StatusByte.EAV)[0] is StatusByte.EAV
    True

The serializers (``dict_to_serialized_dict`` / ``iterable_to_serialized_dict``)
recurse into anything that is a non-``str`` ``Iterable``, so before the fix they
recursed into a flag value forever and raised
``RecursionError: maximum recursion depth exceeded`` from ``encode()`` on the
server's send path.

The fix treats any ``Enum`` as a scalar (serializing its ``.value``) instead of
an iterable. These tests assert that scalar behaviour and that no recursion
occurs. They require Python >= 3.11 to reproduce the original failure, but the
expected serialized output is version independent.
"""

import json
from enum import Enum, IntFlag

from instrumentserver.base import encode
from instrumentserver.blueprints import (
    ServerResponse,
    deserialize_obj,
    dict_to_serialized_dict,
    iterable_to_serialized_dict,
)
from instrumentserver.testing.dummy_instruments.generic import StatusFlag


class StatusByte(IntFlag):
    """Mirror of the Yokogawa GS200 status byte flag."""

    EAV = 1 << 2
    MAV = 1 << 4
    ESB = 1 << 5


class SourceMode(Enum):
    """A plain (non-flag) enum with string values."""

    VOLT = "VOLT"
    CURR = "CURR"


def test_intflag_in_dict_serializes_to_value():
    """A single-bit IntFlag value serializes to its underlying int, no recursion."""
    result = dict_to_serialized_dict({"status_byte": StatusByte.EAV})
    assert result == {"status_byte": str(StatusByte.EAV.value)}  # "4"


def test_intflag_in_iterable_serializes_to_value():
    result = iterable_to_serialized_dict([StatusByte.EAV])
    assert result == [str(StatusByte.EAV.value)]  # ["4"]


def test_combined_intflag_serializes_to_combined_value():
    """A multi-bit flag must not be split into its members; keep the int value."""
    combined = StatusByte.EAV | StatusByte.MAV  # value == 20
    result = dict_to_serialized_dict({"status_byte": combined})
    assert result == {"status_byte": str(combined.value)}  # "20"


def test_plain_enum_serializes_to_value():
    result = dict_to_serialized_dict({"source_mode": SourceMode.VOLT})
    assert result == {"source_mode": "VOLT"}


def test_nested_snapshot_with_intflag_does_not_recurse():
    """A snapshot-shaped nested dict with IntFlag values serializes fully."""
    snapshot = {
        "parameters": {
            "status_byte": {
                "name": "status_byte",
                "unit": "",
                "value": StatusByte.EAV,
                "raw_value": StatusByte.EAV,
            },
            "voltage": {
                "name": "voltage",
                "unit": "V",
                "value": 0.5,
            },
        }
    }

    result = dict_to_serialized_dict(snapshot)

    status = result["parameters"]["status_byte"]
    assert status["value"] == str(StatusByte.EAV.value)
    assert status["raw_value"] == str(StatusByte.EAV.value)
    assert result["parameters"]["voltage"]["value"] == "0.5"


def test_encode_server_response_with_intflag_snapshot():
    """End-to-end: the actual failing path ``encode(ServerResponse(...))``.

    This is what the server runs in ``send_router``; before the fix it raised
    ``RecursionError`` on Python 3.11+.
    """
    snapshot = {
        "parameters": {
            "status_byte": {"name": "status_byte", "value": StatusByte.EAV},
            "condition_register": {
                "name": "condition_register",
                "value": StatusByte.EAV | StatusByte.ESB,
            },
        }
    }
    response = ServerResponse(message=snapshot)

    # Must not raise RecursionError, and must produce valid JSON.
    payload = encode(response)
    decoded = json.loads(payload)
    assert decoded["_class_type"] == "ServerResponse"
    assert "status_byte" in decoded["message"]


def test_server_response_message_with_intflag_round_trips():
    """The serialized payload survives a decode back into Python objects."""
    snapshot = {"parameters": {"status_byte": {"value": StatusByte.EAV}}}
    response = ServerResponse(message=snapshot)

    reconstructed = deserialize_obj(json.loads(encode(response)))
    assert reconstructed._class_type == "ServerResponse"


def test_server_response_enum_message_reconstructs_enum_type():
    """A top-level Enum message round-trips back into the *actual* enum type.

    Unlike a snapshot (where a nested flag is serialized lossily to its value),
    a parameter get returns the flag as the message itself. In that case the
    client should receive a reconstructed ``StatusFlag`` instance, not a bare
    int. ``StatusFlag`` lives in an importable module so deserialization can
    rebuild it via its ``_class_type``.
    """
    response = ServerResponse(message=StatusFlag.EAV)

    reconstructed = deserialize_obj(json.loads(encode(response)))

    assert isinstance(reconstructed.message, StatusFlag)
    assert reconstructed.message == StatusFlag.EAV


def test_server_response_composite_enum_message_reconstructs_enum_type():
    """A multi-bit flag value also reconstructs to the composite enum member."""
    combined = StatusFlag.EAV | StatusFlag.ESB
    response = ServerResponse(message=combined)

    reconstructed = deserialize_obj(json.loads(encode(response)))

    assert isinstance(reconstructed.message, StatusFlag)
    assert reconstructed.message == combined


# --- Full end-to-end round-trip through the real client/server -------------


FLAG_INSTRUMENT_CLASS = (
    "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithFlags"
)


def test_end_to_end_get_intflag_parameter(cli):
    """A live client getting an IntFlag parameter receives the real enum type.

    This is the case the user cares about: calling the parameter (not
    snapshotting) should return a reconstructed ``StatusFlag`` instance on the
    client side, not just its integer value.
    """
    flag_ins = cli.find_or_create_instrument("flag_ins", FLAG_INSTRUMENT_CLASS)

    status = flag_ins.status_byte()
    assert isinstance(status, StatusFlag)
    assert status == StatusFlag.EAV

    condition = flag_ins.condition_register()
    assert isinstance(condition, StatusFlag)
    assert condition == (StatusFlag.EAV | StatusFlag.ESB)


def test_end_to_end_snapshot_with_intflag(cli):
    """The exact failing scenario: snapshotting an instrument with IntFlag values.

    Before the fix this raised RecursionError server-side and the client got no
    response. Here we assert the snapshot comes back intact through the full
    serialize -> send -> deserialize pipeline.
    """
    ins = cli.find_or_create_instrument("flag_ins_snap", FLAG_INSTRUMENT_CLASS)

    # update=True forces the parameters to be read into the snapshot
    snapshot = ins.get_snapshot(update=True)

    assert isinstance(snapshot, dict)
    params = snapshot["parameters"]
    assert params["status_byte"]["value"] == StatusFlag.EAV.value  # 4
    assert (
        params["condition_register"]["value"]
        == (StatusFlag.EAV | StatusFlag.ESB).value  # 36
    )


def test_end_to_end_full_station_snapshot_with_intflag(cli):
    """Snapshot of the whole station (no instrument arg) including flag values.

    This mirrors the user's reported call (``snapshot`` of the station with a
    Yokogawa present) most closely.
    """
    cli.find_or_create_instrument("flag_ins_station", FLAG_INSTRUMENT_CLASS)

    station_snapshot = cli.get_snapshot(update=True)

    assert isinstance(station_snapshot, dict)
    instruments = station_snapshot["instruments"]
    flag_params = instruments["flag_ins_station"]["parameters"]
    assert flag_params["status_byte"]["value"] == StatusFlag.EAV.value
