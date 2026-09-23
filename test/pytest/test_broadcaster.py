"""Unit tests for the Broadcaster mixin (``instrumentserver.base``).

These tests need no Server: they exercise the mixin's own behaviour —
registering and removing sinks, fanning a Broadcast out to the sinks,
tolerating an exception in one sink, and doing nothing without sinks.
The Server part of this file (the Server registering itself as a sink for
created and config-loaded instruments) is a separate task.
"""

import logging

from instrumentserver.base import Broadcaster
from instrumentserver.blueprints import ParameterBroadcastBluePrint
from instrumentserver.params import ParameterManager


def make_bp(
    name: str = "pm.q01.IF",
    action: str = "parameter-update",
    value: float = 1.0,
    unit: str = "Hz",
) -> ParameterBroadcastBluePrint:
    return ParameterBroadcastBluePrint(
        name=name, action=action, value=value, unit=unit
    )


# ---------------------------------------------------------------------------
# broadcasting behaviour of the mixin
# ---------------------------------------------------------------------------


def test_broadcast_without_sinks_is_a_noop():
    bc = Broadcaster()
    bc.broadcast(make_bp())  # must not raise


def test_broadcast_reaches_the_added_sink():
    bc = Broadcaster()
    bp = make_bp()
    received = []
    bc.add_broadcast_sink(received.append)
    bc.broadcast(bp)
    assert received == [bp]


def test_broadcast_reaches_all_sinks_in_registration_order():
    bc = Broadcaster()
    order = []
    bc.add_broadcast_sink(lambda bp: order.append("first"))
    bc.add_broadcast_sink(lambda bp: order.append("second"))
    bc.broadcast(make_bp())
    assert order == ["first", "second"]


def test_adding_the_same_sink_twice_delivers_twice():
    """Pins the documented semantics: sinks are stored in a plain list, so a
    sink registered twice receives every Broadcast twice, and a single
    remove leaves it registered once."""
    bc = Broadcaster()
    bp = make_bp()
    received = []
    bc.add_broadcast_sink(received.append)
    bc.add_broadcast_sink(received.append)

    bc.broadcast(bp)
    assert len(received) == 2
    assert received == [bp, bp]

    bc.remove_broadcast_sink(received.append)
    bc.broadcast(bp)
    assert len(received) == 3
    assert received == [bp, bp, bp]


def test_exception_in_one_sink_is_logged_and_others_still_run(caplog):
    bc = Broadcaster()
    bp = make_bp()
    received = []

    def failing_sink(bp):
        raise RuntimeError("sink is broken")

    bc.add_broadcast_sink(failing_sink)
    bc.add_broadcast_sink(received.append)

    with caplog.at_level(logging.ERROR, logger="instrumentserver.base"):
        bc.broadcast(bp)

    assert received == [bp]
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert "failing_sink" in error_records[0].getMessage()
    assert error_records[0].exc_info is not None


def test_removed_sink_no_longer_receives_broadcasts():
    bc = Broadcaster()
    received = []
    bc.add_broadcast_sink(received.append)
    bc.remove_broadcast_sink(received.append)
    bc.broadcast(make_bp())
    assert received == []


def test_removing_a_sink_that_was_never_added_is_a_noop():
    bc = Broadcaster()

    def unknown_sink(bp):
        pass

    bc.remove_broadcast_sink(unknown_sink)  # must not raise


# ---------------------------------------------------------------------------
# Parameter Manager implements the Broadcaster contract
# (it emits nothing on its own yet; here we only prove the mixin machinery
# works on a real Parameter Manager)
# ---------------------------------------------------------------------------


def test_parameter_manager_is_a_broadcaster(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pm = ParameterManager(name="params")
    assert isinstance(pm, Broadcaster)
    assert callable(pm.add_broadcast_sink)
    assert callable(pm.remove_broadcast_sink)
    assert callable(pm.broadcast)


def test_parameter_manager_broadcast_reaches_sink(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pm = ParameterManager(name="params")
    received = []
    pm.add_broadcast_sink(received.append)
    bp = make_bp()
    pm.broadcast(bp)
    assert received == [bp]

    pm.remove_broadcast_sink(received.append)
    pm.broadcast(make_bp())
    assert received == [bp]
