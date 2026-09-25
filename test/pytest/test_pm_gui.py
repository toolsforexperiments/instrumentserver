"""Client-side state and Broadcast handling of the Parameter Manager GUI
(plan task 5.1).

The GUI keeps the Parameter Manager's Types and Locks in a ``PMState``
(``ParameterManagerGui.state``), filled from the Parameter Manager on
construction and on every refresh, and kept current by the
``pm-lock-update`` and ``pm-type-update`` Broadcasts the model routes to it.
A second Client's changes must reach that state and the tree's value
widgets without any polling, so every cross-client assertion waits with
``qtbot.waitUntil``.

Two shapes of the live path are deliberately avoided in these tests, both
pre-existing and outside this task's scope:

- a parameter another Client creates while the GUI is open makes the
  model's creation branch resolve it on the GUI's (stale) Proxy Instrument
  blueprint, which raises;
- ``lock_type_parameter`` without an explicit Target creates the Globals
  parameter ``_globals.<type>.<path>``, whose ``parameter-creation``
  Broadcast hits the same branch. The Type Lock test therefore declares an
  explicit Target.
"""

import os

import pytest

from instrumentserver.blueprints import PMLockBluePrint, PMTypeBluePrint
from instrumentserver.client.proxy import Client
from instrumentserver.gui.instruments import ParameterManagerGui, PMState

PM_NAME = "parameter_manager"
PM_CLASS = "instrumentserver.params.ParameterManager"
BROADCAST_TIMEOUT = 5000


@pytest.fixture(scope="module", autouse=True)
def pm_working_directory(tmp_path_factory):
    """Run the module in its own working directory.

    The Parameter Manager keeps its profile files in the working directory
    of the process it lives in, and the GUI's profile selection needs at
    least one profile to exist (``switch_to_profile`` raises otherwise).
    The module's Server and its Parameter Manager live in the pytest
    process, so switching the directory for the module gives them a
    private, throwaway profile directory instead of the repository.
    """
    workdir = tmp_path_factory.mktemp("pm_gui_profiles")
    previous = os.getcwd()
    os.chdir(workdir)
    yield workdir
    os.chdir(previous)


@pytest.fixture(scope="module")
def pm(start_server, server_port):
    """The module's Parameter Manager Proxy Instrument, with one profile on
    disk so the GUI's profile combo has an entry to switch to."""
    cli = Client(port=server_port)
    manager = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
    manager.toFile()
    manager.refresh_profiles()
    yield manager
    cli.disconnect()


@pytest.fixture(autouse=True)
def clean_parameter_manager(pm):
    """Leave the shared Parameter Manager without Locks, parameters or
    Types before and after every test."""

    def clean():
        for follower in list(pm.list_locks()):
            pm.remove_lock(follower)
        for path in list(pm.list()):
            pm.remove_parameter(path)
        remaining = list(pm.list_types())
        while remaining:
            for name in remaining:
                try:
                    pm.remove_type(name)
                except ValueError:
                    pass  # still nested in another Type; goes on a later pass
            remaining = list(pm.list_types())

    clean()
    yield
    clean()


@pytest.fixture()
def second_client(start_server, server_port):
    """A second Client on the same Server, acting on the GUI's Parameter
    Manager from the outside."""
    cli = Client(port=server_port)
    yield cli
    cli.disconnect()


def _second_parameter_manager(second_client):
    """The second Client's Proxy Instrument of the same Parameter Manager."""
    return second_client.find_or_create_instrument(PM_NAME, PM_CLASS)


def _make_gui(qtbot, pm, server_port):
    """Build the Parameter Manager GUI on the module's Parameter Manager,
    listening for Broadcasts on the Server's broadcast port."""
    gui = ParameterManagerGui(pm, sub_host="localhost", sub_port=server_port + 1)
    qtbot.addWidget(gui)
    return gui


def _wait_until_broadcasts_arrive(qtbot, gui, second_pm):
    """Make sure the GUI's listener receives Broadcasts before the real
    assertions run.

    A zmq SUB socket drops everything published before its subscription
    has reached the Server's PUB socket (the slow joiner), so the first
    Broadcast after the GUI is built can be lost. Probe with throwaway
    Types until one is observed; every later Broadcast then arrives.
    """
    qtbot.waitUntil(lambda: gui.model.subClient.connected, timeout=BROADCAST_TIMEOUT)
    for attempt in range(3):
        name = f"gui_probe_type_{attempt}"
        second_pm.add_type(name)
        try:
            qtbot.waitUntil(
                lambda: name in gui.state.types, timeout=BROADCAST_TIMEOUT
            )
        except Exception:
            continue  # the probe Broadcast was lost to the slow joiner
        second_pm.remove_type(name)
        qtbot.waitUntil(
            lambda: name not in gui.state.types, timeout=BROADCAST_TIMEOUT
        )
        return
    raise AssertionError(
        "the GUI's listener received no Broadcast; cannot test live updates"
    )


