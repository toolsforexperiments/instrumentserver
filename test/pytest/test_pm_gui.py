"""Client-side state and Broadcast handling of the Parameter Manager GUI
(plan task 5.1), its tabs, tints and gutter bands (plan task 5.2), its
Lock column, lock toggle, context menu and arm strip (plan task 5.3), and
its Locks panel (plan task 5.4).

The GUI keeps the Parameter Manager's Types and Locks in a ``PMState``
(``ParameterManagerGui.state``), filled from the Parameter Manager on
construction and on every refresh, and kept current by the
``pm-lock-update`` and ``pm-type-update`` Broadcasts the model routes to it.
A second Client's changes must reach that state and the tree's value
widgets without any polling, so every cross-client assertion waits with
``qtbot.waitUntil``. The 5.2 tests cover the tab widget around the
existing view, the pure ``compute_claims`` function and the tint palette
without a Server, and the tints and gutter bands a second Client's Type
edits produce live. The 5.3 tests cover the pure Lock helpers, the arm
strip and the read-only rendering without a Server, and the arm-via-context-menu
flow, the toggle, the refused cycle, the Follower repaint on a second
Client's Target update, and the model reload path live. The 5.4 tests cover
the pure Locks-panel row model without a Server, the toolbar action and
splitter, and the panel's rows, remove and lock-all actions, value editor
and "Lock selection to…" flow live.

Two shapes of the live path are deliberately avoided in these tests, both
pre-existing and outside this task's scope:

- a parameter another Client creates while the GUI is open makes the
  model's creation branch resolve it on the GUI's (stale) Proxy Instrument
  blueprint, which raises. Every Type edit below therefore has no creation
  side effect: the parameters (with the units the entries declare) exist
  before the GUI is built, and the entries land on Instances that already
  carry them;
- ``lock_type_parameter`` without an explicit Target creates the Globals
  parameter ``_globals.<type>.<path>``, whose ``parameter-creation``
  Broadcast hits the same branch. The Type Lock test therefore declares an
  explicit Target.
"""

import os

import pytest
from qcodes.instrument import InstrumentBase

from instrumentserver import QtCore, QtWidgets
from instrumentserver.blueprints import PMLockBluePrint, PMTypeBluePrint
from instrumentserver.client.proxy import Client
from instrumentserver.gui.base_instrument import InstrumentSortFilterProxyModel
from instrumentserver.gui.instruments import (
    GUTTER_COLUMN,
    GUTTER_ROLE,
    GUTTER_WIDTH,
    LOCK_COLUMN,
    LOCK_COLUMN_WIDTH,
    LOCK_PANEL_NOTE,
    LOCK_ROW_ROLE,
    TINT_COLOURS,
    Claim,
    GutterDelegate,
    ItemParameters,
    LockArmStrip,
    ModelParameters,
    ParameterManagerGui,
    ParameterManagerTreeView,
    PMState,
    TypePalette,
    build_lock_rows,
    compute_claims,
    followers_reaching,
    lock_column_text,
    lock_root,
    rank_lock_targets,
    relative_path,
)
from instrumentserver.gui.parameters import ParameterWidget
from instrumentserver.gui.shortcuts import KeyboardShortcutManager

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


class _StubParamWidget:
    """Stands in for a ParameterWidget's inner widget of a kind that has no
    ``setValue`` (e.g. the QLineEdit of a string parameter or a read-only
    QLabel): only the ParameterWidget's ``_setMethod`` reaches it."""

    def __init__(self):
        self.set_via_set_method = []

    def _setMethod(self, value):
        self.set_via_set_method.append(value)


class _StubDelegateWidget:
    """Stands in for the delegate's ParameterWidget."""

    def __init__(self):
        self.paramWidget = _StubParamWidget()
        self.set_via_set_method = []

    def _setMethod(self, value):
        self.set_via_set_method.append(value)


def test_on_item_new_value_uses_the_parameter_widget_set_method(qtbot):
    """D24 item three: ``ParameterManagerTreeView.onItemNewValue`` delivers
    the value through the widget's ``_setMethod``, which every
    ParameterWidget kind has — not through ``paramWidget.setValue``, which
    only the input widgets have. The stub's paramWidget deliberately has no
    ``setValue``, so the old code would raise AttributeError here."""
    stub_instrument = InstrumentBase("pm_tree_stub")
    model = ModelParameters(stub_instrument, "parameters", ItemParameters)
    view = ParameterManagerTreeView(InstrumentSortFilterProxyModel(model))
    qtbot.addWidget(view)

    widget = _StubDelegateWidget()
    assert not hasattr(widget.paramWidget, "setValue")
    view.delegate.parameters["stub.x"] = widget
    try:
        view.onItemNewValue("stub.x", 42)
    finally:
        model.stopListener()

    assert widget.set_via_set_method == [42]


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


def test_load_profile_refreshes_the_state_without_broadcasts(
    qtbot, pm, second_client, server_port
):
    """loadProfile re-reads the Types and Locks from the Parameter Manager
    even while the listener is stopped, so no Broadcast can fill the
    state: a Type the second Client created before the load must be in
    gui.state afterwards."""
    second_pm = _second_parameter_manager(second_client)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        gui.model.stopListener()
        second_pm.add_type("pt")
        assert "pt" not in gui.state.types  # no listener, no Broadcast

        gui.loadProfile()
        assert "pt" in gui.state.types
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


# ---------------------------------------------------------------------------
# plan task 5.2: tabs, tints and gutter bands
# ---------------------------------------------------------------------------


def _type_blueprint(name, entries, nested=None, registry=None):
    """A ``PMTypeBluePrint`` whose effective set is expanded the way
    ``params.py`` expands it: the Type's own entries carry itself as
    ``from_type``, and every Nested Type's effective set is mounted under
    the submodule that requires it, keeping the defining Type."""
    nested = dict(nested or {})
    effective = {
        path: {"unit": unit, "from_type": name} for path, unit in entries.items()
    }
    for submodule, nested_name in nested.items():
        for path, spec in registry[nested_name].effective.items():
            effective[f"{submodule}.{path}"] = dict(spec)
    return PMTypeBluePrint(
        name=name,
        parameters={
            path: {"default": None, "unit": unit, "target": None}
            for path, unit in entries.items()
        },
        nested=nested,
        effective=effective,
    )


def test_compute_claims_requires_every_path_with_the_declared_unit():
    """A submodule is an Instance only when it carries every effective path
    of the Type with the unit the Type declares (D12)."""
    qubit = _type_blueprint("qubit", {"IF": "Hz", "bw": "Hz"})

    # both paths, both units: q01 matches and claims its rows
    claims = compute_claims({"qubit": qubit}, {"q01.IF": "Hz", "q01.bw": "Hz"})
    assert claims["q01.IF"] == Claim(type="qubit", instance="q01", stack=["qubit"])
    assert claims["q01.bw"] == Claim(type="qubit", instance="q01", stack=["qubit"])
    assert claims["q01"] == Claim(type="qubit", instance="q01", stack=["qubit"])

    # one path missing: no Instance, nothing claimed
    assert compute_claims({"qubit": qubit}, {"q01.IF": "Hz"}) == {}

    # a wrong unit excludes the submodule just the same
    assert compute_claims({"qubit": qubit}, {"q01.IF": "Hz", "q01.bw": "V"}) == {}
    assert compute_claims({"qubit": qubit}, {"q01.IF": "V", "q01.bw": "Hz"}) == {}


def test_compute_claims_never_matches_globals_at_any_depth():
    """The Globals submodule and everything under it are excluded from
    matching (D12), wherever ``_globals`` appears in the tree."""
    qubit = _type_blueprint("qubit", {"IF": "Hz"})
    claims = compute_claims(
        {"qubit": qubit},
        {
            "q01.IF": "Hz",
            "_globals.qubit.IF": "Hz",
            "q01._globals.IF": "Hz",
        },
    )
    assert set(claims) == {"q01", "q01.IF"}


