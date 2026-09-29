"""Verification script for docs/user_guide/parameter_manager.md.

One section below per page section, in page order (see
test/docs_verification/README.md for conventions). Asserts every behavioral
claim the page makes; exits 0 on success.

A Parameter Manager writes its profile files into the working directory of
the process it lives in, so every section runs inside a throwaway working
directory created (and removed again) under this script's folder; no profile
file is ever left in the repository.

GUI claims (the tab layout, tints and gutter bands, the Lock column and lock
button, the context menu, the arm strip flow, the Locks panel, the Types tab
panes, and the delete-Target confirmation dialog) cannot be asserted from a
script. They are verified manually (the plan's task 5.6 records the
end-to-end GUI check) and captured in the page's screenshots; the same goes
for the Server window showing the generic instrument widget unless the
station config's ``gui`` entry names the Parameter Manager widget. What the
GUI section states about keyboard shortcuts is asserted here against the
GUI's shortcut registry.
"""

import json
import logging
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import capture_broadcasts, client, server

from instrumentserver.blueprints import PMLockBluePrint

PM_CLASS = "instrumentserver.params.ParameterManager"
PM_NAME = "parameter_manager"


@contextmanager
def workspace():
    """Run one section in a throwaway working directory.

    The in-process Server (and with it every Parameter Manager it hosts)
    writes its profile files into the working directory. The directory is
    created under this script's folder and removed again on exit.
    """
    old = os.getcwd()
    path = Path(tempfile.mkdtemp(prefix="verify_pm_", dir=Path(__file__).parent))
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(old)
        shutil.rmtree(path, ignore_errors=True)


def capture_one_broadcast(action):
    """Run ``action`` under a Broadcast capture and return every message
    the capture saw while ``action`` ran, plus a short settle wait.

    ``wait_for(1)`` returns as soon as the first message lands, so the
    settle wait runs before the list is taken: a caller counting the
    messages sees the ones belonging to this action only.
    """
    with capture_broadcasts([PM_NAME]) as cap:
        action()
        cap.wait_for(1)
        time.sleep(0.2)
        return list(cap.messages)


# ---------------------------------------------------------------------------
# Section: Concept
#
# Page claims: the Parameter Manager is the flagship Virtual Instrument, the
# single source of truth for experiment parameters; every Client sees the
# same values without refreshing; a change reaches every GUI live through a
# Broadcast.
# ---------------------------------------------------------------------------
def section_concept() -> None:
    with workspace(), server():
        with client() as cli_a, client() as cli_b:
            pm_a = cli_a.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm_a.add_parameter("q01.IF", initial_value=10e6, unit="Hz")
            assert pm_a.q01.IF() == 10000000.0

            # a second Client reads the same value: one source of truth
            pm_b = cli_b.get_instrument(PM_NAME)
            assert pm_b.q01.IF() == 10000000.0

            # the change goes out as a Broadcast (which is what makes GUIs
            # follow along live, without polling)
            with capture_broadcasts([PM_NAME]) as cap:
                pm_a.q01.IF.set(11e6)
                messages = cap.wait_for(1)
            text = repr(messages)
            assert "parameter-update" in text, text
            assert "parameter_manager.q01.IF" in text, text

            # and the second Client sees the new value on its next read
            assert pm_b.q01.IF() == 11000000.0
    print("section_concept: OK")


