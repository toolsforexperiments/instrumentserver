"""Tests for ``ManagedParameter`` and the Lock API (plan tasks 1.1–1.3).

The first part wires two standalone ManagedParameters (a Target and a
Follower) by hand, with no Parameter Manager involved. The second part
exercises the Lock API on a local Parameter Manager (``lock``, ``unlock``,
``relock``, ``toggle_lock``, ``remove_lock``, ``get_lock``, ``list_locks``,
``followers_of``, and the ``remove_parameter`` Lock cleanup). The third
part checks the ``pm-lock-update`` Broadcasts the Lock methods emit
(D10), on a local Parameter Manager with a Broadcast sink. The last part
exercises the Lock API through a client proxy against a live Server: every
method callable over the wire, ``get_lock``/``list_locks`` deserialising
to ``PMLockBluePrint``, the pull-on-get value over the wire, and a
SubClient receiving the Broadcasts.
"""

import logging
import re

import pytest

from instrumentserver.blueprints import (
    PM_LOCK_UPDATE,
    ParameterBroadcastBluePrint,
    PMLockBluePrint,
)
from instrumentserver.params import (
    ManagedParameter,
    ParameterGroup,
    ParameterManager,
)


def make_target_and_follower():
    """A Target and a Follower, both standalone ManagedParameters."""
    target = ManagedParameter("target", set_cmd=None, initial_value=11, unit="V")
    follower = ManagedParameter("follower", set_cmd=None, initial_value=22, unit="V")
    return target, follower


def lock_follower(follower, target, locked=True):
    """Attach a Lock to the Follower directly (no manager: task 1.2 adds
    the Lock API)."""
    follower._target = target
    follower.lock = PMLockBluePrint(target=target.path, locked=locked)


class CountingManagedParameter(ManagedParameter):
    """ManagedParameter that counts how often its value is read."""

    def __init__(self, name, **kwargs):
        self.get_calls = 0
        super().__init__(name, **kwargs)

    def get_raw(self):
        self.get_calls += 1
        return super().get_raw()


def test_get_redirects_to_target_while_locked():
    target, follower = make_target_and_follower()
    assert follower.get() == 22

    lock_follower(follower, target)
    assert follower.locked
    assert follower.get() == 11

    # pull on get: changing the Target is enough, nothing is pushed
    target.set(33)
    assert follower.get() == 33


def test_set_while_locked_raises_and_names_the_target():
    target, follower = make_target_and_follower()
    lock_follower(follower, target)

    with pytest.raises(
        ValueError, match=re.escape(f"{follower.path} is locked to {target.path}")
    ):
        follower.set(5)

    # the refused set changed nothing: neither the Target nor the own value
    assert target.get() == 11
    assert follower.own_value() == 22


def test_set_while_locked_names_dotted_full_paths_inside_a_manager():
    pm = ParameterManager(name="parameter_manager")
    pm.add_parameter("q01.x", initial_value=1, unit="V")
    pm.add_parameter("q02.y", initial_value=2, unit="V")

    target = pm.parameter("q01.x")
    follower = pm.parameter("q02.y")
    assert target.path == "parameter_manager.q01.x"
    assert follower.path == "parameter_manager.q02.y"

    follower._target = target
    follower.lock = PMLockBluePrint(target="parameter_manager.q01.x", locked=True)

    with pytest.raises(
        ValueError,
        match=re.escape("parameter_manager.q02.y is locked to parameter_manager.q01.x"),
    ):
        follower.set(5)


def test_unlocked_lock_exposes_own_value():
    target, follower = make_target_and_follower()
    lock_follower(follower, target, locked=False)

    # an unlocked Lock only remembers its Target
    target.set(33)
    assert follower.get() == 22

    follower.set(44)
    assert follower.get() == 44


def test_locking_leaves_the_own_cache_untouched():
    target, follower = make_target_and_follower()
    lock_follower(follower, target)

    assert follower.get() == 11
    # the locked get answers with the Target's value but must not write it
    # into the Follower's own cache
    assert follower.cache.get() == 22
    assert follower.own_value() == 22

    # unlocking exposes the own value again (ADR-0002)
    follower.lock.locked = False
    assert follower.get() == 22


def test_snapshot_without_lock_has_no_lock_entry():
    _, follower = make_target_and_follower()

    snap = follower.snapshot(update=False)
    assert snap["value"] == 22
    assert "lock" not in snap