def test_compute_claims_never_matches_the_root():
    """The root of the Parameter Manager is never an Instance (D12): a
    parameter at the root carries the shape, but claims nothing."""
    qubit = _type_blueprint("qubit", {"IF": "Hz"})
    claims = compute_claims({"qubit": qubit}, {"IF": "Hz", "q01.IF": "Hz"})
    assert set(claims) == {"q01", "q01.IF"}


def test_compute_claims_of_an_empty_type():
    """An empty Type has no Instances (D12) and claims nothing."""
    qubit = _type_blueprint("qubit", {})
    assert compute_claims({"qubit": qubit}, {"q01.IF": "Hz"}) == {}


def test_compute_claims_innermost_nested_type_wins():
    """A Nested Type claims the rows it defines at and below its submodule
    (the mock's owner credit): ``readout`` claims ``q01.readout.bw`` with
    the ``qubit`` behind it in the stack."""
    readout = _type_blueprint("readout", {"bw": "Hz"})
    qubit = _type_blueprint(
        "qubit", {"IF": "Hz"}, nested={"readout": "readout"}, registry={"readout": readout}
    )
    claims = compute_claims(
        {"readout": readout, "qubit": qubit},
        {"q01.IF": "Hz", "q01.readout.bw": "Hz"},
    )
    assert claims["q01.IF"] == Claim(type="qubit", instance="q01", stack=["qubit"])
    assert claims["q01.readout.bw"] == Claim(
        type="readout", instance="q01.readout", stack=["qubit", "readout"]
    )
    # the Instance row of the Nested Type is claimed by it as well
    assert claims["q01.readout"] == Claim(
        type="readout", instance="q01.readout", stack=["qubit", "readout"]
    )
    # the outer Instance row stays with the outer Type
    assert claims["q01"] == Claim(type="qubit", instance="q01", stack=["qubit"])


def test_compute_claims_of_a_nested_type_nested_two_levels_deep():
    """A Nested Type's own Nested Type extends the submodule chain (the
    mock's ``at``): ``pulse_window`` claims at ``q01.readout.pw``."""
    pulse_window = _type_blueprint("pulse_window", {"win": "s"})
    readout = _type_blueprint(
        "readout",
        {"bw": "Hz"},
        nested={"pw": "pulse_window"},
        registry={"pulse_window": pulse_window},
    )
    qubit = _type_blueprint(
        "qubit", {"IF": "Hz"}, nested={"readout": "readout"}, registry={"readout": readout}
    )
    claims = compute_claims(
        {"pulse_window": pulse_window, "readout": readout, "qubit": qubit},
        {"q01.IF": "Hz", "q01.readout.bw": "Hz", "q01.readout.pw.win": "s"},
    )
    assert claims["q01.readout.pw.win"] == Claim(
        type="pulse_window",
        instance="q01.readout.pw",
        stack=["qubit", "readout", "pulse_window"],
    )
    # the Nested Type's submodule row carries the same claim
    assert claims["q01.readout.pw"] == Claim(
        type="pulse_window",
        instance="q01.readout.pw",
        stack=["qubit", "readout", "pulse_window"],
    )
    assert claims["q01.readout.bw"].type == "readout"
    assert claims["q01.IF"].type == "qubit"


def test_compute_claims_larger_effective_set_wins():
    """Two non-nested Types covering the same rows: the larger effective
    set claims them, both carry the row in the stack."""
    big = _type_blueprint("big", {"a": "Hz", "b": "Hz"})
    small = _type_blueprint("small", {"a": "Hz"})
    claims = compute_claims(
        {"big": big, "small": small}, {"q01.a": "Hz", "q01.b": "Hz"}
    )
    assert claims["q01.a"] == Claim(type="big", instance="q01", stack=["big", "small"])
    assert claims["q01.b"] == Claim(type="big", instance="q01", stack=["big"])
    assert claims["q01"] == Claim(type="big", instance="q01", stack=["big", "small"])


def test_compute_claims_breaks_ties_by_type_name():
    """Two Types with the same Instance and the same effective set size:
    the Type name decides, for determinism."""
    aaa = _type_blueprint("aaa", {"x": "Hz"})
    zzz = _type_blueprint("zzz", {"x": "Hz"})
    claims = compute_claims({"zzz": zzz, "aaa": aaa}, {"q01.x": "Hz"})
    assert claims["q01.x"] == Claim(type="aaa", instance="q01", stack=["aaa", "zzz"])


def test_palette_assigns_slots_in_type_creation_order():
    """The five palette slots go to the first five Types in creation order,
    one new Type after the other as the GUI sees them."""
    palette = TypePalette()
    palette.sync(["qubit"])
    assert palette.slots == {"qubit": 0}
    palette.sync(["qubit", "readout"])
    palette.sync(["qubit", "readout", "mixer", "attenuator", "script"])
    assert palette.slots == {
        "qubit": 0,
        "readout": 1,
        "mixer": 2,
        "attenuator": 3,
        "script": 4,
    }


def test_palette_recycles_slot_zero_when_exhausted():
    """A sixth Type reuses slot 0 when all five slots are taken (the mock's
    freeTint recycles when exhausted)."""
    palette = TypePalette()
    palette.sync([f"type{index}" for index in range(5)])
    palette.sync([f"type{index}" for index in range(6)])
    assert palette.slots["type5"] == 0


def test_palette_frees_the_slot_of_a_removed_type():
    """Removing a Type frees its slot and the next new Type takes the
    lowest free slot."""
    palette = TypePalette()
    palette.sync(["a", "b", "c", "d", "e"])
    palette.sync(["a", "b", "d", "e"])  # c was removed
    palette.sync(["a", "b", "d", "e", "f"])  # a new Type arrives
    assert palette.slots["f"] == 2


def test_palette_keeps_the_slot_of_an_existing_type_across_updates():
    """A ``pm-type-update`` for an existing Type never changes its colour:
    the slot survives the update and an order change in the state."""
    palette = TypePalette()
    palette.sync(["a", "b", "c"])
    before = dict(palette.slots)
    palette.sync(["a", "b", "c"])  # the update itself
    palette.sync(["c", "b", "a"])  # ... and a reordered state
    assert palette.slots == before


def test_the_parameters_view_moves_into_a_tab_widget(qtbot, pm, server_port):
    """The existing widget becomes tab 0 ("Parameters") of a QTabWidget;
    tab 1 ("Types") is an empty placeholder for its own task; the gutter
    column is wired into the view: visual position 0, fixed width, its own
    delegate reading the GUI's palette, tree branches on the name column."""
    gui = _make_gui(qtbot, pm, server_port)
    try:
        assert gui.tabs.count() == 2
        assert gui.tabs.tabText(0) == "Parameters"
        assert gui.tabs.tabText(1) == "Types"
        parameters_tab = gui.tabs.widget(0)
        assert parameters_tab is gui.parametersTab
        assert parameters_tab.isAncestorOf(gui.view)
        types_tab = gui.tabs.widget(1)
        assert types_tab is gui.typesTab
        assert types_tab.findChildren(QtWidgets.QWidget) == []

        header = gui.view.header()
        assert header.visualIndex(GUTTER_COLUMN) == 0
        assert header.sectionSize(GUTTER_COLUMN) == GUTTER_WIDTH
        assert isinstance(
            gui.view.itemDelegateForColumn(GUTTER_COLUMN), GutterDelegate
        )
        assert gui.view.gutterDelegate.typePalette is gui.typePalette
        assert gui.view.treePosition() == 0
        # the Lock column sits between the unit and the delegate column
        # (visual order: gutter, name, unit, locked to, delegate), with a
        # resizable default width and its header label
        assert header.visualIndex(LOCK_COLUMN) == 3
        assert header.visualIndex(2) == 4
        assert header.sectionSize(LOCK_COLUMN) == LOCK_COLUMN_WIDTH
        assert gui.model.horizontalHeaderItem(LOCK_COLUMN).text() == "locked to"
    finally:
        gui.model.stopListener()


