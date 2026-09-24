"""Unit tests for ``ManagedParameter`` (plan task 1.1).

Two standalone ManagedParameters (a Target and a Follower) with no
Parameter Manager involved. The Lock is wired directly on the parameter
objects: the Lock API on the Parameter Manager is task 1.2, its Broadcasts
task 1.3.
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
