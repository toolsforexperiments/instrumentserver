"""Verification script for docs/technical_guide/broadcasts.md.

One section below per page section, in page order (see
test/docs_verification/README.md for conventions). Asserts every behavioral
claim the page makes; exits 0 on success.

A Parameter Manager writes its profile files into the working directory of
the process it lives in, so every section that hosts one runs inside a
throwaway working directory created (and removed again) under this script's
folder; no profile file is ever left in the repository.

The wire-format and external-forwarding claims are observed with raw ZMQ
frames (``capture_raw_frames``); the consumer-side claims go through the
SubClient (``capture_broadcasts``), the intended live-update path.
"""

import json
import logging
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import zmq

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import (
    DUMMY_INSTRUMENT,
    capture_broadcasts,
    capture_raw_frames,
    client,
    ensure_qapp,
    server,
)

from instrumentserver import DEFAULT_PORT, QtCore
from instrumentserver.base import Broadcaster, decode, recvMultipart
from instrumentserver.blueprints import (
    PARAMETER_CALL,
    PARAMETER_CREATION,
    PARAMETER_DELETION,
    PARAMETER_UPDATE,
    PM_LOCK_UPDATE,
    PM_TYPE_UPDATE,
    ParameterBroadcastBluePrint,
    PMLockBluePrint,
    PMTypeBluePrint,
    bluePrintToDict,
    deserialize_obj,
)
from instrumentserver.client.proxy import SubClient
from instrumentserver.config import loadConfig
from instrumentserver.gui.instruments import PMState
from instrumentserver.params import ParameterManager

PM_CLASS = "instrumentserver.params.ParameterManager"
PM_NAME = "parameter_manager"
BROADCASTER_CLASS = (
    "instrumentserver.testing.dummy_instruments.generic.DummyBroadcasterInstrument"
)
BROADCAST_PORT = DEFAULT_PORT + 1


@contextmanager
def workspace():
    """Run one section in a throwaway working directory.

    The in-process Server (and with it every Parameter Manager it hosts)
    writes its profile files into the working directory. The directory is
    created under this script's folder and removed again on exit.
    """
    old = os.getcwd()
    path = Path(tempfile.mkdtemp(prefix="verify_broadcasts_", dir=Path(__file__).parent))
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(old)
        shutil.rmtree(path, ignore_errors=True)


def capture_actions(action, instruments=None):
    """Run ``action`` under a Broadcast capture and return every message
    the capture saw while ``action`` ran, plus a short settle wait.

    ``wait_for(1)`` returns as soon as the first message lands, so the
    settle wait runs before the list is taken: a caller counting the
    messages sees the ones belonging to this action only.
    """
    with capture_broadcasts(instruments) as cap:
        action()
        cap.wait_for(1)
        time.sleep(0.2)
        return list(cap.messages)


def capture_nothing(action, instruments=None):
    """Run ``action`` under a Broadcast capture and assert that nothing
    arrives while it runs and during a settle wait."""
    with capture_broadcasts(instruments) as cap:
        action()
        time.sleep(0.4)
        assert cap.messages == [], cap.messages


def free_port() -> int:
    """A free TCP port on loopback (bind to 0, read it, close)."""
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if port not in (DEFAULT_PORT, BROADCAST_PORT):
            return port