def _row_items(gui, path):
    """The five items of the row ``path``: name, unit, delegate, gutter and
    Lock column."""
    matches = gui.model.findItems(
        path,
        QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive,
        0,
    )
    assert matches, f"no row {path!r} in the model"
    item = matches[0]
    parent = item.parent()
    if parent is None:
        return [gui.model.item(item.row(), column) for column in range(5)]
    return [parent.child(item.row(), column) for column in range(5)]


def _lock_item(gui, path):
    """The Lock column item of the row ``path``."""
    return _row_items(gui, path)[LOCK_COLUMN]


def _type_tint(gui, type_name):
    """The (tint, tintAlt) pair of the Type's palette slot, or ``None``
    while the GUI has not assigned the Type a slot."""
    slot = gui.typePalette.slots.get(type_name)
    if slot is None:
        return None
    entry = TINT_COLOURS[slot]
    return (entry["tint"], entry["tintAlt"])


def test_tints_follow_a_second_clients_type(qtbot, pm, second_client, server_port):
    """A Type the second Client adds tints the rows its Instances carry
    (including the Instance row itself) and marks the gutter stack; when
    its entries and then the Type are removed, the rows lose them again."""
    second_pm = _second_parameter_manager(second_client)
    pm.add_parameter("q01.IF", initial_value=1.0, unit="Hz")
    pm.add_parameter("q01.readout.bw", initial_value=2.0, unit="Hz")
    pm.add_parameter("q02.IF", initial_value=3.0, unit="V")
    pm.add_parameter("other.x", initial_value=4.0, unit="s")
    pm.update()  # the GUI's tree is built from the proxy's blueprint

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        # no creation side effect: q01 already carries IF with the unit the
        # entry declares, and no other submodule matches
        second_pm.add_type("qubit")
        second_pm.add_type_parameter("qubit", "IF", unit="Hz")

        qtbot.waitUntil(
            lambda: _type_tint(gui, "qubit") is not None
            and _row_items(gui, "q01.IF")[0].data(
                QtCore.Qt.ItemDataRole.BackgroundRole
            )
            in _type_tint(gui, "qubit"),
            timeout=BROADCAST_TIMEOUT,
        )
        tint = _type_tint(gui, "qubit")
        for path in ("q01", "q01.IF"):
            # every column of a claimed row carries the tint: name, unit,
            # delegate and gutter
            for item in _row_items(gui, path):
                assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) in tint
        assert _row_items(gui, "q01.IF")[3].data(GUTTER_ROLE) == ["qubit"]
        # a wrong unit and an unrelated row carry no background
        for path in ("q02.IF", "other.x"):
            for item in _row_items(gui, path):
                assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) is None

        # q01 already carries readout.bw: no creation, and the row tints too
        second_pm.add_type_parameter("qubit", "readout.bw", unit="Hz")
        qtbot.waitUntil(
            lambda: _row_items(gui, "q01.readout.bw")[0].data(
                QtCore.Qt.ItemDataRole.BackgroundRole
            )
            in tint,
            timeout=BROADCAST_TIMEOUT,
        )
        for item in _row_items(gui, "q01.readout.bw"):
            assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) in tint
        for item in _row_items(gui, "q01.IF"):
            assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) in tint

        # emptying the Type takes the tint and the gutter band away again
        second_pm.remove_type_parameter("qubit", "IF")
        second_pm.remove_type_parameter("qubit", "readout.bw")
        qtbot.waitUntil(
            lambda: _row_items(gui, "q01.IF")[0].data(
                QtCore.Qt.ItemDataRole.BackgroundRole
            )
            is None
            and _row_items(gui, "q01.IF")[3].data(GUTTER_ROLE) == [],
            timeout=BROADCAST_TIMEOUT,
        )

        # removing the Type clears the last tint and frees the palette slot
        second_pm.remove_type("qubit")
        qtbot.waitUntil(
            lambda: _row_items(gui, "q01.readout.bw")[0].data(
                QtCore.Qt.ItemDataRole.BackgroundRole
            )
            is None
            and "qubit" not in gui.typePalette.slots,
            timeout=BROADCAST_TIMEOUT,
        )
    finally:
        gui.model.stopListener()


def test_refresh_all_recomputes_tints_after_a_model_reload(
    qtbot, pm, second_client, server_port
):
    """With the listener stopped, a Type the second Client adds still tints
    the rows once refreshAll reloads the model and the state."""
    second_pm = _second_parameter_manager(second_client)
    pm.add_parameter("eq01.IF", initial_value=1.0, unit="Hz")
    pm.update()

    gui = _make_gui(qtbot, pm, server_port)
    try:
        gui.model.stopListener()
        # no creation side effect: eq01 already carries IF with the unit the
        # entry declares
        second_pm.add_type("equbit")
        second_pm.add_type_parameter("equbit", "IF", unit="Hz")
        assert (
            _row_items(gui, "eq01.IF")[0].data(
                QtCore.Qt.ItemDataRole.BackgroundRole
            )
            is None
        )

        gui.refreshAll()
        entry = TINT_COLOURS[gui.typePalette.slots["equbit"]]
        for item in _row_items(gui, "eq01.IF"):
            assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) in (
                entry["tint"],
                entry["tintAlt"],
            )
        assert _row_items(gui, "eq01.IF")[3].data(GUTTER_ROLE) == ["equbit"]
    finally:
        gui.model.stopListener()


def test_a_deletion_broadcast_recomputes_the_tints(
    qtbot, pm, second_client, server_port
):
    """A parameter-deletion Broadcast from a second Client removes the row
    and recomputes the tints: the submodule that stops carrying the whole
    set loses its Claim, so the surviving rows show no tint and no gutter
    band. Deletion is safe live (the model's deletion branch touches no
    Proxy blueprint); creation stays off-limits (TEST_AUDIT trap)."""
    second_pm = _second_parameter_manager(second_client)
    pm.add_parameter("q01.IF", initial_value=1.0, unit="Hz")
    pm.add_parameter("q01.bw", initial_value=2.0, unit="Hz")
    pm.update()  # the GUI's tree is built from the proxy's blueprint

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        # no creation side effect: q01 already carries IF and bw with the
        # units the entries declare
        second_pm.add_type("qubit")
        second_pm.add_type_parameter("qubit", "IF", unit="Hz")
        second_pm.add_type_parameter("qubit", "bw", unit="Hz")

        qtbot.waitUntil(
            lambda: _type_tint(gui, "qubit") is not None
            and _row_items(gui, "q01.bw")[0].data(
                QtCore.Qt.ItemDataRole.BackgroundRole
            )
            in _type_tint(gui, "qubit"),
            timeout=BROADCAST_TIMEOUT,
        )
        tint = _type_tint(gui, "qubit")
        for item in _row_items(gui, "q01.IF"):
            assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) in tint

        # removing the parameter makes q01 stop matching, so the whole Type
        # claim is gone: the row is removed and the survivors untint
        second_pm.remove_parameter("q01.bw")

        def _q01_bw_gone_and_q01_untinted():
            matches = gui.model.findItems(
                "q01.bw",
                QtCore.Qt.MatchFlag.MatchExactly
                | QtCore.Qt.MatchFlag.MatchRecursive,
                0,
            )
            if matches:
                return False
            items = _row_items(gui, "q01.IF")
            return (
                all(
                    item.data(QtCore.Qt.ItemDataRole.BackgroundRole) is None
                    for item in items
                )
                and items[3].data(GUTTER_ROLE) == []
            )

        qtbot.waitUntil(
            _q01_bw_gone_and_q01_untinted, timeout=BROADCAST_TIMEOUT
        )
        for item in _row_items(gui, "q01"):
            assert item.data(QtCore.Qt.ItemDataRole.BackgroundRole) is None
    finally:
        gui.model.stopListener()