# ---------------------------------------------------------------------------
# Section: Hierarchical parameters
#
# Page claims: dotted paths address parameters in nested Parameter Groups,
# which are created on demand; add_parameter / remove_parameter / list /
# has_param manage the tree; get and set work through Proxy attribute
# access; the default remove_parameter prunes the Parameter Group it
# empties; cleanup=False keeps it, and remove_empty_submodules prunes it.
# ---------------------------------------------------------------------------
def section_hierarchical_parameters() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)

            # dotted names create the Parameter Groups on the way
            pm.add_parameter("q01.readout.IF", initial_value=20e6, unit="Hz")
            pm.add_parameter("q01.power", initial_value=-10, unit="dBm")
            assert pm.list() == ["q01.readout.IF", "q01.power"]
            assert pm.has_param("q01.readout.IF")
            assert not pm.has_param("q01.readout.bw")

            # the Proxy reflects the hierarchy: attribute access reaches the
            # nested parameters
            assert pm.q01.readout.IF() == 20000000.0
            pm.q01.power.set(-5)
            assert pm.q01.power() == -5
            pm.q01.readout.IF.set(21e6)
            assert pm.q01.readout.IF() == 21000000.0
            assert pm.q01.readout.IF.unit == "Hz"

            # the default removes the parameter and prunes the Parameter
            # Group it empties
            pm.remove_parameter("q01.readout.IF")
            assert pm.list() == ["q01.power"]
            try:
                pm.q01.readout
                pruned = False
            except AttributeError:
                pruned = True
            assert pruned

            # cleanup=False keeps the emptied Parameter Group instead ...
            pm.add_parameter("q01.readout.IF", initial_value=1, unit="Hz")
            pm.remove_parameter("q01.readout.IF", cleanup=False)
            pm.update()
            assert not pm.has_param("q01.readout.IF")
            assert pm.q01.readout is not None

            # ... and remove_empty_submodules prunes every empty group
            pm.remove_empty_submodules()
            pm.update()
            try:
                pm.q01.readout
                pruned = False
            except AttributeError:
                pruned = True
            assert pruned
            assert pm.list() == ["q01.power"]
    print("section_hierarchical_parameters: OK")