def test_pm_state_helpers_work_without_a_server():
    """PMState fills from a local Parameter Manager and applies the
    Broadcast payloads, with no Server involved."""
    from instrumentserver.params import ParameterManager

    manager = ParameterManager("pm_state_local")
    manager.add_parameter("q01.x", initial_value=1.0, unit="Hz")
    manager.add_parameter("q02.x", initial_value=2.0, unit="Hz")
    manager.lock("q02.x", "q01.x")
    manager.add_type("qubit")
    manager.add_type_parameter("qubit", "IF", default=1.0, unit="Hz")

    state = PMState()
    assert state.types == {}
    assert state.locks == {}

    state.refresh(manager)
    assert isinstance(state.types["qubit"], PMTypeBluePrint)
    assert state.locks["q02.x"] == PMLockBluePrint(
        target="pm_state_local.q01.x", locked=True
    )

    # a pm-lock-update payload replaces the entry; None (the Lock was
    # removed) drops it, and dropping an absent entry is not an error
    state.apply_lock(
        "q02.x", PMLockBluePrint(target="pm_state_local.q01.x", locked=False)
    )
    assert state.locks["q02.x"].locked is False
    state.apply_lock("q02.x", None)
    assert "q02.x" not in state.locks
    state.apply_lock("gone.x", None)

    # same for a Type
    state.apply_type("qubit", None)
    assert "qubit" not in state.types
    state.apply_type("gone", None)


def test_state_on_construction_holds_types_and_locks_created_before(
    qtbot, pm, server_port
):
    """Types and Locks that exist before the GUI is built are in
    gui.state after the constructor ran."""
    pm.add_parameter("cq01.x", initial_value=1.0, unit="Hz")
    pm.add_parameter("cq02.x", initial_value=2.0, unit="Hz")
    pm.lock("cq02.x", "cq01.x")
    pm.add_type("cqubit")
    pm.add_type_parameter("cqubit", "IF", default=3.0, unit="Hz")

    gui = _make_gui(qtbot, pm, server_port)
    try:
        qtbot.waitUntil(
            lambda: isinstance(gui.state.types.get("cqubit"), PMTypeBluePrint),
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: gui.state.locks.get("cq02.x")
            == PMLockBluePrint(target=f"{PM_NAME}.cq01.x", locked=True),
            timeout=BROADCAST_TIMEOUT,
        )
        assert gui.state.types["cqubit"].parameters["IF"] == {
            "default": 3.0,
            "unit": "Hz",
            "target": None,
        }
    finally:
        gui.model.stopListener()


def test_lock_broadcasts_from_a_second_client_update_the_state(
    qtbot, pm, second_client, server_port
):
    """A second Client's lock, unlock and remove_lock reach gui.state
    through the pm-lock-update Broadcasts."""
    second_pm = _second_parameter_manager(second_client)
    second_pm.add_parameter("q01.x", initial_value=10.0, unit="Hz")
    second_pm.add_parameter("q02.x", initial_value=20.0, unit="Hz")

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        second_pm.lock("q02.x", "q01.x")
        qtbot.waitUntil(
            lambda: gui.state.locks.get("q02.x")
            == PMLockBluePrint(target=f"{PM_NAME}.q01.x", locked=True),
            timeout=BROADCAST_TIMEOUT,
        )

        second_pm.unlock("q02.x")
        qtbot.waitUntil(
            lambda: gui.state.locks.get("q02.x")
            == PMLockBluePrint(target=f"{PM_NAME}.q01.x", locked=False),
            timeout=BROADCAST_TIMEOUT,
        )

        second_pm.remove_lock("q02.x")
        qtbot.waitUntil(
            lambda: "q02.x" not in gui.state.locks,
            timeout=BROADCAST_TIMEOUT,
        )
    finally:
        gui.model.stopListener()