# ---------------------------------------------------------------------------
# plan task 5.3: Lock column, toggle, context menu, arm strip
# ---------------------------------------------------------------------------


def test_relative_path_strips_the_instrument_name():
    """Lock Targets are stored as full dotted paths; every string the GUI
    shows is relative to the Parameter Manager."""
    assert relative_path(f"{PM_NAME}.q01.IF", PM_NAME) == "q01.IF"
    # a path without the prefix is returned unchanged
    assert relative_path("q01.IF", PM_NAME) == "q01.IF"


def test_lock_column_text_shows_the_three_forms():
    """A Follower shows ``locked to <target>`` or ``unlocked · <target>``
    (relative Target, middle dot); a Target of N Locks — locked and
    unlocked alike — shows ``target ×N``; everything else shows nothing."""
    locks = {
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=False),
    }
    assert lock_column_text("q02.IF", locks, PM_NAME) == "locked to q01.IF"
    assert lock_column_text("q03.IF", locks, PM_NAME) == "unlocked · q01.IF"
    # the Target note counts unlocked Locks too
    assert lock_column_text("q01.IF", locks, PM_NAME) == "target ×2"
    assert lock_column_text("other.x", locks, PM_NAME) == ""
    assert lock_column_text("q01", locks, PM_NAME) == ""


def test_lock_column_text_follower_text_wins_over_the_target_note():
    """A row that is both Follower and Target shows its own Lock state,
    like the mock's ``rec.lockedTo || srcNote(p)``."""
    locks = {
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
        "q01.IF": PMLockBluePrint(target=f"{PM_NAME}.other.x", locked=False),
    }
    assert lock_column_text("q01.IF", locks, PM_NAME) == "unlocked · other.x"


def test_followers_reaching_walks_locked_chains():
    """Every Follower whose locked Lock targets the parameter directly or
    over a chain of locked Locks; the direct Follower and the middle hop
    both reach ``q01.IF``."""
    locks = {
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
    }
    assert sorted(followers_reaching("q01.IF", locks, PM_NAME)) == [
        "q02.IF",
        "q03.IF",
    ]
    assert followers_reaching("q02.IF", locks, PM_NAME) == ["q03.IF"]
    assert followers_reaching("q03.IF", locks, PM_NAME) == []


def test_an_unlocked_middle_hop_stops_the_chain():
    """An unlocked Lock answers ``get`` with its own value (D7), so the
    Followers behind it do not see an update made past it."""
    locks = {
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=False),
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
    }
    assert followers_reaching("q01.IF", locks, PM_NAME) == []
    assert followers_reaching("q02.IF", locks, PM_NAME) == ["q03.IF"]


def test_a_cycle_in_the_locks_does_not_loop():
    """A Lock mapping that holds a cycle terminates the walk."""
    locks = {
        "q01.IF": PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
    }
    assert sorted(followers_reaching("q01.IF", locks, PM_NAME)) == [
        "q01.IF",
        "q02.IF",
    ]


def test_rank_lock_targets_orders_like_the_mock():
    """Rank 0 (same relative path inside its Instance) before rank 1 (the
    relative path occurs as a submodule) before rank 2, alphabetical
    within a rank, the Follower itself excluded."""
    claims = {
        "q01.IF": Claim(type="qubit", instance="q01", stack=["qubit"]),
        "q02.IF": Claim(type="qubit", instance="q02", stack=["qubit"]),
    }
    candidates = ["q01.IF", "q05.IF.gain", "other.x", "other.a", "q02.IF"]
    ranked = rank_lock_targets("q01.IF", candidates, claims)
    assert ranked == ["q02.IF", "q05.IF.gain", "other.a", "other.x"]


def test_rank_lock_targets_without_a_claim_is_alphabetical():
    """A Follower claimed by no Type has no relative path to prefer, so
    every candidate is rank 2 and sorts alphabetically."""
    ranked = rank_lock_targets(
        "q01.IF", ["zz.x", "aa.x", "q01.IF"], {}
    )
    assert ranked == ["aa.x", "zz.x"]


def test_lock_arm_strip_picks_cancels_and_shows_errors(qtbot):
    """The arm strip picks with Return (the exact path, or the first
    ranked candidate when the text is not a path), cancels with Escape and
    the Cancel button, shows the error text, and disarms."""
    strip = LockArmStrip()
    qtbot.addWidget(strip)
    picked = []
    strip.targetPicked.connect(picked.append)
    cancelled = []
    strip.cancelled.connect(lambda: cancelled.append(True))

    strip.arm("q01.IF", ["q02.IF", "q03.IF"])
    assert strip.label.text() == "Target for q01.IF"
    assert strip.completerModel.stringList() == ["q02.IF", "q03.IF"]
    assert not strip.isHidden()

    strip.lineEdit.setText("q02.IF")
    qtbot.keyClick(strip.lineEdit, QtCore.Qt.Key.Key_Return)
    assert picked == ["q02.IF"]

    # the completer popup's pick path (the activated signal) emits too
    strip.arm("q01.IF", ["q02.IF", "q03.IF"])
    strip.completer.activated[str].emit("q03.IF")
    assert picked == ["q02.IF", "q03.IF"]

    # a text that matches no candidate picks nothing (no unrelated Target)
    strip.arm("q01.IF", ["q02.IF", "q03.IF"])
    strip.lineEdit.setText("garbage")
    qtbot.keyClick(strip.lineEdit, QtCore.Qt.Key.Key_Return)
    assert picked == ["q02.IF", "q03.IF"]

    # a partial text that matches picks the first filtered completion
    strip.arm("q01.IF", ["q02.IF", "q03.IF"])
    strip.lineEdit.setText("q03")
    qtbot.keyClick(strip.lineEdit, QtCore.Qt.Key.Key_Return)
    assert picked == ["q02.IF", "q03.IF", "q03.IF"]

    # the error label shows the Server's text until the next disarm
    strip.show_error("cycle: cannot lock q02.IF to q01.IF")
    assert strip.errorLabel.text() == "cycle: cannot lock q02.IF to q01.IF"
    assert not strip.errorLabel.isHidden()

    # Escape cancels while the strip has focus; the strip only emits the
    # signal — hiding on cancel is the GUI's cancel_arm
    strip.show()
    qtbot.waitExposed(strip)
    strip.activateWindow()
    strip.lineEdit.setFocus()
    qtbot.wait(20)
    qtbot.keyClick(strip.lineEdit, QtCore.Qt.Key.Key_Escape)
    assert cancelled == [True]

    # so does the Cancel button, and disarming hides and clears the strip
    strip.arm("q01.IF", ["q02.IF"])
    strip.show_error("cycle: cannot lock q02.IF to q01.IF")
    strip.cancelButton.click()
    assert cancelled == [True, True]
    strip.disarm()
    assert strip.isHidden()
    assert strip.errorLabel.isHidden() and strip.errorLabel.text() == ""


def test_parameter_widget_set_read_only(qtbot):
    """set_read_only disables the input and the set button and keeps the
    get button enabled, and stores the flag."""
    from instrumentserver.params import ParameterManager

    manager = ParameterManager("pw_read_only_local")
    manager.add_parameter("x", initial_value=1.0)
    widget = ParameterWidget(manager.parameter("x"))
    qtbot.addWidget(widget)

    assert widget.read_only is False
    widget.set_read_only(True)
    assert widget.read_only is True
    assert not widget.paramWidget.isEnabled()
    assert not widget.setButton.isEnabled()
    assert widget.getButton.isEnabled()

    widget.set_read_only(False)
    assert widget.read_only is False
    assert widget.paramWidget.isEnabled()
    assert widget.setButton.isEnabled()
    assert widget.getButton.isEnabled()