# ---------------------------------------------------------------------------
# Section: Types
#
# Page claims: a Type is a named shape (relative paths with defaults and
# units, plus Nested Types); Instances are duck-typed, recomputed on demand,
# never stored; add_instance writes the shape into a new Parameter Group and
# keeps parameters that exist at a target path already; a wrong-unit
# submodule is no Instance; add_type_parameter writes the entry into every
# Instance lacking it; a Type edit emits one pm-type-update Broadcast;
# set_type_parameter_default only affects Instances created later;
# set_type_parameter_unit propagates to every Instance; Nested Types expand
# under their submodule; instances_of / types_of answer on demand; removing
# an entry, a Nested Type or a Type leaves the parameters alone; a Type
# still nested in another refuses to be removed, naming the nester.
# ---------------------------------------------------------------------------
def section_types() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)

            # a fresh Type has no Instances: nothing carries its shape yet
            pm.add_type("qubit")
            pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
            pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
            assert pm.instances_of("qubit") == []

            # add_instance writes the shape into a new Parameter Group
            pm.add_instance("qubit", "q01")
            pm.add_instance("qubit", "q02")
            assert pm.instances_of("qubit") == ["q01", "q02"]
            pm.update()
            assert pm.q01.IF() == 10000000.0
            assert pm.q01.octave_gain() == 10
            assert pm.q01.IF.unit == "Hz"

            # duck-typed: a submodule that carries the shape is an Instance,
            # no matter how it got its parameters
            pm.add_parameter("q03.IF", initial_value=99e6, unit="Hz")
            pm.add_parameter("q03.octave_gain", initial_value=1, unit="dB")
            assert pm.instances_of("qubit") == ["q01", "q02", "q03"]
            assert pm.types_of("q03.IF") == ["qubit"]

            # the unit is part of the shape: a submodule with the wrong unit
            # is no Instance
            pm.add_parameter("q05.IF", initial_value=1, unit="V")
            pm.add_parameter("q05.octave_gain", initial_value=1, unit="dB")
            assert "q05" not in pm.instances_of("qubit")

            # a new entry is written into every Instance lacking it
            pm.add_type_parameter("qubit", "window", default=0.5, unit="s")
            pm.update()
            assert pm.q01.window() == 0.5
            assert pm.q03.window() == 0.5

            # a Type edit announces itself: one pm-type-update Broadcast
            messages = capture_one_broadcast(
                lambda: pm.set_type_parameter_default("qubit", "window", 1.0)
            )
            text = repr(messages)
            assert text.count("pm-type-update") == 1, text
            assert "parameter_manager.qubit" in text, text

            # a new default only affects Instances created later
            assert pm.q01.window() == 0.5
            pm.add_instance("qubit", "q04")
            pm.update()
            assert pm.q04.window() == 1.0

            # a new unit propagates to that parameter in every Instance
            pm.set_type_parameter_unit("qubit", "IF", "V")
            with client() as cli_fresh:
                fresh = cli_fresh.get_instrument(PM_NAME)
                assert fresh.q01.IF.unit == "V"
                assert fresh.q03.IF.unit == "V"

            # a Nested Type expands under its submodule, in the effective set
            pm.add_type("readout")
            pm.add_type_parameter("readout", "bw", default=20e6, unit="Hz")
            pm.add_nested_type("qubit", "readout", "readout")
            pm.update()
            assert pm.q01.readout.bw() == 20000000.0
            blueprint = pm.get_type("qubit")
            assert blueprint.nested == {"readout": "readout"}
            assert blueprint.effective["readout.bw"] == {
                "unit": "Hz",
                "from_type": "readout",
            }
            # the Nested Type claims its entries; the innermost Type wins
            assert pm.types_of("q01.readout.bw") == ["readout", "qubit"]
            assert pm.instances_of("readout") == [
                "q01.readout",
                "q02.readout",
                "q03.readout",
                "q04.readout",
            ]

            # a Type still required as a Nested Type refuses to be removed,
            # naming the Types that nest it
            try:
                pm.remove_type("readout")
                nested_error = None
            except Exception as exc:  # noqa: BLE001
                nested_error = str(exc)
            assert nested_error is not None
            assert "qubit" in nested_error, nested_error

            # removing an entry from the Type leaves the parameters alone,
            # and the Instances keep matching: the required shape only shrank
            pm.remove_type_parameter("qubit", "window")
            assert pm.has_param("q01.window")
            assert pm.has_param("q04.window")
            assert pm.instances_of("qubit") == ["q01", "q02", "q03", "q04"]

            # duck-typing cuts both ways: deleting a required parameter makes
            # the submodule stop matching, and nothing else changes
            pm.remove_parameter("q02.IF")
            assert pm.has_param("q02.octave_gain")
            assert pm.instances_of("qubit") == ["q01", "q03", "q04"]

            # same for a Nested Type and for the Type itself: the parameters
            # stay whatever happens to the Type
            pm.remove_nested_type("qubit", "readout")
            assert pm.has_param("q01.readout.bw")
            assert "q01.readout" in pm.instances_of("readout")
            pm.remove_type("qubit")
            assert pm.list_types() == ["readout"]
            assert pm.has_param("q01.IF")
            assert pm.q01.IF() == 10000000.0

            # add_instance keeps parameters that exist at a target path
            # already, with their own value and unit
            pm.add_type("qubit")
            pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
            pm.add_parameter("q09.IF", initial_value=99, unit="Hz")
            pm.add_instance("qubit", "q09")
            pm.update()
            assert pm.q09.IF() == 99
            assert pm.q09.IF.unit == "Hz"
            assert pm.instances_of("qubit") == ["q09"]
    print("section_types: OK")