# ---------------------------------------------------------------------------
# Section: What triggers a Broadcast
#
# Page claims: the Server emits from the worker thread that executed the
# client request, under that instrument's instrument mutex; parameter-update
# on a parameter set (with the value set), parameter-call on a parameter get
# (with the value read), parameter-creation / parameter-deletion when the
# called method is literally named add_parameter / remove_parameter (with
# name = <instrument>.<args joined>, and for creation the initial_value and
# unit keyword arguments); any other method call emits nothing unless the
# instrument is a Broadcaster; the six action strings are the module
# constants in blueprints.py.
# ---------------------------------------------------------------------------
def section_what_triggers_a_broadcast() -> None:
    assert PARAMETER_UPDATE == "parameter-update"
    assert PARAMETER_CALL == "parameter-call"
    assert PARAMETER_CREATION == "parameter-creation"
    assert PARAMETER_DELETION == "parameter-deletion"
    assert PM_LOCK_UPDATE == "pm-lock-update"
    assert PM_TYPE_UPDATE == "pm-type-update"

    with workspace(), server() as srv:
        with client() as cli:
            dummy = cli.find_or_create_instrument("dummy", DUMMY_INSTRUMENT)
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm.add_parameter("q01.IF", initial_value=10e6, unit="Hz")
            pm.add_parameter("q01Data.IF", initial_value=10e6, unit="Hz")

            # a parameter set: parameter-update, carrying the value set
            with capture_broadcasts() as cap:
                dummy.param0.set(0.5)
                (bp,) = cap.wait_for(1)
            assert bp.name == "dummy.param0"
            assert bp.action == PARAMETER_UPDATE
            assert bp.value == 0.5

            # a parameter get: parameter-call, carrying the value read
            with capture_broadcasts() as cap:
                assert dummy.param0() == 0.5
                (bp,) = cap.wait_for(1)
            assert bp.name == "dummy.param0"
            assert bp.action == PARAMETER_CALL
            assert bp.value == 0.5

            # a direct add_parameter call: parameter-creation, named
            # <instrument>.<args joined>, with the initial_value and unit
            # keyword arguments
            with capture_broadcasts([PM_NAME]) as cap:
                pm.add_parameter("extra.gain", initial_value=3, unit="V")
                (bp,) = cap.wait_for(1)
            assert bp.name == "parameter_manager.extra.gain"
            assert bp.action == PARAMETER_CREATION
            assert bp.value == 3
            assert bp.unit == "V"

            # a direct remove_parameter call: parameter-deletion
            with capture_broadcasts([PM_NAME]) as cap:
                pm.remove_parameter("extra.gain")
                (bp,) = cap.wait_for(1)
            assert bp.name == "parameter_manager.extra.gain"
            assert bp.action == PARAMETER_DELETION
            assert bp.value is None

            # no initial_value / unit given: value None, unit ""
            with capture_broadcasts([PM_NAME]) as cap:
                pm.add_parameter("extra.offset")
                (bp,) = cap.wait_for(1)
            assert bp.name == "parameter_manager.extra.offset"
            assert bp.action == PARAMETER_CREATION
            assert bp.value is None
            assert bp.unit == ""
            pm.remove_parameter("extra.offset")

            # any other method call emits nothing: a method that is no
            # parameter, and read-only Parameter Manager queries
            capture_nothing(lambda: dummy.test_func(1, 2, 3, d=4))
            capture_nothing(lambda: pm.list_types())
            capture_nothing(lambda: pm.has_param("q01.IF"))

            # the Server emits from the worker thread that executed the
            # request: a sink on the instrument (the Parameter Manager is a
            # Broadcaster) sees a ThreadPoolExecutor worker, not the caller.
            # The instrument's sinks run for its own emissions (the Lock
            # methods); a plain parameter set is emitted by the Server
            # itself, not through the instrument
            recorded = []

            def recording_sink(bp) -> None:
                recorded.append(threading.current_thread())

            pm_instrument = srv.station.components[PM_NAME]
            pm_instrument.add_broadcast_sink(recording_sink)
            try:
                with capture_broadcasts([PM_NAME]) as cap:
                    pm.lock("q01.IF", "q01Data.IF")
                    cap.wait_for(1)
                assert recorded, "the sink never ran"
                assert recorded[0] is not threading.current_thread()
                assert recorded[0].name.startswith("ThreadPoolExecutor"), (
                    recorded[0].name
                )
            finally:
                pm_instrument.remove_broadcast_sink(recording_sink)
            pm.unlock("q01.IF")

            # and the emission happens while the worker holds the
            # instrument mutex: a second request for the same instrument
            # waits until the first one is done
            def blocked_call() -> None:
                with client() as second_cli:
                    finished.append(
                        second_cli.call(f"{PM_NAME}.set", "q01.IF", 12e6)
                    )

            mutex = srv._get_lock_for_target(PM_NAME)
            finished = []
            mutex.acquire()
            try:
                worker = threading.Thread(target=blocked_call, daemon=True)
                worker.start()
                time.sleep(0.5)
                assert finished == [], "the second call was not serialized"
            finally:
                mutex.release()
            worker.join(5)
            assert finished != []
            assert pm.q01.IF() == 12000000.0
    print("section_what_triggers_a_broadcast: OK")