def test_snapshot_while_locked_reports_target_value_and_lock():
    target, follower = make_target_and_follower()
    lock_follower(follower, target)

    snap = follower.snapshot(update=False)
    assert snap["value"] == 11
    assert snap["lock"] == {"target": target.path, "locked": True}

    # the own value survives in the cache
    assert follower.own_value() == 22


def test_snapshot_while_unlocked_reports_own_value_and_lock():
    target, follower = make_target_and_follower()
    lock_follower(follower, target, locked=False)

    snap = follower.snapshot(update=False)
    assert snap["value"] == 22
    assert snap["lock"] == {"target": target.path, "locked": False}


def test_locked_snapshot_gets_the_target_once_per_snapshot():
    target = CountingManagedParameter("target", set_cmd=None, initial_value=11)
    follower = ManagedParameter("follower", set_cmd=None, initial_value=22)
    lock_follower(follower, target)

    # update=True: the base snapshot asks this parameter, whose locked get
    # already answers with the Target's value — no second Target get
    snap = follower.snapshot(update=True)
    assert snap["value"] == 11
    assert snap["lock"] == {"target": target.path, "locked": True}
    assert target.get_calls == 1

    # update=False: the Target is read directly, per its own state (D7)
    snap = follower.snapshot(update=False)
    assert snap["value"] == 11
    assert target.get_calls == 2


def test_own_value_is_the_cached_own_value_regardless_of_state():
    target, follower = make_target_and_follower()
    assert follower.own_value() == 22

    lock_follower(follower, target)
    assert follower.get() == 11
    assert follower.own_value() == 22

    follower.lock.locked = False
    assert follower.own_value() == 22


def test_parameter_manager_creates_managed_parameters():
    pm = ParameterManager(name="pm_locks_unit")
    pm.add_parameter("q01.x", initial_value=5, unit="V")

    assert isinstance(pm.parameter("q01.x"), ManagedParameter)
    assert pm.get("q01.x") == 5

    pm.set("q01.x", 6)
    assert pm.get("q01.x") == 6


# ---------------------------------------------------------------------------
# Lock API on the Parameter Manager (plan task 1.2, D9)
# ---------------------------------------------------------------------------


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """A fresh Parameter Manager in an empty working directory, with a few
    parameters to lock."""
    monkeypatch.chdir(tmp_path)
    manager = ParameterManager(name="parameter_manager")
    manager.add_parameter("q01.x", initial_value=1, unit="V")
    manager.add_parameter("q01.y", initial_value=2, unit="V")
    manager.add_parameter("q02.x", initial_value=3, unit="V")
    manager.add_parameter("q02.y", initial_value=4, unit="V")
    manager.add_parameter("q01Data.IF", initial_value=10, unit="Hz")
    return manager


def test_lock_creates_a_locked_lock_and_get_pulls(pm):
    pm.lock("q01.x", "q01Data.IF")

    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )
    assert pm.parameter("q01.x").locked
    assert pm.get("q01.x") == 10

    # pull on get: changing the Target is enough, nothing is pushed
    pm.set("q01Data.IF", 20)
    assert pm.get("q01.x") == 20

    # set on the locked Follower raises, naming the full dotted paths
    with pytest.raises(
        ValueError,
        match=re.escape(
            "parameter_manager.q01.x is locked to parameter_manager.q01Data.IF"
        ),
    ):
        pm.set("q01.x", 99)


def test_names_go_in_relative_and_blueprint_targets_come_out_full(pm):
    pm.lock("q02.x", "q01Data.IF")

    lock = pm.get_lock("q02.x")
    assert lock is not None
    assert lock.target == "parameter_manager.q01Data.IF"
    assert list(pm.list_locks()) == ["q02.x"]
    assert pm.followers_of("q01Data.IF") == ["q02.x"]


def test_lock_with_unknown_follower_or_target_raises_naming_the_path(pm):
    with pytest.raises(ValueError, match="Parameter 'nope.x' does not exist"):
        pm.lock("nope.x", "q01Data.IF")

    with pytest.raises(ValueError, match="Parameter 'nope.IF' does not exist"):
        pm.lock("q01.x", "nope.IF")

    # the failed calls left no Lock behind
    assert pm.list_locks() == {}


def test_lock_with_two_unknown_paths_names_both(pm):
    with pytest.raises(ValueError) as excinfo:
        pm.lock("nope1", "nope2")

    # every offending path, not the first (rule 3)
    assert str(excinfo.value) == (
        "Parameter 'nope1' does not exist; Parameter 'nope2' does not exist"
    )
    assert pm.list_locks() == {}