# ---------------------------------------------------------------------------
# Section: Locks
#
# Page claims: a Lock has three states (no Lock; Lock present but unlocked,
# remembering its Target; Lock present and locked); a locked Follower
# answers get with the Target's value and refuses set with an error naming
# the Target; values are pulled on get, so setting the Target is enough and
# unlocking exposes the Follower's own value again; Locks chain and each hop
# reads by its own state; cycles and self-locks are refused with an error
# listing the chain; the Target lives in the same Parameter Manager (D8);
# get_lock / list_locks / followers_of report the state; deleting a Target
# removes the Locks that pointed at it; every Lock method the page names
# emits one pm-lock-update Broadcast per affected Follower.
# ---------------------------------------------------------------------------
def section_locks() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm.add_parameter("q01Data.IF", initial_value=10e6, unit="Hz")
            pm.add_parameter("q01.IF", initial_value=5e6, unit="Hz")
            pm.add_parameter("q02.IF", initial_value=0, unit="Hz")

            with capture_broadcasts([PM_NAME]) as cap:
                pm.lock("q01.IF", "q01Data.IF")
                messages = cap.wait_for(1)
            text = repr(messages)
            assert "pm-lock-update" in text, text
            assert "parameter_manager.q01.IF" in text, text

            # locked: the Follower answers get with the Target's value
            lock = pm.get_lock("q01.IF")
            assert lock.target == "parameter_manager.q01Data.IF"
            assert lock.locked
            assert pm.q01.IF() == 10000000.0

            # pull on get: setting the Target is enough, nothing is pushed
            pm.q01Data.IF.set(11e6)
            assert pm.q01.IF() == 11000000.0

            # set on a locked Follower raises, naming Follower and Target
            try:
                pm.q01.IF.set(12e6)
                set_error = None
            except Exception as exc:  # noqa: BLE001
                set_error = str(exc)
            assert set_error is not None
            assert (
                "parameter_manager.q01.IF is locked to "
                "parameter_manager.q01Data.IF" in set_error
            ), set_error

            # unlocking exposes the Follower's own value again
            pm.unlock("q01.IF")
            assert pm.get_lock("q01.IF").locked is False
            assert pm.q01.IF() == 5000000.0
            pm.relock("q01.IF")
            assert pm.q01.IF() == 11000000.0

            # every Lock method the page names announces the Follower: one
            # pm-lock-update per state change
            messages = capture_one_broadcast(lambda: pm.toggle_lock("q01.IF"))
            text = repr(messages)
            assert text.count("pm-lock-update") == 1, text
            assert "parameter_manager.q01.IF" in text, text
            assert pm.get_lock("q01.IF").locked is False
            messages = capture_one_broadcast(lambda: pm.toggle_lock("q01.IF"))
            assert pm.get_lock("q01.IF").locked is True

            # bookkeeping: followers_of and list_locks
            assert pm.followers_of("q01Data.IF") == ["q01.IF"]
            assert list(pm.list_locks()) == ["q01.IF"]

            # chains: each hop reads according to its own state
            pm.lock("q02.IF", "q01.IF")
            assert pm.q02.IF() == 11000000.0
            pm.q01Data.IF.set(12e6)
            assert pm.q02.IF() == 12000000.0
            pm.unlock("q01.IF")
            assert pm.q01.IF() == 5000000.0
            assert pm.q02.IF() == 5000000.0
            pm.relock("q01.IF")
            assert pm.q02.IF() == 12000000.0
            assert sorted(pm.list_locks()) == ["q01.IF", "q02.IF"]

            # cycles are refused, with the whole chain in the error
            try:
                pm.lock("q01Data.IF", "q02.IF")
                cycle_error = None
            except Exception as exc:  # noqa: BLE001
                cycle_error = str(exc)
            assert cycle_error is not None
            assert "cycle in Lock targets" in cycle_error, cycle_error
            for path in (
                "parameter_manager.q02.IF",
                "parameter_manager.q01.IF",
                "parameter_manager.q01Data.IF",
            ):
                assert path in cycle_error, cycle_error

            # a self-lock is refused too
            try:
                pm.lock("q01.IF", "q01.IF")
                self_error = None
            except Exception as exc:  # noqa: BLE001
                self_error = str(exc)
            assert self_error is not None
            assert "cannot lock" in self_error, self_error

            # the Target must live in the same Parameter Manager (D8)
            other = cli.find_or_create_instrument("parameter_manager_2", PM_CLASS)
            other.add_parameter("elsewhere.x", initial_value=1)
            try:
                pm.lock("q01.IF", "parameter_manager_2.elsewhere.x")
                cross_error = None
            except Exception as exc:  # noqa: BLE001
                cross_error = str(exc)
            assert cross_error is not None
            assert "does not exist" in cross_error, cross_error

            # deleting a Target removes the Locks that pointed at it; the
            # Followers become plain parameters
            pm.remove_parameter("q01Data.IF")
            assert pm.get_lock("q01.IF") is None
            assert pm.q01.IF() == 5000000.0
            # a Follower of a survivor keeps its Lock: q02.IF is locked to
            # q01.IF, which still exists
            assert pm.get_lock("q02.IF") == PMLockBluePrint(
                target="parameter_manager.q01.IF", locked=True
            )

            # removing a Lock announces it with a None payload
            messages = capture_one_broadcast(lambda: pm.remove_lock("q02.IF"))
            text = repr(messages)
            assert text.count("pm-lock-update") == 1, text
            assert "parameter_manager.q02.IF" in text, text
            assert pm.list_locks() == {}
    print("section_locks: OK")