# ---------------------------------------------------------------------------
# Section: The wire format
#
# Page claims: the PUB socket lives on the request port + 1; a Broadcast is
# a two-frame ZMQ message, frame 1 the topic (the instrument name, the first
# dotted component of the message's name, so subscribers can filter per
# instrument, as a plain prefix match), frame 2 the JSON of the
# ParameterBroadcastBluePrint dict with its _class_type; decode /
# deserialize_obj rebuild the dataclass from that dict; PUB/SUB slow
# joiner: subscribe before you trigger.
# ---------------------------------------------------------------------------
def section_the_wire_format() -> None:
    with workspace(), server() as srv:
        # the publishing socket is bound on the request port + 1; no
        # external forwarding is configured here
        assert srv.broadcastPort == BROADCAST_PORT
        assert srv.externalBroadcastAddr is None
        assert srv.externalBroadcastSocket is None

        with client() as cli:
            dummy = cli.find_or_create_instrument("dummy", DUMMY_INSTRUMENT)

            with capture_raw_frames(BROADCAST_PORT) as cap:
                dummy.param0.set(0.5)
                frames = cap.wait_for(1)
            topic, payload = frames[0]
            print(f"wire format, frame 1 (topic): {topic!r}")
            print(f"wire format, frame 2 (payload): {payload}")

            # frame 1: the topic is the instrument name, the first dotted
            # component of the message's name
            assert topic == "dummy"

            # frame 2: the JSON of the ParameterBroadcastBluePrint dict,
            # with its _class_type; every field is on the wire as a string
            assert json.loads(payload) == {
                "name": "dummy.param0",
                "action": "parameter-update",
                "value": "0.5",
                "unit": "",
                "_class_type": "ParameterBroadcastBluePrint",
            }

            # decode / deserialize_obj rebuild the dataclass from that dict
            bp = deserialize_obj(json.loads(payload))
            assert isinstance(bp, ParameterBroadcastBluePrint)
            assert bp.name == "dummy.param0"
            assert bp.action == PARAMETER_UPDATE
            assert bp.value == 0.5  # the numeric strings come back as numbers
            assert bp.unit == ""
            assert decode(payload) == bp  # decode does the loads + deserialize

            # and bluePrintToDict is the exact inverse of that rebuild
            assert bluePrintToDict(bp) == json.loads(payload)

            # the topic lets subscribers filter per instrument, as a plain
            # prefix match: subscribing to "dummy" also receives "dummy2"
            dummy2 = cli.find_or_create_instrument("dummy2", DUMMY_INSTRUMENT)
            with capture_raw_frames(BROADCAST_PORT, topic="dummy") as cap:
                dummy2.param0.set(1)
                frames = cap.wait_for(1)
            assert frames[0][0] == "dummy2"

            # PUB/SUB slow joiner: a subscriber that connects after the
            # trigger misses the message. Subscribe before you trigger.
            dummy.param0.set(0.75)
            time.sleep(0.2)  # the message is published (and gone for late joiners)
            with capture_raw_frames(BROADCAST_PORT) as late:
                assert late.frames == []
                dummy.param0.set(0.8)
                frames = late.wait_for(1)
            assert json.loads(frames[0][1])["value"] == "0.8"

            # one Broadcast reaches every subscriber: two captures on the
            # same socket both receive the same two frames
            with (
                capture_raw_frames(BROADCAST_PORT) as cap_a,
                capture_raw_frames(BROADCAST_PORT) as cap_b,
            ):
                dummy.param0.set(0.9)
                frames_a = cap_a.wait_for(1)
                frames_b = cap_b.wait_for(1)
            assert frames_a == frames_b
    print("section_the_wire_format: OK")