@pytest.mark.parametrize(
    "call",
    [
        lambda pm: pm.unlock("nope.x"),
        lambda pm: pm.relock("nope.x"),
        lambda pm: pm.toggle_lock("nope.x"),
        lambda pm: pm.remove_lock("nope.x"),
        lambda pm: pm.get_lock("nope.x"),
        lambda pm: pm.followers_of("nope.x"),
    ],
    ids=[
        "unlock",
        "relock",
        "toggle_lock",
        "remove_lock",
        "get_lock",
        "followers_of",
    ],
)
def test_unknown_path_raises_naming_the_path_and_changes_nothing(pm, call):
    # a Lock exists, so list_locks proves the failed call changed nothing
    pm.lock("q01.x", "q01Data.IF")

    with pytest.raises(ValueError, match="Parameter 'nope.x' does not exist"):
        call(pm)

    assert pm.list_locks() == {
        "q01.x": PMLockBluePrint(target="parameter_manager.q01Data.IF", locked=True)
    }


def test_relock_with_a_missing_remembered_target_raises_naming_both(pm):
    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")
    # hand-wire a remembered Target that no longer exists
    pm.parameter("q01.x").lock = PMLockBluePrint(
        target="parameter_manager.gone", locked=False
    )

    with pytest.raises(
        ValueError,
        match=re.escape(
            "parameter_manager.q01.x remembers Target parameter_manager.gone, "
            "which does not exist"
        ),
    ):
        pm.relock("q01.x")

    # the refused relock left the Lock unlocked
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.gone", locked=False
    )


def test_self_lock_raises_naming_the_path(pm):
    with pytest.raises(
        ValueError, match="cannot lock parameter_manager.q01.x to itself"
    ):
        pm.lock("q01.x", "q01.x")

    assert pm.get_lock("q01.x") is None


def test_lock_refuses_a_two_node_cycle_and_names_every_path(pm):
    pm.lock("q01.x", "q01.y")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "cannot lock parameter_manager.q01.y to parameter_manager.q01.x: "
            "cycle in Lock targets: "
            "parameter_manager.q01.x -> parameter_manager.q01.y"
        ),
    ):
        pm.lock("q01.y", "q01.x")

    # the refused lock changed nothing
    assert pm.get_lock("q01.y") is None
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01.y", locked=True
    )


def test_lock_walks_targets_regardless_of_locked_state(pm):
    # q01.x carries an unlocked Lock that remembers q01Data.IF; the cycle
    # walk must still see it (D7)
    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")

    with pytest.raises(ValueError, match="cycle in Lock targets"):
        pm.lock("q01Data.IF", "q01.x")

    # the Target chain a -> b -> c closes on a: locking a to c is refused,
    # and the message walks the cycle from the proposed Target
    pm.lock("q01.y", "q01.x")
    pm.lock("q02.x", "q01.y")
    with pytest.raises(
        ValueError,
        match=re.escape(
            "cannot lock parameter_manager.q01.x to parameter_manager.q02.x: "
            "cycle in Lock targets: parameter_manager.q02.x -> "
            "parameter_manager.q01.y -> parameter_manager.q01.x"
        ),
    ):
        pm.lock("q01.x", "q02.x")


def test_lock_re_targets_an_existing_lock(pm):
    pm.lock("q01.y", "q01Data.IF")
    pm.lock("q01.y", "q02.x")

    assert pm.get_lock("q01.y") == PMLockBluePrint(
        target="parameter_manager.q02.x", locked=True
    )
    assert pm.followers_of("q01Data.IF") == []
    assert pm.followers_of("q02.x") == ["q01.y"]
    assert pm.get("q01.y") == 3


def test_a_failed_re_target_leaves_the_old_lock_untouched(pm):
    pm.lock("q02.x", "q01Data.IF")
    pm.lock("q01.y", "q02.x")  # q01.y follows q02.x

    # re-targeting q02.x to q01.y would close the cycle q02.x -> q01.y -> q02.x
    with pytest.raises(ValueError, match="cycle in Lock targets"):
        pm.lock("q02.x", "q01.y")

    assert pm.get_lock("q02.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )
    assert pm.get("q02.x") == 10


def test_unlock_keeps_the_target_and_exposes_the_own_value(pm):
    pm.lock("q01.x", "q01Data.IF")

    pm.unlock("q01.x")

    # unlocked Lock remembers its Target (D5)
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=False
    )
    assert pm.get("q01.x") == 1
    pm.set("q01.x", 7)
    assert pm.get("q01.x") == 7
    # an unlocked Follower still counts as a Follower
    assert pm.followers_of("q01Data.IF") == ["q01.x"]