# ---------------------------------------------------------------------------
# Section: Type Locks and Globals
#
# Page claims: lock_type_parameter puts a locked Lock on the entry's
# parameter in every current Instance; with no explicit Target the Target is
# the Globals parameter _globals.<type>.<path>, created on demand with the
# entry's default and unit; setting the Globals parameter moves every
# Follower; on a Proxy, pm.get/pm.set are QCoDeS' local shorthands and raise
# KeyError on a dotted path, attribute access reaches the Globals submodule
# once the Proxy knows it (one update() for a Proxy built before it
# existed), and the Parameter Manager's own dotted get/set run through
# Client.call; Instance parameters already locked to another Target are
# skipped, returned and logged; unlock_type_parameter removes only the rule,
# the Locks it created stay; new Instances created after the rule is removed
# get no Lock; Globals is never an Instance, its parameters cannot be
# created through add_parameter, and a Globals parameter is saved with the
# profile.
# ---------------------------------------------------------------------------
def section_type_locks_and_globals() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm.add_type("qubit")
            pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
            pm.add_instance("qubit", "q01")
            pm.add_instance("qubit", "q02")
            pm.update()

            # the default Target: the Globals parameter, created on demand
            assert pm.lock_type_parameter("qubit", "IF") == []
            assert pm.has_param("_globals.qubit.IF")
            assert "_globals.qubit.IF" in pm.list()

            # this Proxy was built before the Globals parameter existed, so
            # its cached Blueprint does not know the submodule yet
            try:
                pm._globals
                stale_error = None
            except AttributeError as exc:  # noqa: BLE001
                stale_error = str(exc)
            assert stale_error is not None

            # one update() later, attribute access reaches it
            pm.update()
            assert pm._globals.qubit.IF() == 10000000.0

            # the Proxy's own dotted get and set are QCoDeS' local,
            # deprecated shorthands: they raise KeyError on a dotted path
            try:
                pm.get("_globals.qubit.IF")
                proxy_get_error = None
            except KeyError as exc:  # noqa: BLE001
                proxy_get_error = str(exc)
            assert proxy_get_error is not None

            # the Parameter Manager's own dotted get and set are reachable
            # through Client.call
            assert cli.call("parameter_manager.get", "_globals.qubit.IF") == 10000000.0
            for instance in ("q01", "q02"):
                lock = pm.get_lock(f"{instance}.IF")
                assert lock.target == "parameter_manager._globals.qubit.IF"
                assert lock.locked
            # Globals is never an Instance
            assert pm.instances_of("qubit") == ["q01", "q02"]

            # setting the Globals parameter moves every Follower
            cli.call("parameter_manager.set", "_globals.qubit.IF", 12e6)
            assert pm._globals.qubit.IF() == 12000000.0
            assert pm.q01.IF() == 12000000.0
            assert pm.q02.IF() == 12000000.0

            # an explicit Target; an Instance already locked to another
            # Target is skipped, returned and logged
            pm.add_parameter("lo.frequency", initial_value=1e6, unit="Hz")
            pm.remove_lock("q02.IF")
            records = []
            handler = logging.Handler()
            handler.emit = lambda record: records.append(record.getMessage())
            logger = logging.getLogger("instrumentserver.params")
            logger.addHandler(handler)
            try:
                skipped = pm.lock_type_parameter("qubit", "IF", target="lo.frequency")
            finally:
                logger.removeHandler(handler)
            assert skipped == ["q01.IF"], skipped
            assert any("skipped" in message for message in records), records
            assert pm.get_lock("q02.IF") == PMLockBluePrint(
                target="parameter_manager.lo.frequency", locked=True
            )
            assert pm.q02.IF() == 1000000.0
            assert pm.q01.IF() == 12000000.0

            # removing the Type Lock removes only the rule
            pm.unlock_type_parameter("qubit", "IF")
            assert pm.get_type("qubit").parameters["IF"]["target"] is None
            assert pm.get_lock("q02.IF") is not None
            # ... so Instances created afterwards get no Lock
            pm.add_instance("qubit", "q03")
            assert pm.get_lock("q03.IF") is None

            # Globals parameters are created on demand by the Type Lock, not
            # through the public API
            try:
                pm.add_parameter("_globals.extra", initial_value=1)
                globals_error = None
            except Exception as exc:  # noqa: BLE001
                globals_error = str(exc)
            assert globals_error is not None
            assert "reserved" in globals_error, globals_error

            # a Globals parameter is saved with the profile
            pm.toFile()
            document = json.loads(
                (Path.cwd() / "parameter_manager-parameter_manager.json").read_text()
            )
            assert "parameter_manager._globals.qubit.IF" in document["parameters"]
    print("section_type_locks_and_globals: OK")