# ---------------------------------------------------------------------------
# Section: SubClient
#
# Page claims: the SubClient is the Qt consumer: a SUB socket subscribing to
# named instruments or to all, emitting every Broadcast as a
# ParameterBroadcastBluePrint on its update signal, running on its own
# QThread, stoppable with stop(); GUIs stay live by applying the
# pm-lock-update / pm-type-update payloads to their state locally, with no
# follow-up fetch (D22); a non-Qt consumer runs a plain SUB loop like the
# Listener's.
# ---------------------------------------------------------------------------
def section_subclient() -> None:
    with workspace(), server():
        with client() as cli:
            dummy = cli.find_or_create_instrument("dummy", DUMMY_INSTRUMENT)
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm.add_parameter("q01.IF", initial_value=10e6, unit="Hz")
            pm.add_parameter("q01Data.IF", initial_value=10e6, unit="Hz")

            # the Qt consumer: subscribe to named instruments, run on its
            # own QThread, emit ParameterBroadcastBluePrints on update
            ensure_qapp()
            received = []
            sub = SubClient(instruments=[PM_NAME])
            sub.update.connect(received.append, QtCore.Qt.DirectConnection)
            thread = QtCore.QThread()
            sub.moveToThread(thread)
            thread.started.connect(sub.connect)
            sub.finished.connect(thread.quit)
            thread.start()
            assert sub.thread() is thread
            assert thread is not QtCore.QThread.currentThread()
            deadline = time.monotonic() + 5
            while not sub.connected and time.monotonic() < deadline:
                time.sleep(0.05)
            assert sub.connected
            time.sleep(0.3)  # PUB/SUB slow joiner

            # another instrument's Broadcast is filtered out by the topic
            dummy.param0.set(0.5)
            pm.q01.IF.set(11e6)
            deadline = time.monotonic() + 5
            while len(received) < 1 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(received) == 1, received
            assert isinstance(received[0], ParameterBroadcastBluePrint)
            assert received[0].name == "parameter_manager.q01.IF"
            assert received[0].action == PARAMETER_UPDATE

            # stop() ends the listener loop; the GUI's stopListener stops
            # the thread with it: stop(), thread.quit(), thread.wait()
            sub.stop()
            thread.quit()
            assert thread.wait(2000)
            assert not thread.isRunning()

            # instruments=None (the default) subscribes to everything
            with capture_broadcasts() as cap:  # no instrument names: all
                dummy.param0.set(0.6)
                pm.q01.IF.set(11.5e6)
                messages = cap.wait_for(2)
            assert {bp.name for bp in messages} == {
                "dummy.param0",
                "parameter_manager.q01.IF",
            }

            # how GUIs stay live (D22): the Parameter Manager GUI keeps a
            # PMState, fills it once, and applies every pm-lock-update /
            # pm-type-update payload locally; no follow-up fetch. Here the
            # payloads of a second Client's changes are applied by hand and
            # must equal a fresh full fetch afterwards.
            state = PMState()
            state.refresh(pm)
            assert state.locks == {}
            assert state.types == {}

            pm.add_type("qubit")
            pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
            with capture_broadcasts([PM_NAME]) as cap:
                pm.lock("q01.IF", "q01Data.IF")
                pm.set_type_parameter_default("qubit", "IF", 12e6)
                cap.wait_for(2)
                time.sleep(0.2)
            for bp in cap.messages:
                path = ".".join(bp.name.split(".")[1:])
                if bp.action == PM_LOCK_UPDATE:
                    state.apply_lock(path, bp.value)
                elif bp.action == PM_TYPE_UPDATE:
                    state.apply_type(path, bp.value)
            fresh = PMState()
            fresh.refresh(pm)
            assert state.locks == fresh.locks
            assert state.types == fresh.types

            # a non-Qt consumer: a plain SUB loop like the Listener's, on a
            # plain thread, with recvMultipart doing the decode
            listener_messages = []
            stop = threading.Event()

            def run_listener() -> None:
                context = zmq.Context.instance()
                sock = context.socket(zmq.SUB)
                sock.connect(f"tcp://localhost:{BROADCAST_PORT}")
                sock.setsockopt_string(zmq.SUBSCRIBE, "")
                sock.setsockopt(zmq.RCVTIMEO, 100)  # ms
                try:
                    while not stop.is_set():
                        try:
                            listener_messages.append(recvMultipart(sock))
                        except zmq.Again:
                            continue
                finally:
                    sock.close(linger=0)

            listener_thread = threading.Thread(target=run_listener, daemon=True)
            listener_thread.start()
            time.sleep(0.3)  # PUB/SUB slow joiner
            # the Target accepts set; the locked Follower would refuse it
            pm.q01Data.IF.set(13e6)
            deadline = time.monotonic() + 5
            while len(listener_messages) < 1 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert listener_messages, "the plain SUB loop received nothing"
            topic, bp = listener_messages[0]
            assert topic == PM_NAME
            assert isinstance(bp, ParameterBroadcastBluePrint)
            assert bp.name == "parameter_manager.q01Data.IF"
            assert bp.value == 13000000.0
            stop.set()
            listener_thread.join(2)
    print("section_subclient: OK")