def _make_live_parameters(pm):
    """Create the 5.3 live tests' parameters before the GUI is built (a
    parameter another Client creates while the GUI is open crashes the
    model's parameter-creation branch, TEST_AUDIT.md)."""
    pm.add_parameter("q01.IF", initial_value=1.0, unit="Hz")
    pm.add_parameter("q02.IF", initial_value=2.0, unit="Hz")
    pm.add_parameter("q03.IF", initial_value=3.0, unit="Hz")
    pm.add_parameter("other.x", initial_value=4.0, unit="s")
    pm.update()  # the GUI's tree is built from the proxy's blueprint


def _click_row(qtbot, gui, path):
    """Click the tree row ``path`` with the left mouse button; the GUI must
    be shown for the view to have geometry."""
    gui.show()
    qtbot.waitExposed(gui)
    gui.view.expandAll()
    source_index = gui.model.indexFromItem(_row_items(gui, path)[0])
    proxy_index = gui.proxyModel.mapFromSource(source_index)
    qtbot.mouseClick(
        gui.view.viewport(),
        QtCore.Qt.MouseButton.LeftButton,
        pos=gui.view.visualRect(proxy_index).center(),
    )


def test_arm_via_context_menu_pick_a_row_and_toggle(
    qtbot, pm, second_client, server_port
):
    """The plan's named flow: arm through the context menu, pick a row to
    lock, watch the Lock column and the lock button repaint through the
    Broadcast, toggle with the lock button both ways, and unlock through
    the context menu."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        gui.view.lastSelectedItem = _row_items(gui, "q01.IF")[0]
        gui.view.lockToAction.trigger()

        assert not gui.armStrip.isHidden()
        assert gui.armStrip.label.text() == "Target for q01.IF"
        assert gui.armed_follower == "q01.IF"
        candidates = gui.armStrip.completerModel.stringList()
        assert "q02.IF" in candidates
        assert "q01.IF" not in candidates

        # clicking the q02.IF row picks it as the Target
        _click_row(qtbot, gui, "q02.IF")
        qtbot.waitUntil(
            lambda: pm.get_lock("q01.IF")
            == PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
            timeout=BROADCAST_TIMEOUT,
        )
        assert gui.armStrip.isHidden()
        assert gui.armed_follower is None

        # the pm-lock-update Broadcast repaints the Lock column and the
        # lock button, and renders the locked Follower read-only
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q01.IF").text() == "locked to q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )
        assert _lock_item(gui, "q02.IF").text() == "target ×1"

        follower_widget = gui.view.delegate.parameters["q01.IF"]
        button = follower_widget.lockButton
        assert not button.isHidden()
        assert button.property("locked") is True
        assert not follower_widget.paramWidget.isEnabled()

        # locking repaints the Follower's value: while locked it answers
        # get with the Target's value (D3)
        qtbot.waitUntil(
            lambda: follower_widget._getMethod() == 2.0,
            timeout=BROADCAST_TIMEOUT,
        )

        # toggle with the lock button: unlock first …
        button.click()
        qtbot.waitUntil(
            lambda: pm.get_lock("q01.IF").locked is False,
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q01.IF").text() == "unlocked · q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )
        assert button.property("locked") is False
        assert follower_widget.paramWidget.isEnabled()

        # unlocking exposes the Follower's own value again (D3, D5)
        qtbot.waitUntil(
            lambda: follower_widget._getMethod() == 1.0,
            timeout=BROADCAST_TIMEOUT,
        )

        # … and lock again to the remembered Target
        button.click()
        qtbot.waitUntil(
            lambda: pm.get_lock("q01.IF").locked is True,
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q01.IF").text() == "locked to q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )
        assert button.property("locked") is True
        qtbot.waitUntil(
            lambda: follower_widget._getMethod() == 2.0,
            timeout=BROADCAST_TIMEOUT,
        )

        # the context menu's Unlock unlocks on the Server
        gui.view.lastSelectedItem = _row_items(gui, "q01.IF")[0]
        gui.view.unlockAction.trigger()
        qtbot.waitUntil(
            lambda: pm.get_lock("q01.IF").locked is False,
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q01.IF").text() == "unlocked · q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )
    finally:
        gui.model.stopListener()


def test_a_cycle_attempt_shows_the_error_and_stays_armed(
    qtbot, pm, second_client, server_port
):
    """Locking the Follower's own Target back would close a cycle (D7):
    the Server refuses, the arm strip shows the error text and stays
    armed, and Escape disarms it."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        pm.lock("q01.IF", "q02.IF")
        qtbot.waitUntil(
            lambda: gui.state.locks.get("q01.IF")
            == PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
            timeout=BROADCAST_TIMEOUT,
        )

        gui.arm_lock("q02.IF")
        assert gui.armed_follower == "q02.IF"
        assert not gui.armStrip.isHidden()

        gui.pick_lock_target("q01.IF")
        assert "cycle" in gui.armStrip.errorLabel.text()
        assert not gui.armStrip.isHidden()
        assert gui.armed_follower == "q02.IF"
        assert pm.get_lock("q02.IF") is None

        # Escape over the tree disarms the pick too (the view's Escape
        # shortcut calls cancel_arm)
        gui.show()
        qtbot.waitExposed(gui)
        gui.view.setFocus()
        qtbot.wait(20)
        qtbot.keyClick(gui.view, QtCore.Qt.Key.Key_Escape)
        assert gui.armStrip.isHidden()
        assert gui.armed_follower is None

        # re-arm: Escape in the strip's line edit disarms as well
        gui.arm_lock("q02.IF")
        assert gui.armed_follower == "q02.IF"
        gui.armStrip.activateWindow()
        gui.armStrip.lineEdit.setFocus()
        qtbot.wait(20)
        qtbot.keyClick(gui.armStrip.lineEdit, QtCore.Qt.Key.Key_Escape)
        assert gui.armStrip.isHidden()
        assert gui.armed_follower is None
    finally:
        gui.model.stopListener()


def test_setting_the_target_from_a_second_client_repaints_the_followers(
    qtbot, pm, second_client, server_port
):
    """A value the second Client sets on a Target repaints every Follower
    whose locked Lock chain reaches it (D3: a locked Follower answers get
    with the Target's value, and nothing is ever pushed into it)."""
    _make_live_parameters(pm)
    # the second Client's proxy is built after the parameters exist, so its
    # blueprint knows q02.IF
    second_pm = _second_parameter_manager(second_client)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        # a chain: q03.IF follows q01.IF, which follows q02.IF
        pm.lock("q01.IF", "q02.IF")
        pm.lock("q03.IF", "q01.IF")
        qtbot.waitUntil(
            lambda: gui.state.locks.get("q01.IF")
            == PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True)
            and gui.state.locks.get("q03.IF")
            == PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
            timeout=BROADCAST_TIMEOUT,
        )

        second_pm.q02.IF.set(7)
        follower_widget = gui.view.delegate.parameters["q01.IF"]
        chain_widget = gui.view.delegate.parameters["q03.IF"]
        qtbot.waitUntil(
            lambda: follower_widget._getMethod() == 7,
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: chain_widget._getMethod() == 7,
            timeout=BROADCAST_TIMEOUT,
        )
    finally:
        gui.model.stopListener()