# ---------------------------------------------------------------------------
# Section: Profiles and files
#
# Page claims: toFile writes the version-2 profile document (values are the
# parameters' own values, lock appears only on Followers); fromFile loads it
# again, with deleteMissing removing parameters the document does not list;
# the dictionary variant takes deleteMissing explicitly; switch_to_profile
# saves the current profile, then clears everything, then loads the new one;
# sorted(pm.refresh_profiles()) reports the profile files of the working
# directory; a file without a version key is the legacy flat map: it loads
# as parameters only, removes the parameters it does not list (their Locks
# with them), leaves Locks whose parameters stay untouched, and writes no
# Types and no Locks; saving always writes version 2.
# ---------------------------------------------------------------------------
def section_profiles_and_files() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)
            pm.add_parameter("lo.frequency", initial_value=5e9, unit="Hz")
            pm.add_parameter("q01.IF", initial_value=10e6, unit="Hz")

            # a Follower, so the profile file shows a lock entry
            pm.lock("q01.IF", "lo.frequency")
            pm.toFile()

            profile = Path.cwd() / "parameter_manager-parameter_manager.json"
            assert profile.exists()
            document = json.loads(profile.read_text())
            assert document["version"] == 2
            assert sorted(document) == ["parameters", "types", "version"]
            assert document["parameters"]["parameter_manager.q01.IF"] == {
                "unit": "Hz",
                "value": 10000000.0,
                "lock": {"target": "parameter_manager.lo.frequency", "locked": True},
            }
            # the Target stores no lock entry, and its own current value
            assert document["parameters"]["parameter_manager.lo.frequency"] == {
                "unit": "Hz",
                "value": 5000000000.0,
            }
            assert document["types"] == {}

            # fromFile restores the saved state: the own value of the
            # Follower and its Lock, so it reads the Target again
            pm.lo.frequency.set(6e9)
            pm.fromFile()
            assert pm.lo.frequency() == 5000000000.0
            assert pm.q01.IF() == 5000000000.0
            assert pm.get_lock("q01.IF") == PMLockBluePrint(
                target="parameter_manager.lo.frequency", locked=True
            )

            # deleteMissing removes the parameters the document does not
            # list; deleteMissing=False keeps them
            pm.add_parameter("temp.extra", initial_value=1)
            document = pm.toParamDict()
            del document["parameters"]["parameter_manager.temp.extra"]
            pm.fromParamDict(document, deleteMissing=False)
            assert pm.has_param("temp.extra")
            pm.fromParamDict(document)
            assert not pm.has_param("temp.extra")

            # a second profile: saving to a profile file also selects it;
            # a plain name lands in the working directory as
            # parameter_manager-cooldown.json
            pm.toFile(name="cooldown")
            assert sorted(pm.refresh_profiles()) == [
                "parameter_manager-cooldown.json",
                "parameter_manager-parameter_manager.json",
            ]
            assert sorted(pm.list_profiles()) == [
                "parameter_manager-cooldown.json",
                "parameter_manager-parameter_manager.json",
            ]

            # the cooldown profile holds a different state: unlocked, and a
            # different value
            pm.unlock("q01.IF")
            pm.lo.frequency.set(8e9)

            # the save selected cooldown, so switch back to the default
            # profile first; the state comes back from the file
            pm.switch_to_profile("parameter_manager")
            assert pm.lo.frequency() == 5000000000.0
            assert pm.get_lock("q01.IF").locked is True

            # change the live state, then switch: the leaving profile is
            # saved first, everything is cleared, then cooldown is loaded
            pm.lo.frequency.set(9e9)
            pm.switch_to_profile("cooldown")
            assert pm.lo.frequency() == 8000000000.0
            assert pm.get_lock("q01.IF") == PMLockBluePrint(
                target="parameter_manager.lo.frequency", locked=False
            )

            # a file without a version key is the legacy flat map: it loads
            # as parameters only. Two of its parameters carry an unlocked
            # Lock in-session first, to observe what the load does to Locks
            # (a locked Follower would refuse the load's set, D6)
            pm.add_parameter("old_target", initial_value=5, unit="Hz")
            pm.add_parameter("old_param", initial_value=1, unit="M")
            pm.lock("old_param", "old_target")
            pm.unlock("old_param")
            legacy = Path.cwd() / "parameter_manager-legacy.json"
            legacy.write_text(
                json.dumps(
                    {
                        "parameter_manager.old_target": {"unit": "Hz", "value": 5},
                        "parameter_manager.old_param": {"unit": "M", "value": 123},
                    }
                )
            )
            pm.fromFile("parameter_manager-legacy.json")
            # the parameters the file does not list are removed, their Locks
            # with them; the Lock between the two listed parameters stays,
            # untouched by the reader
            assert not pm.has_param("lo.frequency")
            assert not pm.has_param("q01.IF")
            assert pm.list_locks() == {
                "old_param": PMLockBluePrint(
                    target="parameter_manager.old_target", locked=False
                )
            }
            pm.update()
            assert pm.old_param() == 123
            assert pm.old_target() == 5

            # saving always writes version 2, even over a legacy file; and
            # loading a profile file selected it, so the save lands there
            pm.toFile()
            assert json.loads(legacy.read_text())["version"] == 2
    print("section_profiles_and_files: OK")