def test_relock_locks_to_the_remembered_target(pm):
    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")

    pm.relock("q01.x")

    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )
    assert pm.get("q01.x") == 10
    # the own value is still there for the next unlock
    pm.unlock("q01.x")
    assert pm.get("q01.x") == 1


def test_relock_refuses_a_cycle_and_stays_unlocked(pm):
    # The Lock API itself cannot build this state: locking q01Data.IF to
    # q01.x is refused while q01.x still remembers it, even unlocked. It is
    # reachable by hand-wiring (or through the GUI's remembered target, as
    # the design mock's toggleLock), so relock re-validates: locking back
    # to a remembered Target that now follows the Follower is refused.
    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")
    q01_data_if = pm.parameter("q01Data.IF")
    q01_data_if._target = pm.parameter("q01.x")
    q01_data_if.lock = PMLockBluePrint(target="parameter_manager.q01.x", locked=True)

    with pytest.raises(
        ValueError,
        match=re.escape(
            "cannot lock parameter_manager.q01.x to parameter_manager.q01Data.IF: "
            "cycle in Lock targets: "
            "parameter_manager.q01Data.IF -> parameter_manager.q01.x"
        ),
    ):
        pm.relock("q01.x")

    # the refused relock left the Lock unlocked
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=False
    )


def test_toggle_lock_switches_both_ways(pm):
    pm.lock("q01.x", "q01Data.IF")

    pm.toggle_lock("q01.x")
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=False
    )
    assert pm.get("q01.x") == 1

    pm.toggle_lock("q01.x")
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )
    assert pm.get("q01.x") == 10


def test_calls_without_a_lock_raise_naming_the_path(pm):
    for call in (pm.unlock, pm.relock, pm.toggle_lock, pm.remove_lock):
        with pytest.raises(ValueError, match="parameter_manager.q01.x has no Lock"):
            call("q01.x")


def test_unlock_on_an_already_unlocked_lock_is_a_logged_no_op(pm, caplog):
    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")
    target_obj = pm.parameter("q01Data.IF")
    follower = pm.parameter("q01.x")

    with caplog.at_level(logging.INFO):
        pm.unlock("q01.x")

    # state unchanged: the Lock is still present and unlocked, still
    # remembering its Target, and the own value still answers get()
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=False
    )
    assert follower._target is target_obj
    assert pm.get("q01.x") == 1
    records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(records) == 1
    assert (
        "parameter_manager.q01.x is already unlocked; nothing to do"
        in records[0].getMessage()
    )


def test_relock_on_an_already_locked_lock_is_a_logged_no_op(pm, caplog):
    pm.lock("q01.x", "q01Data.IF")
    follower = pm.parameter("q01.x")
    # sentinel: relock's mutation path would re-resolve the remembered
    # Target into _target and replace this reference; the no-op must not
    sentinel = pm.parameter("q02.y")
    follower._target = sentinel
    value_before = pm.get("q01.x")

    with caplog.at_level(logging.INFO):
        pm.relock("q01.x")

    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )
    assert follower._target is sentinel
    assert pm.get("q01.x") == value_before
    records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(records) == 1
    assert (
        "parameter_manager.q01.x is already locked; nothing to do"
        in records[0].getMessage()
    )


def test_remove_lock_forgets_the_target_entirely(pm):
    pm.lock("q01.x", "q01Data.IF")

    pm.remove_lock("q01.x")

    assert pm.get_lock("q01.x") is None
    assert pm.list_locks() == {}
    assert pm.followers_of("q01Data.IF") == []
    assert pm.get("q01.x") == 1
    pm.set("q01.x", 42)
    assert pm.get("q01.x") == 42


def test_get_lock_and_list_locks_without_locks(pm):
    assert pm.get_lock("q01.x") is None
    assert pm.list_locks() == {}


def test_followers_of_lists_locked_and_unlocked_followers(pm):
    pm.lock("q01.x", "q01Data.IF")
    pm.lock("q02.x", "q01Data.IF")
    pm.unlock("q02.x")

    assert pm.followers_of("q01Data.IF") == ["q01.x", "q02.x"]
    # a parameter nobody follows
    assert pm.followers_of("q02.y") == []


