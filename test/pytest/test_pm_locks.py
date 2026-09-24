"""Unit tests for ``ManagedParameter`` and the Lock API (plan tasks 1.1
and 1.2).

The first part wires two standalone ManagedParameters (a Target and a
Follower) by hand, with no Parameter Manager involved. The second part
exercises the Lock API on a local Parameter Manager (``lock``, ``unlock``,
``relock``, ``toggle_lock``, ``remove_lock``, ``get_lock``, ``list_locks``,
``followers_of``, and the ``remove_parameter`` Lock cleanup). Its
Broadcasts are task 1.3.
"""

import re

import pytest

from instrumentserver.blueprints import PMLockBluePrint
from instrumentserver.params import ManagedParameter, ParameterManager


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
    q01_data_if.lock = PMLockBluePrint(
        target="parameter_manager.q01.x", locked=True
    )

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


def test_state_inconsistent_calls_raise_naming_the_path(pm):
    # no Lock at all
    for call in (pm.unlock, pm.relock, pm.toggle_lock, pm.remove_lock):
        with pytest.raises(
            ValueError, match="parameter_manager.q01.x has no Lock"
        ):
            call("q01.x")

    # Lock present but in the other state already
    pm.lock("q01.x", "q01Data.IF")
    with pytest.raises(
        ValueError, match="parameter_manager.q01.x is already locked"
    ):
        pm.relock("q01.x")
    pm.unlock("q01.x")
    with pytest.raises(
        ValueError, match="parameter_manager.q01.x is not locked"
    ):
        pm.unlock("q01.x")


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
    # a parameter added directly on a Parameter Group (as the wire call
    # pm.q01.add_parameter does) is a plain qcodes Parameter
    pm.q01.add_parameter("plain", initial_value=7)

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