# ---------------------------------------------------------------------------
# Section: The GUI
#
# The GUI's behaviour (the Parameters and Types tabs, tints and gutter
# bands, the "locked to" column and per-row lock button, the context menu,
# the arm strip, the Locks panel, the Types tab panes, and the delete-Target
# confirmation) cannot be asserted from a script; it is verified manually
# (plan task 5.6 records the end-to-end GUI check) and captured in the
# page's screenshots. The same goes for the Server window showing the
# generic instrument widget unless the station config's gui entry names the
# Parameter Manager widget. The keyboard shortcuts the page lists come from
# the GUI's shortcut registry, and that is asserted here.
# ---------------------------------------------------------------------------
def section_the_gui() -> None:
    from instrumentserver.gui.shortcuts import KeyboardShortcutManager

    registry = KeyboardShortcutManager.REGISTRY
    expected = {
        "delete_item": ("Ctrl+Backspace", "Delete the selected parameter"),
        "toggle_locks": ("Ctrl+Shift+L", "Show or hide the Locks panel"),
        "lock_to": ("Ctrl+L", "Lock the selected parameter to… (pick a Target)"),
        "unlock_item": ("Ctrl+U", "Unlock the selected parameter"),
        "show_types": (
            "Ctrl+Shift+Y",
            "Switch between the Parameters and Types tabs",
        ),
        "add_item": ("Ctrl+N", "Jump cursor to the add parameter bar"),
        "load_items": ("Ctrl+Shift+O", "Load parameters from JSON file"),
        "save_items": ("Ctrl+Shift+S", "Save parameters to JSON file"),
        "refresh_all": ("Ctrl+Shift+R", "Refresh all parameters from instrument"),
    }
    for action_id, entry in expected.items():
        assert registry[action_id] == entry, (action_id, registry[action_id])
    print("section_the_gui: OK")


