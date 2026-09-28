"""Client-side state and Broadcast handling of the Parameter Manager GUI
(plan task 5.1), plus its tabs, tints and gutter bands (plan task 5.2).

The GUI keeps the Parameter Manager's Types and Locks in a ``PMState``
(``ParameterManagerGui.state``), filled from the Parameter Manager on
construction and on every refresh, and kept current by the
``pm-lock-update`` and ``pm-type-update`` Broadcasts the model routes to it.
A second Client's changes must reach that state and the tree's value
widgets without any polling, so every cross-client assertion waits with
``qtbot.waitUntil``. The 5.2 tests cover the tab widget around the
existing view, the pure ``compute_claims`` function and the tint palette
without a Server, and the tints and gutter bands a second Client's Type
edits produce live.

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
    TINT_COLOURS,
    Claim,
    GutterDelegate,
    ItemParameters,
    ModelParameters,
    ParameterManagerGui,
    ParameterManagerTreeView,
    PMState,
    TypePalette,
    compute_claims,
)

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
    finally:
        gui.model.stopListener()


def _row_items(gui, path):
    """The four items of the row ``path``: name, unit, delegate, gutter."""
    matches = gui.model.findItems(
        path,
        QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive,
        0,
    )
    assert matches, f"no row {path!r} in the model"
    item = matches[0]
    parent = item.parent()
    if parent is None:
        return [gui.model.item(item.row(), column) for column in range(4)]
    return [parent.child(item.row(), column) for column in range(4)]


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