def test_a_second_clients_lock_shows_in_the_column_and_button(
    qtbot, pm, second_client, server_port
):
    """A Lock the second Client makes shows up in the Lock column and on
    the lock button without any GUI action."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)
        assert _lock_item(gui, "q03.IF").text() == ""

        second_pm.lock("q03.IF", "q02.IF")
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q03.IF").text() == "locked to q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )
        widget = gui.view.delegate.parameters["q03.IF"]
        assert not widget.lockButton.isHidden()
        assert widget.lockButton.property("locked") is True
        assert not widget.paramWidget.isEnabled()
    finally:
        gui.model.stopListener()


def test_the_context_menu_lock_actions_enable_by_the_lock_state(
    qtbot, pm, second_client, server_port
):
    """The aboutToShow rule: "Lock to…" is enabled for every parameter
    row, "Unlock" only while that row's Lock in the state is locked, and
    both are disabled on a submodule row."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        second_pm.lock("q03.IF", "q02.IF")
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q03.IF").text() == "locked to q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )

        # (a) a parameter row with a locked Lock: both enabled
        gui.view.lastSelectedItem = _row_items(gui, "q03.IF")[0]
        gui.view.contextMenu.aboutToShow.emit()
        assert gui.view.lockToAction.isEnabled()
        assert gui.view.unlockAction.isEnabled()

        # (b) the same row after the second Client unlocks: only "Lock
        # to…" stays enabled
        second_pm.unlock("q03.IF")
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q03.IF").text() == "unlocked · q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )
        gui.view.contextMenu.aboutToShow.emit()
        assert gui.view.lockToAction.isEnabled()
        assert not gui.view.unlockAction.isEnabled()

        # (c) a submodule row: both disabled
        gui.view.lastSelectedItem = _row_items(gui, "q03")[0]
        gui.view.contextMenu.aboutToShow.emit()
        assert not gui.view.lockToAction.isEnabled()
        assert not gui.view.unlockAction.isEnabled()
    finally:
        gui.model.stopListener()


def test_refresh_all_shows_a_lock_made_while_the_listener_was_stopped(
    qtbot, pm, second_client, server_port
):
    """With the listener stopped, a Lock the second Client makes still
    reaches the Lock column and the lock button through refreshAll's
    re-read of the state."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        gui.model.stopListener()
        second_pm.lock("q03.IF", "q02.IF")
        assert _lock_item(gui, "q03.IF").text() == ""

        gui.refreshAll()
        assert _lock_item(gui, "q03.IF").text() == "locked to q02.IF"
        widget = gui.view.delegate.parameters["q03.IF"]
        assert not widget.lockButton.isHidden()
        assert widget.lockButton.property("locked") is True
        assert not widget.paramWidget.isEnabled()
    finally:
        gui.model.stopListener()


def test_a_filter_cycle_re_applies_the_lock_state(
    qtbot, pm, second_client, server_port
):
    """A filter cycle re-opens the hidden rows' persistent editors as
    fresh ParameterWidgets; apply_locks runs on filterFinished, so a
    locked Follower comes back with its lock button and read-only input."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        second_pm.lock("q01.IF", "q02.IF")
        qtbot.waitUntil(
            lambda: _lock_item(gui, "q01.IF").text() == "locked to q02.IF",
            timeout=BROADCAST_TIMEOUT,
        )

        def _q01_if_is_mapped(mapped: bool):
            matches = gui.model.findItems(
                "q01.IF",
                QtCore.Qt.MatchFlag.MatchExactly
                | QtCore.Qt.MatchFlag.MatchRecursive,
                0,
            )
            proxy_index = gui.proxyModel.mapFromSource(
                gui.model.indexFromItem(matches[0])
            )
            return proxy_index.isValid() is mapped

        # the filter hides the q01.IF row …
        gui.lineEdit.setText("other")
        qtbot.waitUntil(lambda: _q01_if_is_mapped(False), timeout=BROADCAST_TIMEOUT)

        # … and clearing it brings the row back with its Lock state
        gui.lineEdit.setText("")
        widget = gui.view.delegate.parameters["q01.IF"]
        qtbot.waitUntil(
            lambda: widget.lockButton.property("locked") is True
            and not widget.lockButton.isHidden(),
            timeout=BROADCAST_TIMEOUT,
        )
        assert not widget.paramWidget.isEnabled()
    finally:
        gui.model.stopListener()


# ---------------------------------------------------------------------------
# plan task 5.4: the Locks panel
# ---------------------------------------------------------------------------


def test_build_lock_rows_nests_followers_under_a_plain_target():
    """A plain Target with two Followers — one of them unlocked — builds
    one root with two children, each child carrying its own Lock (locked
    and unlocked alike, D5), and the root carrying none."""
    locks = {
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=False),
    }
    rows = build_lock_rows(locks, {}, PM_NAME)
    assert [row.path for row in rows] == ["q01.IF"]
    root = rows[0]
    assert root.lock is None
    assert root.type_locks == []
    assert [child.path for child in root.children] == ["q02.IF", "q03.IF"]
    assert root.children[0].lock == locks["q02.IF"]
    assert root.children[1].lock == locks["q03.IF"]
    assert root.children[0].children == []


def test_build_lock_rows_walks_a_chain_nested_and_once():
    """A chain q03 → q02 → q01 nests two levels deep and the middle hop
    q02 appears once."""
    locks = {
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
    }
    rows = build_lock_rows(locks, {}, PM_NAME)
    assert [row.path for row in rows] == ["q01.IF"]
    root = rows[0]
    assert [child.path for child in root.children] == ["q02.IF"]
    assert [
        grandchild.path for grandchild in root.children[0].children
    ] == ["q03.IF"]


def test_build_lock_rows_sorts_the_type_lock_target_first():
    """A Type Lock Target sorts before a plain Target and carries the
    (Type, entry) pairs whose stored Target it is."""
    dqubit = PMTypeBluePrint(
        name="dqubit",
        parameters={
            "IF": {
                "default": None,
                "unit": "Hz",
                "target": f"{PM_NAME}.tshared",
            }
        },
        nested={},
        effective={"IF": {"unit": "Hz", "from_type": "dqubit"}},
    )
    locks = {
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.plain.x", locked=True),
        "dq01.IF": PMLockBluePrint(target=f"{PM_NAME}.tshared", locked=True),
    }
    rows = build_lock_rows(locks, {"dqubit": dqubit}, PM_NAME)
    assert [row.path for row in rows] == ["tshared", "plain.x"]
    assert rows[0].type_locks == [("dqubit", "IF")]
    assert rows[1].type_locks == []
    assert [child.path for child in rows[0].children] == ["dq01.IF"]


def test_lock_root_follows_locked_hops_only():
    """lock_root walks locked Locks to the end of the chain and stops at
    an unlocked hop, which answers ``get`` with its own value (D7)."""
    locks = {
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=False),
    }
    assert lock_root("q03.IF", locks, PM_NAME) == "q02.IF"
    assert lock_root("q02.IF", locks, PM_NAME) == "q02.IF"
    assert lock_root("q01.IF", locks, PM_NAME) == "q01.IF"

    all_locked = {
        "q03.IF": PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
        "q02.IF": PMLockBluePrint(target=f"{PM_NAME}.q01.IF", locked=True),
    }
    assert lock_root("q03.IF", all_locked, PM_NAME) == "q01.IF"


def _panel_row_items(gui, path):
    """The three items of the Locks panel row ``path``: label, value and
    buttons."""
    matches = []

    def walk(parent):
        for row in range(parent.rowCount()):
            item = parent.child(row, 0)
            if item is None:
                continue
            if item.data(LOCK_ROW_ROLE) == path:
                matches.append(
                    [parent.child(row, column) for column in range(3)]
                )
            walk(item)

    walk(gui.locksPanel.model.invisibleRootItem())
    assert matches, f"no Locks panel row {path!r}"
    return matches[0]


def _panel_root_paths(gui):
    """The paths of the Locks panel's depth-0 rows."""
    root = gui.locksPanel.model.invisibleRootItem()
    return [root.child(row, 0).data(LOCK_ROW_ROLE) for row in range(root.rowCount())]


def _panel_child_paths(gui, path):
    """The paths of the Locks panel row ``path``'s children."""
    item = _panel_row_items(gui, path)[0]
    return [item.child(row, 0).data(LOCK_ROW_ROLE) for row in range(item.rowCount())]