# ---------------------------------------------------------------------------
# Section: Using it from measurement code
#
# Page claims: a measurement script finds (or creates) the Parameter Manager
# through a Client; a Type keeps repeated structures complete and a Type
# Lock shares one value; the sweep sets the Globals Target and reads the
# Followers through the Proxy; setting a locked Follower raises, so a
# deviating parameter is unlocked first and rejoins with relock; the profile
# is saved at the end of the experiment.
# ---------------------------------------------------------------------------
def section_using_it_from_measurement_code() -> None:
    with workspace(), server():
        with client() as cli:
            pm = cli.find_or_create_instrument(PM_NAME, PM_CLASS)

            # one-time setup: the parameters the experiment needs
            pm.add_parameter("power", initial_value=-10, unit="dBm")
            pm.add_type("qubit")
            pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
            pm.add_instance("qubit", "q0")
            pm.add_instance("qubit", "q1")
            pm.update()

            # one shared IF for both qubits: the Type Lock's Globals Target
            pm.lock_type_parameter("qubit", "IF")

            # the sweep: set the Target, read the Followers (the page shows
            # this loop with print, so the script runs the same expressions)
            printed = []
            for if_hz in (10e6, 11e6, 12e6):
                cli.call("parameter_manager.set", "_globals.qubit.IF", if_hz)
                printed.append(f"{pm.q0.IF()} {pm.q1.IF()}")
            assert printed == [
                "10000000.0 10000000.0",
                "11000000.0 11000000.0",
                "12000000.0 12000000.0",
            ], printed

            # a locked Follower refuses set: unlock first, then rejoin
            try:
                pm.q0.IF.set(13e6)
                deviate_error = None
            except Exception as exc:  # noqa: BLE001
                deviate_error = str(exc)
            assert deviate_error is not None
            assert "is locked to" in deviate_error, deviate_error
            pm.unlock("q0.IF")
            pm.q0.IF.set(13e6)
            assert pm.q0.IF() == 13000000.0
            assert pm.q1.IF() == 12000000.0
            pm.relock("q0.IF")
            assert pm.q0.IF() == 12000000.0

            # end of the experiment: save the profile
            pm.toFile()
            assert (Path.cwd() / "parameter_manager-parameter_manager.json").exists()
    print("section_using_it_from_measurement_code: OK")


if __name__ == "__main__":
    section_concept()
    section_hierarchical_parameters()
    section_types()
    section_locks()
    section_type_locks_and_globals()
    section_profiles_and_files()
    section_the_gui()
    section_using_it_from_measurement_code()
    print("verify_parameter_manager: all sections OK")