def test_type_broadcasts_from_a_second_client_update_the_state(
    qtbot, pm, second_client, server_port
):
    """A second Client's add_type, add_type_parameter and remove_type
    reach gui.state through the pm-type-update Broadcasts."""
    second_pm = _second_parameter_manager(second_client)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        second_pm.add_type("qubit")
        qtbot.waitUntil(
            lambda: isinstance(gui.state.types.get("qubit"), PMTypeBluePrint),
            timeout=BROADCAST_TIMEOUT,
        )

        second_pm.add_type_parameter("qubit", "IF", unit="Hz")
        qtbot.waitUntil(
            lambda: gui.state.types.get("qubit") is not None
            and "IF" in gui.state.types["qubit"].parameters,
            timeout=BROADCAST_TIMEOUT,
        )
        assert gui.state.types["qubit"].parameters["IF"] == {
            "default": None,
            "unit": "Hz",
            "target": None,
        }

        second_pm.remove_type("qubit")
        qtbot.waitUntil(
            lambda: "qubit" not in gui.state.types,
            timeout=BROADCAST_TIMEOUT,
        )
    finally:
        gui.model.stopListener()


def test_type_lock_from_a_second_client_updates_types_and_locks(
    qtbot, pm, second_client, server_port
):
    """A second Client's lock_type_parameter puts the entry's Target into
    gui.state.types and the Instances' Locks into gui.state.locks."""
    second_pm = _second_parameter_manager(second_client)
    second_pm.add_parameter("dq01.IF", initial_value=1.0, unit="Hz")
    second_pm.add_parameter("dq02.IF", initial_value=2.0, unit="Hz")
    # a root-level parameter: the root is never an Instance, so targeting
    # it cannot self-lock an Instance parameter
    second_pm.add_parameter("tshared", initial_value=0.0, unit="Hz")
    second_pm.add_type("dqubit")
    second_pm.add_type_parameter("dqubit", "IF", default=1.0, unit="Hz")

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        # an explicit Target, so no Globals parameter is created and no
        # parameter-creation Broadcast hits the model's creation branch
        second_pm.lock_type_parameter("dqubit", "IF", target="tshared")

        qtbot.waitUntil(
            lambda: gui.state.types.get("dqubit") is not None
            and gui.state.types["dqubit"].parameters["IF"]["target"]
            == f"{PM_NAME}.tshared",
            timeout=BROADCAST_TIMEOUT,
        )
        for follower in ("dq01.IF", "dq02.IF"):
            qtbot.waitUntil(
                lambda follower=follower: gui.state.locks.get(follower)
                == PMLockBluePrint(target=f"{PM_NAME}.tshared", locked=True),
                timeout=BROADCAST_TIMEOUT,
            )
    finally:
        gui.model.stopListener()


def test_a_second_clients_set_reaches_the_tree_widget(
    qtbot, pm, second_client, server_port
):
    """A value the second Client sets on a parameter shown in the tree
    ends up in the row's widget (D24: onItemNewValue uses
    widget._setMethod)."""
    pm.add_parameter("sq01.x", initial_value=1.0, unit="Hz")
    pm.update()  # the GUI's tree is built from the proxy's blueprint

    gui = _make_gui(qtbot, pm, server_port)
    try:
        second_pm = _second_parameter_manager(second_client)
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        widget = gui.view.delegate.parameters["sq01.x"]
        line_edit = widget.paramWidget.input
        assert line_edit.text() == "1.0"

        second_pm.sq01.x.set(42)
        qtbot.waitUntil(
            lambda: line_edit.text() == "42", timeout=BROADCAST_TIMEOUT
        )
    finally:
        gui.model.stopListener()


def test_refresh_all_refills_the_state_from_the_server(
    qtbot, pm, second_client, server_port
):
    """refreshAll() re-reads every Type and Lock, so the state catches up
    with changes made while the listener was not running."""
    second_pm = _second_parameter_manager(second_client)
    second_pm.add_parameter("rq01.x", initial_value=1.0, unit="Hz")
    second_pm.add_parameter("rq02.x", initial_value=2.0, unit="Hz")

    gui = _make_gui(qtbot, pm, server_port)
    try:
        # no live updates: the Lock must reach the state through the GUI's
        # own refresh
        gui.model.stopListener()
        second_pm.lock("rq02.x", "rq01.x")
        assert "rq02.x" not in gui.state.locks

        gui.refreshAll()
        assert gui.state.locks == second_pm.list_locks()
        assert gui.state.locks["rq02.x"] == PMLockBluePrint(
            target=f"{PM_NAME}.rq01.x", locked=True
        )
    finally:
        gui.model.stopListener()