def test_the_locks_action_toggles_the_panel(qtbot, pm, server_port):
    """The toolbar action is checkable and unchecked, the panel starts
    hidden as the splitter's second pane, and the shortcut is registered;
    triggering the action shows the panel."""
    gui = _make_gui(qtbot, pm, server_port)
    try:
        assert gui.locksAction.isCheckable()
        assert not gui.locksAction.isChecked()
        assert gui.locksPanel.isHidden()
        assert gui.locksSplitter.widget(0) is gui.view
        assert gui.locksSplitter.widget(1) is gui.locksPanel
        assert gui.parametersTab.isAncestorOf(gui.locksSplitter)
        assert KeyboardShortcutManager.REGISTRY["toggle_locks"] == (
            "Ctrl+Shift+L",
            "Show or hide the Locks panel",
        )

        gui.locksAction.trigger()
        assert gui.locksAction.isChecked()
        assert not gui.locksPanel.isHidden()

        gui.locksAction.trigger()
        assert not gui.locksAction.isChecked()
        assert gui.locksPanel.isHidden()
    finally:
        gui.model.stopListener()


def test_the_panel_rows_reflect_list_locks_and_remove_from_the_panel(
    qtbot, pm, second_client, server_port
):
    """The plan's named tests: a second Client's locked chain shows in the
    panel as one root with its Followers beneath; the remove button removes
    the Lock on the Server and the row disappears; a Lock the second Client
    makes while the panel is open appears live; and the second Client
    unlocking a Follower flips its toggle and gives it its editor back."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)
    second_pm.lock("q01.IF", "q02.IF")
    second_pm.lock("q03.IF", "q01.IF")

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)
        assert gui.state.locks == pm.list_locks()

        gui.locksAction.trigger()  # shows the panel and rebuilds its rows
        qtbot.waitUntil(
            lambda: _panel_root_paths(gui) == ["q02.IF"],
            timeout=BROADCAST_TIMEOUT,
        )
        assert _panel_child_paths(gui, "q02.IF") == ["q01.IF"]
        assert _panel_child_paths(gui, "q01.IF") == ["q03.IF"]

        # the root is a plain Target: no buttons and a ParameterWidget
        # value editor; its Followers are locked: a read-only label and the
        # toggle and remove buttons
        root_entry = gui.locksPanel.rowWidgets["q02.IF"]
        assert isinstance(root_entry["editor"], ParameterWidget)
        assert root_entry["toggle"] is None and root_entry["remove"] is None
        follower_entry = gui.locksPanel.rowWidgets["q01.IF"]
        assert follower_entry["label"] is not None
        assert follower_entry["editor"] is None
        assert follower_entry["toggle"] is not None
        assert follower_entry["remove"] is not None
        grandchild_entry = gui.locksPanel.rowWidgets["q03.IF"]
        assert grandchild_entry["label"] is not None

        # press the remove button of q03.IF: the Lock goes on the Server
        gui.locksPanel.rowWidgets["q03.IF"]["remove"].click()
        qtbot.waitUntil(
            lambda: pm.get_lock("q03.IF") is None, timeout=BROADCAST_TIMEOUT
        )
        qtbot.waitUntil(
            lambda: "q03.IF" not in _panel_child_paths(gui, "q01.IF"),
            timeout=BROADCAST_TIMEOUT,
        )
        assert "q03.IF" not in gui.locksPanel.rowWidgets

        # live update: a Lock the second Client makes appears as a new
        # child row
        second_pm.lock("other.x", "q02.IF")
        qtbot.waitUntil(
            lambda: "other.x" in _panel_child_paths(gui, "q02.IF"),
            timeout=BROADCAST_TIMEOUT,
        )

        # the second Client unlocks q01.IF: the toggle goes unlocked and
        # the value cell becomes an editor again
        second_pm.unlock("q01.IF")

        def _q01_unlocked_in_panel():
            entry = gui.locksPanel.rowWidgets.get("q01.IF")
            return (
                entry is not None
                and entry["toggle"] is not None
                and entry["toggle"].property("locked") is False
                and entry["editor"] is not None
            )

        qtbot.waitUntil(_q01_unlocked_in_panel, timeout=BROADCAST_TIMEOUT)
    finally:
        gui.model.stopListener()


def test_the_type_lock_rows_lock_all_and_remove_rule(
    qtbot, pm, second_client, server_port
):
    """A Type Lock Target is the panel's first root, labelled with its
    Type; "remove rule" clears only the rule and leaves the Locks; and
    "lock all" locks an unlocked Follower again through the stored
    Target."""
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

        gui.locksAction.trigger()
        qtbot.waitUntil(
            lambda: _panel_root_paths(gui) == ["tshared"],
            timeout=BROADCAST_TIMEOUT,
        )
        assert _panel_row_items(gui, "tshared")[0].text() == "[type: dqubit] tshared"
        assert _panel_child_paths(gui, "tshared") == ["dq01.IF", "dq02.IF"]

        # "remove rule": only the rule goes; both Locks stay
        gui.locksPanel.rowWidgets["tshared"]["removeRule"].click()
        qtbot.waitUntil(
            lambda: pm.get_type("dqubit").parameters["IF"]["target"] is None,
            timeout=BROADCAST_TIMEOUT,
        )
        assert set(pm.list_locks()) == {"dq01.IF", "dq02.IF"}
        qtbot.waitUntil(
            lambda: _panel_row_items(gui, "tshared")[0].text() == "tshared",
            timeout=BROADCAST_TIMEOUT,
        )

        # re-declare the Type Lock from the second Client, then unlock
        # dq01.IF from there too; the panel's row carries its "lock all"
        # button again once the Type Broadcast arrived and the rebuild ran
        second_pm.lock_type_parameter("dqubit", "IF", target="tshared")
        second_pm.unlock("dq01.IF")
        qtbot.waitUntil(
            lambda: pm.get_lock("dq01.IF") is not None
            and pm.get_lock("dq01.IF").locked is False,
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: (
                gui.state.locks.get("dq01.IF") is not None
                and gui.state.locks["dq01.IF"].locked is False
            ),
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: (
                gui.locksPanel.rowWidgets.get("tshared") is not None
                and gui.locksPanel.rowWidgets["tshared"]["lockAll"] is not None
            ),
            timeout=BROADCAST_TIMEOUT,
        )

        # ... and "lock all" locks it again through the stored Target
        gui.locksPanel.rowWidgets["tshared"]["lockAll"].click()
        qtbot.waitUntil(
            lambda: pm.get_lock("dq01.IF") is not None
            and pm.get_lock("dq01.IF").locked,
            timeout=BROADCAST_TIMEOUT,
        )
        # "lock all" passes the entry's stored Target: a call without it
        # would re-point the rule to the Globals default (D17)
        qtbot.waitUntil(
            lambda: pm.get_type("dqubit").parameters["IF"]["target"]
            == f"{PM_NAME}.tshared",
            timeout=BROADCAST_TIMEOUT,
        )
        assert pm.get_lock("dq01.IF").target == f"{PM_NAME}.tshared"
        assert not any(path.startswith("_globals") for path in pm.list())
    finally:
        gui.model.stopListener()


def test_the_lock_all_note_names_the_skipped_followers(
    qtbot, pm, second_client, server_port
):
    """"lock all" names the Instance parameters it skips on the note
    label and leaves them locked to their own Target (D17): one whose
    Lock the second Client re-targeted keeps that Target."""
    second_pm = _second_parameter_manager(second_client)
    second_pm.add_parameter("dq01.IF", initial_value=1.0, unit="Hz")
    second_pm.add_parameter("dq02.IF", initial_value=2.0, unit="Hz")
    # root-level parameters: the root is never an Instance, so targeting
    # them cannot self-lock an Instance parameter
    second_pm.add_parameter("tshared", initial_value=0.0, unit="Hz")
    second_pm.add_parameter("talt", initial_value=9.0, unit="Hz")
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

        gui.locksAction.trigger()
        qtbot.waitUntil(
            lambda: _panel_root_paths(gui) == ["tshared"],
            timeout=BROADCAST_TIMEOUT,
        )

        # the second Client re-targets one Instance parameter; waiting for
        # the GUI's state makes sure the rebuild that replaces the panel's
        # buttons has run before the click
        second_pm.lock("dq01.IF", "talt")
        qtbot.waitUntil(
            lambda: pm.get_lock("dq01.IF") is not None
            and pm.get_lock("dq01.IF").target == f"{PM_NAME}.talt",
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: (
                gui.state.locks.get("dq01.IF") is not None
                and gui.state.locks["dq01.IF"].target == f"{PM_NAME}.talt"
            ),
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: (
                gui.locksPanel.rowWidgets.get("tshared") is not None
                and gui.locksPanel.rowWidgets["tshared"]["lockAll"] is not None
            ),
            timeout=BROADCAST_TIMEOUT,
        )

        # "lock all": dq01.IF is skipped, named on the note label, and
        # stays locked to its own Target
        gui.locksPanel.rowWidgets["tshared"]["lockAll"].click()
        qtbot.waitUntil(
            lambda: "skipped: dq01.IF" in gui.locksPanel.noteLabel.text(),
            timeout=BROADCAST_TIMEOUT,
        )
        assert pm.get_lock("dq01.IF").target == f"{PM_NAME}.talt"
    finally:
        gui.model.stopListener()


def test_the_panel_value_editor_sets_the_target(
    qtbot, pm, second_client, server_port
):
    """Typing a value into the root Target's editor and pressing its set
    button sets the parameter on the Server, and the tree's Follower row
    repaints to it (5.3's repaint path). A second Client's set repaints
    the panel in place: the root editor and the locked Follower's
    read-only label both show the new value without a rebuild."""
    # the second Client's proxy is built after the parameters exist, so
    # its blueprint knows q02.IF (attribute access resolves through it)
    _make_live_parameters(pm)
    second_pm = _second_parameter_manager(second_client)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)

        second_pm.lock("q01.IF", "q02.IF")
        qtbot.waitUntil(
            lambda: gui.state.locks.get("q01.IF")
            == PMLockBluePrint(target=f"{PM_NAME}.q02.IF", locked=True),
            timeout=BROADCAST_TIMEOUT,
        )

        gui.locksAction.trigger()
        qtbot.waitUntil(
            lambda: _panel_root_paths(gui) == ["q02.IF"],
            timeout=BROADCAST_TIMEOUT,
        )
        editor = gui.locksPanel.rowWidgets["q02.IF"]["editor"]
        assert editor is not None

        editor.paramWidget.input.setText("11")
        editor.setButton.click()
        qtbot.waitUntil(
            lambda: pm.q02.IF.get() == 11, timeout=BROADCAST_TIMEOUT
        )
        tree_widget = gui.view.delegate.parameters["q01.IF"]
        qtbot.waitUntil(
            lambda: tree_widget._getMethod() == 11, timeout=BROADCAST_TIMEOUT
        )

        # the second Client's set reaches the panel without a local echo:
        # the root editor and the locked Follower's read-only label are
        # refreshed in place (a no-op refresh_values would fail here)
        second_pm.q02.IF.set(21)
        qtbot.waitUntil(
            lambda: (
                gui.locksPanel.rowWidgets.get("q02.IF") is not None
                and gui.locksPanel.rowWidgets["q02.IF"]["editor"] is not None
                and gui.locksPanel.rowWidgets["q02.IF"]["editor"]._getMethod()
                == 21
            ),
            timeout=BROADCAST_TIMEOUT,
        )
        qtbot.waitUntil(
            lambda: (
                gui.locksPanel.rowWidgets.get("q01.IF") is not None
                and gui.locksPanel.rowWidgets["q01.IF"]["label"] is not None
                and gui.locksPanel.rowWidgets["q01.IF"]["label"].text() == "21"
            ),
            timeout=BROADCAST_TIMEOUT,
        )
    finally:
        gui.model.stopListener()


def test_lock_selection_to_arms_the_tree_row(qtbot, pm, second_client, server_port):
    """"Lock selection to…" shows the tree's current parameter in the
    selected label and arms the pick for it; on a submodule row it says so
    on the note label and arms nothing."""
    second_pm = _second_parameter_manager(second_client)
    _make_live_parameters(pm)

    gui = _make_gui(qtbot, pm, server_port)
    try:
        _wait_until_broadcasts_arrive(qtbot, gui, second_pm)
        gui.locksAction.trigger()
        assert gui.locksPanel.selectedLabel.text() == "no parameter selected"

        # select the other.x row in the tree: the label follows it
        source_index = gui.model.indexFromItem(_row_items(gui, "other.x")[0])
        gui.view.setCurrentIndex(gui.proxyModel.mapFromSource(source_index))
        qtbot.waitUntil(
            lambda: gui.locksPanel.selectedLabel.text() == "other.x",
            timeout=BROADCAST_TIMEOUT,
        )

        gui.locksPanel.lockSelectionButton.click()
        assert gui.armed_follower == "other.x"
        assert not gui.armStrip.isHidden()

        # a fresh pick, then a submodule row: the label shows that no
        # parameter is selected and pressing arms nothing
        gui.cancel_arm()
        source_index = gui.model.indexFromItem(_row_items(gui, "other")[0])
        gui.view.setCurrentIndex(gui.proxyModel.mapFromSource(source_index))
        qtbot.waitUntil(
            lambda: gui.locksPanel.selectedLabel.text() == "no parameter selected",
            timeout=BROADCAST_TIMEOUT,
        )
        gui.locksPanel.lockSelectionButton.click()
        assert (
            "Select a parameter in the tree first."
            in gui.locksPanel.noteLabel.text()
        )
        assert gui.armed_follower is None
        assert gui.armStrip.isHidden()
    finally:
        gui.model.stopListener()


def test_a_panel_action_error_shows_on_the_note_label(qtbot, pm, server_port):
    """A refused panel action shows the Server's error text on the note
    label, and the next successful action restores the default note. The
    panel's toggle button runs the same action as the signal: unlock, then
    lock again."""
    pm.add_parameter("q01.x", initial_value=1.0, unit="Hz")
    pm.add_parameter("q02.x", initial_value=2.0, unit="Hz")
    pm.lock("q02.x", "q01.x")
    pm.update()  # the GUI's tree is built from the proxy's blueprint

    gui = _make_gui(qtbot, pm, server_port)
    try:
        gui.locksAction.trigger()

        # the panel's toggle button is wired to the same action: unlock,
        # then lock again; the rebuild replaces the button, so it is
        # re-read from rowWidgets before the second click
        gui.locksPanel.rowWidgets["q02.x"]["toggle"].click()
        qtbot.waitUntil(
            lambda: pm.get_lock("q02.x").locked is False,
            timeout=BROADCAST_TIMEOUT,
        )

        def _unlocked_toggle_back():
            entry = gui.locksPanel.rowWidgets.get("q02.x")
            return (
                entry is not None
                and entry["toggle"] is not None
                and entry["toggle"].property("locked") is False
            )

        qtbot.waitUntil(_unlocked_toggle_back, timeout=BROADCAST_TIMEOUT)
        gui.locksPanel.rowWidgets["q02.x"]["toggle"].click()
        qtbot.waitUntil(
            lambda: pm.get_lock("q02.x").locked is True,
            timeout=BROADCAST_TIMEOUT,
        )

        gui.locksPanel.toggleLockRequested.emit("no.such")
        assert "no.such" in gui.locksPanel.noteLabel.text()

        # a successful action restores the default note
        gui.locksPanel.toggleLockRequested.emit("q02.x")
        qtbot.waitUntil(
            lambda: pm.get_lock("q02.x").locked is False,
            timeout=BROADCAST_TIMEOUT,
        )
        assert gui.locksPanel.noteLabel.text() == LOCK_PANEL_NOTE
    finally:
        gui.model.stopListener()