def test_chain_reads_hop_by_hop_per_own_state(pm):
    pm.lock("q01.y", "q01Data.IF")  # middle hop
    pm.lock("q02.x", "q01.y")  # end of the chain

    # both locked: q02.x pulls through q01.y to q01Data.IF
    assert pm.get("q02.x") == 10

    # q01.y unlocked: q02.x reads q01.y's own value (D7)
    pm.unlock("q01.y")
    pm.set("q01.y", 5)
    assert pm.get("q02.x") == 5
    assert pm.followers_of("q01.y") == ["q02.x"]

    # q01.y locked again: the chain pulls through once more
    pm.relock("q01.y")
    assert pm.get("q02.x") == 10


def test_remove_parameter_removes_every_lock_pointing_at_it(pm):
    pm.lock("q01.x", "q01Data.IF")
    pm.lock("q02.x", "q01Data.IF")
    pm.unlock("q02.x")

    pm.remove_parameter("q01Data.IF")

    # both Followers are plain parameters again (D3), whatever the state was
    assert pm.get_lock("q01.x") is None
    assert pm.get_lock("q02.x") is None
    assert pm.list_locks() == {}
    assert pm.get("q01.x") == 1
    assert pm.get("q02.x") == 3
    pm.set("q01.x", 11)
    assert pm.get("q01.x") == 11


def test_remove_parameter_leaves_unrelated_locks_alone(pm):
    pm.lock("q01.x", "q01Data.IF")
    pm.lock("q02.x", "q02.y")

    pm.remove_parameter("q02.y")  # Target of q02.x only

    assert pm.get_lock("q02.x") is None
    # q01.x still follows q01Data.IF
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )
    assert pm.get("q01.x") == 10


def test_remove_parameter_of_a_chain_middle(pm):
    pm.lock("q01.y", "q01Data.IF")  # Follower of q01Data.IF ...
    pm.lock("q02.x", "q01.y")  # ... and Target of q02.x

    pm.remove_parameter("q01.y")

    # q02.x followed q01.y, which is gone: plain parameter again
    assert pm.get_lock("q02.x") is None
    assert pm.get("q02.x") == 3
    # q01Data.IF is untouched and now has no Followers
    assert pm.get("q01Data.IF") == 10
    assert pm.followers_of("q01Data.IF") == []


def test_remove_all_parameters_clears_every_lock(pm):
    pm.lock("q01.x", "q01Data.IF")
    pm.lock("q02.x", "q01.y")

    pm.remove_all_parameters()

    assert pm.list() == []
    assert pm.list_locks() == {}


def test_lock_with_a_plain_group_parameter(pm):
    # a plain qcodes Parameter (no lock, no path) can only end up inside a
    # Parameter Manager through direct, unrouted creation — legacy or
    # foreign code. The Lock API must still handle it.
    pm.q01._add_own_parameter("plain", set_cmd=None, initial_value=7)

    # it cannot carry a Lock
    with pytest.raises(
        ValueError, match="parameter_manager.q01.plain cannot carry a Lock"
    ):
        pm.lock("q01.plain", "q01.x")
    assert pm.get_lock("q01.plain") is None

    # but the Target knows nothing (D3): following it works
    pm.lock("q01.x", "q01.plain")
    assert pm.get("q01.x") == 7
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01.plain", locked=True
    )
    assert pm.followers_of("q01.plain") == ["q01.x"]
    # a plain Parameter never shows up as a Follower
    assert "q01.plain" not in pm.list_locks()


def test_group_remove_parameter_delegates_to_the_root(pm):
    pm.lock("q01.x", "q02.y")

    pm.q02.remove_parameter("y")

    # the Lock pointing at the removed Target went with it (D3), through
    # the root's cleanup
    assert pm.list_locks() == {}
    assert pm.get_lock("q01.x") is None
    assert pm.get("q01.x") == 1
    pm.set("q01.x", 5)
    assert pm.get("q01.x") == 5


def test_group_add_parameter_creates_a_managed_parameter(pm):
    pm.q01.add_parameter("z", initial_value=1)

    param = pm.parameter("q01.z")
    assert isinstance(param, ManagedParameter)
    assert param.path == "parameter_manager.q01.z"
    # it can carry a Lock
    pm.lock("q01.z", "q01Data.IF")
    assert pm.get("q01.z") == 10


