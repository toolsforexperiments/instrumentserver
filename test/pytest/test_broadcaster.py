"""Tests for the Broadcaster contract (``instrumentserver.base``) and its
Server-side registration (``instrumentserver.server.core``).

The unit part needs no Server: it exercises the mixin's own behaviour —
registering and removing sinks, fanning a Broadcast out to the sinks,
tolerating an exception in one sink, and doing nothing without sinks.
The Server part creates a Broadcaster instrument through a client, makes it
emit a Broadcast, and checks that a SubClient receives it; a plain dummy
instrument is checked to still work and to stay sink-free.
"""

import logging
import time
from contextlib import contextmanager

import qcodes as qc

from instrumentserver import QtCore
from instrumentserver.base import Broadcaster
from instrumentserver.blueprints import ParameterBroadcastBluePrint
from instrumentserver.client.proxy import SubClient
from instrumentserver.config import loadConfig
from instrumentserver.params import ParameterManager
from instrumentserver.server.core import StationServer


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


# ---------------------------------------------------------------------------
# Server part: the Server registers itself as a sink on Broadcaster
# instruments that join the Station, and a Broadcast emitted by such an
# instrument reaches a SubClient through the Server's PUB socket.
# ---------------------------------------------------------------------------

BROADCASTER_INSTRUMENT_CLASS = (
    "instrumentserver.testing.dummy_instruments.generic.DummyBroadcasterInstrument"
)


@contextmanager
def capture_broadcasts(instruments, sub_port):
    """Run a SubClient on its own QThread and collect the Broadcasts it receives.

    Mirrors the pattern of ``test/docs_verification/helpers.py``, but takes the
    Broadcast port from the ``server_port`` fixture instead of the default.
    """
    received = []
    sub = SubClient(
        instruments=instruments, sub_host="localhost", sub_port=sub_port
    )
    sub.update.connect(received.append, QtCore.Qt.DirectConnection)
    thread = QtCore.QThread()
    sub.moveToThread(thread)
    thread.started.connect(sub.connect)
    sub.finished.connect(thread.quit)
    thread.start()
    # PUB/SUB slow joiner: let the SUB socket connect before Broadcasts fire.
    time.sleep(0.3)
    try:
        yield received
    finally:
        sub.stop()
        thread.wait(2000)
        thread.deleteLater()


def wait_for_broadcasts(received, n=1, timeout=5.0):
    """Block until at least ``n`` Broadcasts arrived, or fail with a report."""
    deadline = time.monotonic() + timeout
    while len(received) < n:
        if time.monotonic() > deadline:
            raise AssertionError(
                f"Expected {n} Broadcast(s) within {timeout}s, "
                f"got {len(received)}: {received!r}"
            )
        time.sleep(0.05)


def test_created_broadcaster_instrument_reaches_subclient(cli, start_server, server_port):
    """A Broadcaster instrument created through a client has the Server as a
    sink, and a method call that emits a blueprint arrives at a SubClient."""
    inst = cli.find_or_create_instrument("bcaster", BROADCASTER_INSTRUMENT_CLASS)

    # The Server registered itself as a sink on the instrument in the Station.
    server_instrument = start_server.station.components["bcaster"]
    assert start_server._broadcastParameterChange in server_instrument._broadcast_sinks

    with capture_broadcasts(["bcaster"], server_port + 1) as received:
        inst.emit_broadcast(value=2.5, unit="V")

        wait_for_broadcasts(received)
        # exactly one message: the Server registered itself once
        assert len(received) == 1
        bp = received[0]
        assert isinstance(bp, ParameterBroadcastBluePrint)
        assert bp.name == "bcaster.param0"
        assert bp.action == "parameter-update"
        assert float(bp.value) == 2.5
        assert bp.unit == "V"


def test_plain_dummy_instrument_still_works_and_gets_no_sink(dummy_instrument, start_server):
    """A plain dummy instrument keeps working over the wire, and since it does
    not implement the Broadcaster contract the Server registers no sink."""
    cli, dummy = dummy_instrument

    dummy.param0(0.5)
    assert dummy.param0() == 0.5

    server_dummy = start_server.station.components["dummy"]
    assert not hasattr(server_dummy, "add_broadcast_sink")


def test_config_loaded_broadcaster_instrument_gets_sink(
    tmp_path, server_port, qapp_session
):
    """Instruments that reach the Station from a config file get the Server
    registered as a Broadcast sink in ``StationServer.__init__`` (ADR-0003).

    Mirrors the production config path: an instrumentserver YAML like
    ``test/docs_verification/getting_started/quickstartConfig.yml`` is split
    by ``loadConfig`` into a station config and a serverConfig, and the
    Server registers itself on every component the Station was loaded with.
    The StationServer is constructed directly — registration happens in
    ``__init__``, so no thread or socket bind is needed.
    """
    config = tmp_path / "serverConfig.yml"
    config.write_text(
        "instruments:\n"
        "  cfg_bcaster:\n"
        "    type: instrumentserver.testing.dummy_instruments.generic."
        "DummyBroadcasterInstrument\n"
        "    initialize: True\n"
    )
    stationConfigPath, serverConfig, _, _, tempFile, _, _ = loadConfig(config)

    server = StationServer(
        port=server_port, serverConfig=serverConfig, stationConfig=stationConfigPath
    )
    try:
        assert "cfg_bcaster" in server.station.components
        component = server.station.components["cfg_bcaster"]
        assert isinstance(component, Broadcaster)
        assert server._broadcastParameterChange in component._broadcast_sinks
        assert len(component._broadcast_sinks) == 1
    finally:
        # The StationServer was never started (no thread, no bound sockets);
        # close what it opened so the other tests keep a clean qcodes state.
        tempFile.close()
        server._wakeup_r.close()
        server._wakeup_w.close()
        if qc.Instrument.exist("cfg_bcaster"):
            qc.Instrument.find_instrument("cfg_bcaster").close()