# ---------------------------------------------------------------------------
# Section: External forwarding
#
# Page claims: the station config's ipAddresses.externalBroadcast (a
# "tcp://address:port" string, the networking section of the config file)
# makes the Server bind a second PUB socket there and send every Broadcast
# to both sockets, with the same two frames, so live UIs and Listeners on
# other machines subscribe unchanged.
# ---------------------------------------------------------------------------
def section_external_forwarding() -> None:
    with workspace() as workdir:
        # the config file form: the networking section's externalBroadcast
        # lands in the ipAddresses dict the Server is started with
        config = workdir / "extBroadcastConfig.yml"
        config.write_text(
            "instruments: {}\n"
            "networking:\n"
            '  externalBroadcast: "tcp://127.0.0.1:6000"\n'
        )
        station_cfg, _server_cfg, _full, _shortcuts, temp_file, _rates, addresses = (
            loadConfig(str(config))
        )
        temp_file.close()
        assert addresses == {"externalBroadcast": "tcp://127.0.0.1:6000"}

        # the in-process form: startServer takes ipAddresses directly
        external_port = free_port()
        with server(
            ipAddresses={"externalBroadcast": f"tcp://127.0.0.1:{external_port}"}
        ) as srv:
            assert srv.externalBroadcastAddr == f"tcp://127.0.0.1:{external_port}"
            with client() as cli:
                dummy = cli.find_or_create_instrument("dummy", DUMMY_INSTRUMENT)

                # every Broadcast goes to both sockets, as the same two frames
                with (
                    capture_raw_frames(BROADCAST_PORT) as main_cap,
                    capture_raw_frames(external_port) as ext_cap,
                ):
                    dummy.param0.set(0.5)
                    main_frames = main_cap.wait_for(1)
                    ext_frames = ext_cap.wait_for(1)
                assert ext_frames == main_frames

                # so a consumer on the external address works unchanged
                with capture_broadcasts(["dummy"], port=external_port) as cap:
                    dummy.param0.set(0.7)
                    (bp,) = cap.wait_for(1)
                assert bp.name == "dummy.param0"
                assert bp.value == 0.7
    print("section_external_forwarding: OK")


# ---------------------------------------------------------------------------
# Section: The Broadcaster contract
#
# Page claims: the Broadcaster mixin (add_broadcast_sink /
# remove_broadcast_sink / broadcast) fans a Broadcast out to its sinks;
# the Server registers _broadcastParameterChange as a sink at the two
# registration points (creation over the wire, loading from the station
# config), by hasattr(instrument, "add_broadcast_sink"); instruments
# without it are untouched; standalone use with no sinks is a no-op; a sink
# that raises is logged and the others still run; Broadcaster emissions use
# the same socket, topic and wire format as the Server's own Broadcasts, so
# existing subscribers need no change; a Broadcaster instrument emits
# through the Server to a SubClient.
# ---------------------------------------------------------------------------
def section_the_broadcaster_contract() -> None:
    # the mixin itself, no Server involved
    with workspace():
        bc = Broadcaster()
        bp = ParameterBroadcastBluePrint(
            "bcaster.param0", PARAMETER_UPDATE, 1.0, "V"
        )

        # no sinks: a no-op
        bc.broadcast(bp)

        received = []
        bc.add_broadcast_sink(received.append)
        bc.broadcast(bp)
        assert received == [bp]

        bc.remove_broadcast_sink(received.append)
        bc.broadcast(bp)
        assert received == [bp]

        # a sink that raises is logged; the others still run
        pm = ParameterManager(name="pm_standalone")
        seen, errors = [], []
        handler = logging.Handler()
        handler.emit = lambda record: errors.append(record.getMessage())
        logger = logging.getLogger("instrumentserver.base")
        logger.addHandler(handler)
        try:
            def failing_sink(bp):
                raise RuntimeError("sink is broken")

            pm.add_broadcast_sink(failing_sink)
            pm.add_broadcast_sink(seen.append)
            pm.broadcast(bp)
        finally:
            logger.removeHandler(handler)
        assert seen == [bp]
        assert len(errors) == 1
        assert "broadcast sink" in errors[0], errors

        # standalone use: no sinks registered, so the Parameter Manager's
        # own emissions are no-ops and everything works without a Server
        pm.add_parameter("own.a", initial_value=1)
        pm.add_parameter("own.b", initial_value=2)
        pm.lock("own.b", "own.a")
        assert pm.get_lock("own.b").locked is True

    # registration point 1: an instrument created over the wire
    with workspace(), server() as srv:
        with client() as cli:
            bcaster = cli.find_or_create_instrument("bcaster", BROADCASTER_CLASS)
            instrument = srv.station.components["bcaster"]
            assert srv._broadcastParameterChange in instrument._broadcast_sinks

            # instruments without the mixin are untouched
            cli.find_or_create_instrument("dummy", DUMMY_INSTRUMENT)
            assert not hasattr(srv.station.components["dummy"], "add_broadcast_sink")

            # same socket, topic and wire format as the Server's own
            # Broadcasts: two frames, topic = instrument name, JSON with
            # the _class_type
            with capture_raw_frames(BROADCAST_PORT) as cap:
                bcaster.emit_broadcast(value=2.5, unit="V")
                frames = cap.wait_for(1)
            topic, payload = frames[0]
            assert topic == "bcaster"
            assert json.loads(payload) == {
                "name": "bcaster.param0",
                "action": PARAMETER_UPDATE,
                "value": "2.5",
                "unit": "V",
                "_class_type": "ParameterBroadcastBluePrint",
            }

            # the minimal example: the Broadcaster instrument emits through
            # the Server, and a SubClient receives the blueprint unchanged
            with capture_broadcasts(["bcaster"]) as cap:
                bcaster.emit_broadcast(value=3.0, unit="V")
                (bp,) = cap.wait_for(1)
            assert isinstance(bp, ParameterBroadcastBluePrint)
            assert bp.name == "bcaster.param0"
            assert bp.action == PARAMETER_UPDATE
            assert bp.value == 3.0
            assert bp.unit == "V"

    # registration point 2: an instrument loaded from the station config
    with workspace() as workdir:
        config = workdir / "broadcasterConfig.yml"
        config.write_text(
            "instruments:\n"
            "  cfg_bcaster:\n"
            "    type: instrumentserver.testing.dummy_instruments.generic."
            "DummyBroadcasterInstrument\n"
            "    initialize: True\n"
        )
        station_cfg, server_cfg, _full, _shortcuts, temp_file, _rates, _addresses = (
            loadConfig(str(config))
        )
        try:
            with server(config=station_cfg, serverConfig=server_cfg) as srv:
                assert "cfg_bcaster" in srv.station.components
                component = srv.station.components["cfg_bcaster"]
                assert srv._broadcastParameterChange in component._broadcast_sinks
        finally:
            temp_file.close()
    print("section_the_broadcaster_contract: OK")