def test_nested_group_add_parameter_creates_a_managed_parameter(pm):
    pm.add_parameter("q01.ro.IF", initial_value=2)  # creates the depth-2 group

    pm.q01.ro.add_parameter("gain", initial_value=3)

    param = pm.parameter("q01.ro.gain")
    assert isinstance(param, ManagedParameter)
    assert param.path == "parameter_manager.q01.ro.gain"
    pm.lock("q01.ro.gain", "q01.ro.IF")
    assert pm.get("q01.ro.gain") == 2


def test_standalone_group_keeps_plain_parameters():
    solo = ParameterGroup("solo_group")
    solo.add_parameter("p", initial_value=1)

    assert solo._root is None
    assert not isinstance(solo.parameter("p"), ManagedParameter)


def test_target_paths_must_be_relative_to_the_manager(pm):
    # rule 4: paths are relative to the Parameter Manager. A full-form
    # path and a foreign root both name a parameter this manager cannot
    # resolve (D8: Targets only inside the same Parameter Manager).
    with pytest.raises(
        ValueError,
        match=re.escape("Parameter 'parameter_manager.q01.y' does not exist"),
    ):
        pm.lock("q01.x", "parameter_manager.q01.y")

    with pytest.raises(
        ValueError, match=re.escape("Parameter 'other.z' does not exist")
    ):
        pm.lock("q01.x", "other.z")

    assert pm.list_locks() == {}


# ---------------------------------------------------------------------------
# pm-lock-update Broadcasts (plan task 1.3, D10)
#
# One Broadcast per affected Follower, name = full Follower path, value =
# its PMLockBluePrint, or None when its Lock was removed. Emitted by every
# Lock method that changes a Lock and by remove_parameter when deleting a
# Target drops Locks; the logged no-op paths and failed validations emit
# nothing (decided during 1.3).
# ---------------------------------------------------------------------------


@pytest.fixture
def pm_with_sink(pm):
    """The Lock API fixture with a Broadcast sink attached, recording
    every Broadcast the Parameter Manager emits."""
    received = []
    pm.add_broadcast_sink(received.append)
    return pm, received


def test_lock_emits_one_pm_lock_update_naming_the_follower(pm_with_sink):
    pm, received = pm_with_sink

    pm.lock("q01.x", "q01Data.IF")

    assert len(received) == 1
    bp = received[0]
    assert isinstance(bp, ParameterBroadcastBluePrint)
    assert bp.name == "parameter_manager.q01.x"
    assert bp.action == PM_LOCK_UPDATE
    assert bp.value == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )


def test_re_targeting_a_lock_emits_one_pm_lock_update_with_the_new_target(
    pm_with_sink,
):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    received.clear()

    pm.lock("q01.x", "q01.y")  # re-targets the existing Lock (D9)

    assert len(received) == 1
    bp = received[0]
    assert bp.name == "parameter_manager.q01.x"
    assert bp.action == PM_LOCK_UPDATE
    assert bp.value == PMLockBluePrint(target="parameter_manager.q01.y", locked=True)
    assert pm.get("q01.x") == 2  # the Follower now pulls from q01.y


def test_unlock_emits_pm_lock_update_with_the_unlocked_lock(pm_with_sink):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    received.clear()

    pm.unlock("q01.x")

    assert len(received) == 1
    bp = received[0]
    assert bp.name == "parameter_manager.q01.x"
    assert bp.action == PM_LOCK_UPDATE
    assert bp.value == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=False
    )


def test_relock_emits_pm_lock_update_with_the_locked_lock(pm_with_sink):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")
    received.clear()

    pm.relock("q01.x")

    assert len(received) == 1
    bp = received[0]
    assert bp.name == "parameter_manager.q01.x"
    assert bp.action == PM_LOCK_UPDATE
    assert bp.value == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )


def test_toggle_lock_emits_one_broadcast_per_state_change(pm_with_sink):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    received.clear()

    pm.toggle_lock("q01.x")
    assert len(received) == 1
    assert received[0].name == "parameter_manager.q01.x"
    assert received[0].value == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=False
    )

    pm.toggle_lock("q01.x")
    assert len(received) == 2
    assert received[1].value == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )


def test_broadcast_payloads_are_independent_of_the_stored_lock(pm_with_sink):
    # unlock and relock broadcast a snapshot, not the parameter's own Lock
    # record: a sink that keeps payloads must still see each Broadcast's
    # state at emit time after the Lock is toggled again
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    received.clear()

    pm.toggle_lock("q01.x")  # unlock
    pm.toggle_lock("q01.x")  # lock again

    assert len(received) == 2
    assert received[0].value.locked is False
    assert received[1].value.locked is True
    assert received[0].value.locked != received[1].value.locked
    assert received[0].value is not received[1].value
    # the stored record is untouched by the broadcasting
    assert pm.get_lock("q01.x") == PMLockBluePrint(
        target="parameter_manager.q01Data.IF", locked=True
    )


def test_remove_lock_emits_pm_lock_update_with_none(pm_with_sink):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    received.clear()

    pm.remove_lock("q01.x")

    assert len(received) == 1
    bp = received[0]
    assert bp.name == "parameter_manager.q01.x"
    assert bp.action == PM_LOCK_UPDATE
    assert bp.value is None


def test_noop_unlock_and_relock_emit_nothing(pm_with_sink, caplog):
    # decided during 1.3: the logged no-op paths affect no Follower,
    # so they emit no Broadcast
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")  # locked
    pm.lock("q02.x", "q01Data.IF")  # locked
    pm.unlock("q02.x")  # unlocked
    received.clear()

    with caplog.at_level(logging.INFO):
        pm.relock("q01.x")  # already locked: no-op
        pm.unlock("q02.x")  # already unlocked: no-op

    assert received == []
    assert "already locked" in caplog.text
    assert "already unlocked" in caplog.text


def test_failed_lock_validations_emit_nothing(pm_with_sink):
    pm, received = pm_with_sink

    # validate-then-mutate: a refused call must not broadcast either
    with pytest.raises(ValueError):
        pm.lock("nope", "q01Data.IF")
    with pytest.raises(ValueError):
        pm.lock("q01.x", "q01.x")  # self-lock
    with pytest.raises(ValueError):
        pm.relock("q02.y")  # no Lock
    with pytest.raises(ValueError):
        pm.toggle_lock("q02.y")  # no Lock
    assert received == []

    pm.lock("q01.x", "q01Data.IF")
    pm.unlock("q01.x")
    received.clear()
    with pytest.raises(ValueError):
        pm.lock("q01Data.IF", "q01.x")  # would close a cycle
    with pytest.raises(ValueError):
        pm.unlock("q02.y")  # no Lock
    with pytest.raises(ValueError):
        pm.relock("q02.y")  # no Lock
    with pytest.raises(ValueError):
        pm.toggle_lock("q02.y")  # no Lock
    with pytest.raises(ValueError):
        pm.remove_lock("q02.y")  # no Lock
    # a relock that would close a cycle is refused as well (D7)
    pm.parameter("q01Data.IF")._target = pm.parameter("q01.x")
    pm.parameter("q01Data.IF").lock = PMLockBluePrint(
        target="parameter_manager.q01.x", locked=True
    )
    with pytest.raises(ValueError, match="cycle in Lock targets"):
        pm.relock("q01.x")

    assert received == []


def test_remove_parameter_emits_one_none_per_dropped_lock(pm_with_sink):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")
    pm.lock("q02.x", "q01Data.IF")
    pm.unlock("q02.x")  # an unlocked Lock is dropped all the same
    received.clear()

    pm.remove_parameter("q01Data.IF")

    assert len(received) == 2
    names = {bp.name for bp in received}
    assert names == {"parameter_manager.q01.x", "parameter_manager.q02.x"}
    for bp in received:
        assert bp.action == PM_LOCK_UPDATE
        assert bp.value is None


def test_remove_parameter_without_dropped_locks_emits_nothing(pm_with_sink):
    pm, received = pm_with_sink
    pm.lock("q01.x", "q01Data.IF")  # q01.x is a Follower, not a Target
    received.clear()

    # removing a Follower drops no Locks: its own Lock disappears with it,
    # and the parameter-deletion Broadcast is the Server's business
    pm.remove_parameter("q01.x")
    assert received == []

    pm.remove_parameter("q02.y")  # unrelated parameter
    assert received == []


# ---------------------------------------------------------------------------
# Lock API through a client proxy against a live Server (plan task 1.3)
#
# The Server registers itself as a Broadcast sink on the Parameter Manager
# (task 0.3), so every Lock method call over the wire also emits its
# pm-lock-update on the PUB socket. The server-side Parameter Manager is
# shared by all tests of this module, so every test removes the parameters
# it created again.
# ---------------------------------------------------------------------------

PROXY_FOLLOWER = "q02.x"
PROXY_TARGET = "q01Data.IF"