# ---------------------------------------------------------------------------
# Section: The Parameter Manager's actions
#
# Page claims: pm-lock-update, one per affected Follower, name = full
# Follower path, value = PMLockBluePrint(target, locked) or None when the
# Lock was removed, emitted by every Lock method and by remove_parameter
# when deleting a Target drops Locks (D10); pm-type-update, name =
# <instrument>.<type>, value = PMTypeBluePrint(name, parameters, nested,
# effective) or None when the Type was removed, from every Type-editing
# method including lock_type_parameter / unlock_type_parameter (D22);
# re-emitted parameter-creation for parameters the Parameter Manager
# creates as side effects, while direct add_parameter / remove_parameter
# calls are announced by the Server, so nothing is announced twice; the
# ordering rules the docstrings state.
# ---------------------------------------------------------------------------
def section_the_parameter_managers_actions() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm.add_parameter("q01Data.IF", initial_value=10e6, unit="Hz")
            pm.add_parameter("q01.IF", initial_value=5e6, unit="Hz")

            # pm-lock-update: one per affected Follower, name = full
            # Follower path, value = PMLockBluePrint(target, locked)
            with capture_broadcasts([PM_NAME]) as cap:
                pm.lock("q01.IF", "q01Data.IF")
                (bp,) = cap.wait_for(1)
            assert bp.action == PM_LOCK_UPDATE
            assert bp.name == "parameter_manager.q01.IF"
            assert bp.value == PMLockBluePrint(
                target="parameter_manager.q01Data.IF", locked=True
            )

            # every Lock method announces its state change exactly once
            messages = capture_actions(lambda: pm.unlock("q01.IF"))
            assert len(messages) == 1
            assert messages[0].value == PMLockBluePrint(
                target="parameter_manager.q01Data.IF", locked=False
            )
            messages = capture_actions(lambda: pm.relock("q01.IF"))
            assert len(messages) == 1 and messages[0].value.locked is True
            messages = capture_actions(lambda: pm.toggle_lock("q01.IF"))
            assert len(messages) == 1 and messages[0].value.locked is False
            messages = capture_actions(lambda: pm.toggle_lock("q01.IF"))
            assert len(messages) == 1 and messages[0].value.locked is True

            # the no-op path emits nothing: unlocking an unlocked Lock
            pm.unlock("q01.IF")
            capture_nothing(lambda: pm.unlock("q01.IF"), [PM_NAME])
            pm.relock("q01.IF")

            # remove_lock announces the removal with a None payload
            messages = capture_actions(lambda: pm.remove_lock("q01.IF"))
            assert len(messages) == 1
            assert messages[0].action == PM_LOCK_UPDATE
            assert messages[0].name == "parameter_manager.q01.IF"
            assert messages[0].value is None
            pm.lock("q01.IF", "q01Data.IF")

            # deleting a Target: one pm-lock-update with None per dropped
            # Follower, then the Server's parameter-deletion (the deletion
            # itself emits nothing in the Parameter Manager)
            messages = capture_actions(lambda: pm.remove_parameter("q01Data.IF"))
            actions = [bp.action for bp in messages]
            assert actions == [PM_LOCK_UPDATE, PARAMETER_DELETION], actions
            assert messages[0].name == "parameter_manager.q01.IF"
            assert messages[0].value is None
            assert messages[1].name == "parameter_manager.q01Data.IF"

            # pm-type-update: name = <instrument>.<type>, value = the fresh
            # PMTypeBluePrint, one per Type edit. (The Type's entry is named
            # gain, not IF: the lock-demo submodule q01 carries q01.IF in
            # Hz, and a Type requiring IF would duck-type it into an
            # Instance and broadcast about it too.)
            messages = capture_actions(lambda: pm.add_type("qubit"))
            assert len(messages) == 1
            assert messages[0].action == PM_TYPE_UPDATE
            assert messages[0].name == "parameter_manager.qubit"
            assert messages[0].value == PMTypeBluePrint(
                name="qubit", parameters={}, nested={}, effective={}
            )

            # no Instances yet, so an entry edit emits only the Type update
            messages = capture_actions(
                lambda: pm.add_type_parameter("qubit", "gain", default=10, unit="dB")
            )
            assert [bp.action for bp in messages] == [PM_TYPE_UPDATE]

            # an Instance exists: the entry written into it is announced as
            # a parameter-creation first, then the Type update
            pm.add_instance("qubit", "q02")
            pm.update()
            messages = capture_actions(
                lambda: pm.add_type_parameter("qubit", "window", default=0.5, unit="s")
            )
            assert [bp.action for bp in messages] == [
                PARAMETER_CREATION,
                PM_TYPE_UPDATE,
            ], [
                (bp.action, bp.name, bp.value, bp.unit) for bp in messages
            ]
            assert messages[0].name == "parameter_manager.q02.window"
            assert messages[0].value == 0.5
            assert messages[0].unit == "s"
            assert messages[1].name == "parameter_manager.qubit"
            assert messages[1].value.name == "qubit"
            assert messages[1].value.parameters["window"] == {
                "default": 0.5,
                "unit": "s",
                "target": None,
            }

            # add_instance announces every parameter it creates, in
            # creation order, and no pm-type-update: it edits no Type
            messages = capture_actions(lambda: pm.add_instance("qubit", "q03"))
            actions = [bp.action for bp in messages]
            assert actions == [PARAMETER_CREATION, PARAMETER_CREATION], actions
            assert [bp.name for bp in messages] == [
                "parameter_manager.q03.gain",
                "parameter_manager.q03.window",
            ]

            # remove_type announces the removal with a None payload
            pm.add_type("shortlived")
            messages = capture_actions(lambda: pm.remove_type("shortlived"))
            assert len(messages) == 1
            assert messages[0].action == PM_TYPE_UPDATE
            assert messages[0].name == "parameter_manager.shortlived"
            assert messages[0].value is None

            # a Type Lock with the default Globals Target: the created
            # Globals parameter first, then one pm-lock-update per applied
            # Lock, then the pm-type-update of the edited Type
            pm.add_type("readout")
            pm.add_type_parameter("readout", "bw", default=20e6, unit="Hz")
            pm.add_instance("readout", "r01")
            pm.add_instance("readout", "r02")
            messages = capture_actions(lambda: pm.lock_type_parameter("readout", "bw"))
            actions = [bp.action for bp in messages]
            assert actions == [
                PARAMETER_CREATION,
                PM_LOCK_UPDATE,
                PM_LOCK_UPDATE,
                PM_TYPE_UPDATE,
            ], actions
            assert messages[0].name == "parameter_manager._globals.readout.bw"
            assert messages[0].value == 20000000.0
            assert {bp.name for bp in messages[1:3]} == {
                "parameter_manager.r01.bw",
                "parameter_manager.r02.bw",
            }
            assert all(bp.value.locked for bp in messages[1:3])
            assert messages[3].name == "parameter_manager.readout"

            # unlock_type_parameter: exactly one pm-type-update, the Locks stay
            messages = capture_actions(
                lambda: pm.unlock_type_parameter("readout", "bw")
            )
            assert [bp.action for bp in messages] == [PM_TYPE_UPDATE]
            assert messages[0].value.parameters["bw"]["target"] is None

            # a new Instance of a Type with a Type Lock: the creation, then
            # the Lock the new Instance gets at creation; no Type update
            pm.lock_type_parameter("readout", "bw")
            messages = capture_actions(lambda: pm.add_instance("readout", "r03"))
            actions = [bp.action for bp in messages]
            assert actions == [PARAMETER_CREATION, PM_LOCK_UPDATE], actions
            assert messages[0].name == "parameter_manager.r03.bw"
            assert messages[1].name == "parameter_manager.r03.bw"
            assert messages[1].value == PMLockBluePrint(
                target="parameter_manager._globals.readout.bw", locked=True
            )

            # a direct add_parameter is announced by the Server, exactly
            # once: the Parameter Manager adds nothing of its own
            messages = capture_actions(
                lambda: pm.add_parameter("q01.power", initial_value=-10, unit="dBm"),
                [PM_NAME],
            )
            assert len(messages) == 1
            assert messages[0].action == PARAMETER_CREATION
            assert messages[0].name == "parameter_manager.q01.power"

            # ... and a direct remove_parameter is announced once, too
            messages = capture_actions(
                lambda: pm.remove_parameter("q01.power"), [PM_NAME]
            )
            assert len(messages) == 1
            assert messages[0].action == PARAMETER_DELETION

            # a Target that a Type Lock rule points at: the dropped Lock
            # (pm-lock-update with None) first, then the pm-type-update of
            # the cleared rule, then the Server's parameter-deletion
            pm.add_parameter("shared.frequency", initial_value=1e6, unit="Hz")
            pm.add_type("receiver")
            pm.add_type_parameter("receiver", "lo", default=1e6, unit="Hz")
            pm.add_instance("receiver", "rcv01")
            pm.lock_type_parameter("receiver", "lo", target="shared.frequency")
            messages = capture_actions(lambda: pm.remove_parameter("shared.frequency"))
            actions = [bp.action for bp in messages]
            assert actions == [
                PM_LOCK_UPDATE,
                PM_TYPE_UPDATE,
                PARAMETER_DELETION,
            ], actions
            assert messages[0].name == "parameter_manager.rcv01.lo"
            assert messages[0].value is None
            assert messages[1].name == "parameter_manager.receiver"
            assert messages[1].value.parameters["lo"]["target"] is None
            assert messages[2].name == "parameter_manager.shared.frequency"

            # the two payload blueprints as they appear on the wire
            pm.add_parameter("show.target", initial_value=1.0, unit="V")
            pm.add_parameter("show.follower", initial_value=0.0, unit="V")
            with capture_raw_frames(BROADCAST_PORT, topic=PM_NAME) as cap:
                pm.lock("show.follower", "show.target")
                frames = cap.wait_for(1)
            lock_payload = frames[0][1]
            print(f"pm-lock-update payload: {lock_payload}")
            wire = json.loads(lock_payload)
            assert wire["action"] == PM_LOCK_UPDATE
            assert wire["value"]["_class_type"] == "PMLockBluePrint"

            pm.add_type("display")
            pm.add_type_parameter("display", "gain", default=10, unit="dB")
            with capture_raw_frames(BROADCAST_PORT, topic=PM_NAME) as cap:
                pm.set_type_parameter_default("display", "gain", 12)
                frames = cap.wait_for(1)
            type_payload = frames[0][1]
            print(f"pm-type-update payload: {type_payload}")
            wire = json.loads(type_payload)
            assert wire["action"] == PM_TYPE_UPDATE
            assert wire["value"]["_class_type"] == "PMTypeBluePrint"
    print("section_the_parameter_managers_actions: OK")


if __name__ == "__main__":
    section_what_triggers_a_broadcast()
    section_the_wire_format()
    section_subclient()
    section_external_forwarding()
    section_the_broadcaster_contract()
    section_the_parameter_managers_actions()
    print("verify_broadcasts: all sections OK")