def _add_proxy_params(params):
    """Create the two parameters the proxy Lock tests use, replacing any
    leftovers from an earlier test of this module."""
    _remove_proxy_params(params)
    params.add_parameter(PROXY_FOLLOWER, initial_value=3, unit="V")
    params.add_parameter(PROXY_TARGET, initial_value=10, unit="Hz")


def _remove_proxy_params(params):
    for name in (PROXY_FOLLOWER, PROXY_TARGET):
        if params.has_param(name):
            params.remove_parameter(name)


def test_every_lock_method_is_callable_through_the_proxy(param_manager):
    cli, params = param_manager
    _add_proxy_params(params)
    try:
        params.lock(PROXY_FOLLOWER, PROXY_TARGET)
        assert params.get_lock(PROXY_FOLLOWER) == PMLockBluePrint(
            target="parameter_manager.q01Data.IF", locked=True
        )

        params.unlock(PROXY_FOLLOWER)
        assert params.get_lock(PROXY_FOLLOWER).locked is False

        params.relock(PROXY_FOLLOWER)
        assert params.get_lock(PROXY_FOLLOWER).locked is True

        params.toggle_lock(PROXY_FOLLOWER)
        assert params.get_lock(PROXY_FOLLOWER).locked is False
        params.toggle_lock(PROXY_FOLLOWER)
        assert params.get_lock(PROXY_FOLLOWER).locked is True

        assert params.followers_of(PROXY_TARGET) == [PROXY_FOLLOWER]
        assert list(params.list_locks()) == [PROXY_FOLLOWER]

        params.remove_lock(PROXY_FOLLOWER)
        assert params.get_lock(PROXY_FOLLOWER) is None
        assert params.list_locks() == {}
        assert params.followers_of(PROXY_TARGET) == []
    finally:
        _remove_proxy_params(params)


def test_get_lock_and_list_locks_deserialise_to_pm_lock_blueprint(param_manager):
    cli, params = param_manager
    _add_proxy_params(params)
    try:
        params.lock(PROXY_FOLLOWER, PROXY_TARGET)

        lock_bp = params.get_lock(PROXY_FOLLOWER)
        assert isinstance(lock_bp, PMLockBluePrint)
        assert lock_bp == PMLockBluePrint(
            target="parameter_manager.q01Data.IF", locked=True
        )

        locks = params.list_locks()
        assert isinstance(locks, dict)
        assert isinstance(locks[PROXY_FOLLOWER], PMLockBluePrint)
        assert locks == {
            PROXY_FOLLOWER: PMLockBluePrint(
                target="parameter_manager.q01Data.IF", locked=True
            )
        }
    finally:
        _remove_proxy_params(params)


def test_locked_follower_answers_get_with_the_target_value_over_the_wire(
    param_manager,
):
    cli, params = param_manager
    _add_proxy_params(params)
    try:
        params.lock(PROXY_FOLLOWER, PROXY_TARGET)

        # the named check: pm.q02.x() returns the Target's value
        assert params.q02.x() == 10

        # pull on get: changing the Target is enough, nothing is pushed
        params.q01Data.IF.set(20)
        assert params.q02.x() == 20

        # unlocking exposes the Follower's own value again
        params.unlock(PROXY_FOLLOWER)
        assert params.q02.x() == 3
    finally:
        _remove_proxy_params(params)


def test_subclient_receives_pm_lock_update_and_none_after_remove_lock(
    param_manager, server_port, capture_broadcasts, wait_for_broadcasts
):
    cli, params = param_manager
    _add_proxy_params(params)
    try:
        with capture_broadcasts(["parameter_manager"], server_port + 1) as received:
            params.lock(PROXY_FOLLOWER, PROXY_TARGET)
            wait_for_broadcasts(received)

            assert len(received) == 1
            bp = received[0]
            assert isinstance(bp, ParameterBroadcastBluePrint)
            assert bp.name == "parameter_manager.q02.x"
            assert bp.action == PM_LOCK_UPDATE
            assert isinstance(bp.value, PMLockBluePrint)
            assert bp.value == PMLockBluePrint(
                target="parameter_manager.q01Data.IF", locked=True
            )

            params.remove_lock(PROXY_FOLLOWER)
            wait_for_broadcasts(received, n=2)

            assert len(received) == 2
            removed = received[1]
            assert removed.name == "parameter_manager.q02.x"
            assert removed.action == PM_LOCK_UPDATE
            assert removed.value is None
    finally:
        _remove_proxy_params(params)
