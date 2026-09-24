# History: Parameter Manager Redesign (Types and Locks)

One section per finished task, in the order the tasks were done. Written by the historian agent from the commits and the orchestration working files.

## 0.1 `ParameterGroup` split — 2026-09-23

`src/instrumentserver/params.py` now has `ParameterGroup(InstrumentBase)`, a Parameter Group that holds parameters and nested groups and carries the tree helpers moved out of `ParameterManager` (`_get_param`, `_get_parent`, `has_param`, `parameter`, `to_tree`/`_to_tree`, `list`, `remove_empty_submodules` and the dotted `add_parameter`/`remove_parameter`/`get`/`set`). `ParameterManager(ParameterGroup)` keeps only the root's job: `workingDirectory`, profiles and file load/save. Submodules made by `_get_parent(..., create_parent=True)` are now plain `ParameterGroup(n)` objects, so creating `q01.IF` no longer lists the working directory or tries to load `parameter_manager-q01.json`. Two new tests in `test/pytest/test_param_manager.py` cover this: `test_submodules_are_groups` and `test_submodule_does_not_load_parameter_file`.

### Commit by commit
- `46e34cd` The whole task in one commit. It moved the tree helpers into `ParameterGroup`, made `ParameterManager` subclass it, changed `_get_parent` to create `ParameterGroup(n)`, and changed the `_to_tree` assertion to `isinstance(sm, ParameterGroup)`. It also added the two tests. The first test checks that `q01` and `q01.readout` are groups and not managers, and that no "parameter file not found" warning shows up in `caplog`. The second writes a `parameter_manager-q01.json` into `tmp_path` and checks that `q01` does not pick up `file_param`. All 10 existing tests passed without changes (12 passed, full suite 161 passed). All six reviewers approved in round 0 and there were no fix commits.

### Dropped findings
- test-reviewer-qwen said `test_submodule_does_not_load_parameter_file` never asserts that `q01` is a `ParameterGroup` (should-fix) → dropped because it is wrong: the test in `46e34cd` has `assert isinstance(params.q01, ParameterGroup)`.
- The "no longer lists the working directory" half of the acceptance has no direct assertion. It holds only because `ParameterGroup` has no `refresh_profiles` (raised as a nit by test-reviewer-deepseek and reviewer-deepseek) → not sent. The sibling test already shows that no file logic runs on a submodule.
- `test_submodules_are_groups` runs in the real cwd, so its `caplog` check would pass without testing anything if a `parameter_manager-q01.json` ever sat there (test-reviewer-deepseek, nit) → not sent. It is worth adding `monkeypatch.chdir(tmp_path)` the next time a task touches this file.

### Loose ends
- A dead local `full_name` in `_get_parent` was already there before this task and moved over unchanged (noted by the coder and plan-checker-deepseek). Left alone as out of scope under plan rule 6.
- The 4 `PytestUnknownMarkWarning`s for the unregistered `integration` mark in `test_apps.py` are out of scope. The `_newOrDeleteParameterDetection` KeyError belongs to task 0.4.

### Process notes
- Three reviewers ran the full `uv run pytest` at the same time on fixed ports and got noise: a port-5555 `ZMQError` in `test_server_gui.py::test_loading_button`, a setup error in the `param_manager` fixture, and a PyQt crash. Each passed alone or on a rerun, and the orchestrator's own run was green. Recorded for RUNS.md: reviewers should run only the named test file, or take turns on full-suite runs.
- reviewer-deepseek went idle without writing a report or sending worker_done. It finished after a nudge.
- reviewer-deepseek's request to run `git worktree add` into `/tmp` to check the base was rejected, and it was told to use `git show <base>:<path>` instead.
- test-reviewer-qwen sent worker_done twice. Orca rejected the second one.
- The times in `decisions.md` mix two clocks (21:xx and 16:xx entries are interleaved), so the log order there is more reliable than its timestamps.

## 0.0 Per-run test ports — 2026-09-23

`test/pytest/conftest.py` now has a session-scoped `server_port` fixture. It draws a random port from 20000–40000, checks by binding that both `port` and `port + 1` (the Broadcast port) are free, and gives up with a `RuntimeError` after 100 tries. `start_server`, its shutdown `BaseClient`, `cli`, and the tests in `test_client_station.py`, `test_server_gui.py` and `test_gui_navigation.py` all take the port from it, and `AGENTS.md` gained the "Tests never use a fixed port" rule under "Testing". No change to `src/`. The task was added to the plan after the 0.1 pilot, where three reviewers running the suite at the same time collided on port 5555.

### Commit by commit
- `dcac611` (base, not task code) Tooling commit that added task 0.0 and decision D27 to the plan, together with the orchestration tooling changes (qwen roles moved to `qwen3.8-27b`, `wait-event.sh`, extra opencode permissions).
- `71aa9af` The whole task in one commit. Besides the planned edits, three things the task text did not spell out:
  - `test_apps.py` also held the literal 5555, in argparse-default assertions rather than a live server port. The file was not listed in the task, but the acceptance grep covered it, so the orchestrator ruled before dispatch that the grep wins. The four default asserts now compare against `instrumentserver.DEFAULT_PORT`, and the two mocked `parameterManagerScript` tests pass `--port 4567`.
  - `test_server_gui.py` gained `_wait_until_client_points_at_server`. The embedded client first connects to the default port and only switches to the real one when the server-started signal arrives. With a fixed default port that race did no harm; with a random port the first request could go to the wrong address. The helper copies the wait `test_gui_navigation._start_window` already had.
  - The coder's first version probed sequentially in the OS ephemeral range. Two sessions starting together got overlapping pairs, so it switched to the random wide-range draw.
  Checks: the orchestrator's two concurrent `uv run pytest -q` runs both gave 161 passed, and the acceptance grep (with `__pycache__` excluded) found nothing. All six reviewers approved in round 0 with only nits. The fix list was empty, so there were no fix commits.

### Dropped findings
- The `server_port` docstring says 20000–40000 is "outside the OS ephemeral port range". That holds on macOS but not on Linux, where the range starts at 32768 (reviewer-deepseek, reviewer-qwen, test-reviewer-qwen, plan-checker-qwen, all nit) → not sent. It is a wording problem only, since the bind check still guarantees a free pair. Fix it the next time a task touches `conftest.py`.
- `_wait_until_client_points_at_server` duplicates the wait in `test_gui_navigation.py` (reviewer-deepseek, nit) → not sent; a refactor preference. The other reviewers called the wait a needed race fix.
- `server_port` has no unit test of its own, and a port could be taken between the check and the server's bind (test-reviewer-deepseek, nits; test-reviewer-qwen made the same fixture-test point) → not sent. The plan's test criterion is "whole suite green", and a bad pair fails every test that uses a server, so it cannot fail silently.

### Questions to Marcos
- plan-checker-qwen: the plan's Testing conventions still said GUI tests use their "own server on a fixed port ≥ 5600", which D27 made stale → raised in the run report (RUNS.md). The plan now says "own server on the `server_port` fixture, never a fixed port, see D27". That edit was committed afterwards in `0fbbddf`.

### Loose ends
- The acceptance line in the plan was changed on 2026-09-23 from `grep -rn` to `git grep -n "5555\|5599" -- test/pytest`, because the old grep also matched stale `__pycache__` bytecode. During the run the coder deleted the `.pyc` files to make the old grep pass, and the orchestrator ran it with `__pycache__` excluded.
- `test/test_async_requests/test_client.py` and `demo_concurrency.py` still use a literal 5555 (reviewer-qwen). They are outside `test/pytest` and outside this task.

### Process notes
- reviewer-deepseek's output degenerated into garbage, and it went idle with no report. It went idle a second time after deciding to approve without writing the report. Each time a terminal nudge got it going again, and it finished after the second nudge, about 35 minutes after dispatch.
- The coder's permission requests were mostly `perl -pi` edits of the named test files and three rounds of paired concurrent pytest runs. Each was allowed once. The one out-of-repo write was the pytest logs in opencode's temp dir.
- With the new fixture, reviewers ran the full suite at the same time without the port clashes seen in the 0.1 pilot.

## 0.2 `Broadcaster` mixin — 2026-09-23

`src/instrumentserver/base.py` now has a `Broadcaster` mixin right after `sendBroadcast`. It keeps its sinks in a plain list (`_broadcast_sinks`) and has `add_broadcast_sink(fn)`, `remove_broadcast_sink(fn)` (does nothing if `fn` is not registered) and `broadcast(bp)`. `broadcast` calls each sink in registration order, logs an exception from one sink with `logger.exception` and carries on with the rest, and does nothing when there are no sinks. `ParameterManager` is now `ParameterManager(Broadcaster, ParameterGroup)` and does not broadcast anything yet. The new `test/pytest/test_broadcaster.py` holds the unit part: 9 server-free tests after the fix round.

### Commit by commit
- `8d04b42` The mixin, the change to `ParameterManager`'s bases plus a docstring paragraph, and 8 tests: no-op without sinks, delivery, registration order, exception isolation (checks one ERROR record naming `failing_sink`, with `exc_info`), removal, removing an unregistered sink, and two tests on a real `ParameterManager` run under `monkeypatch.chdir(tmp_path)`. One change the task text did not ask for: the annotations on the three public methods are strings (`"ParameterBroadcastBluePrint"`). The client builds proxy methods by exec-ing the call-signature string from the blueprint. An unquoted annotation shows up as the dotted `instrumentserver.blueprints.ParameterBroadcastBluePrint`, which the exec'd code cannot resolve, so building any `ParameterManager` proxy would fail with a `NameError`. The class docstring tells Phase 1 to quote annotations the same way, and reviewer-qwen reproduced the failure on its own. Orchestrator run: 8 passed in the file, 169 in the full suite.
- `693d4e7` Fix from round 1: `test_adding_the_same_sink_twice_delivers_twice`. It adds the same sink twice, checks that one `broadcast` reaches it twice, then removes it once and checks that the next `broadcast` reaches it once. test-reviewer-qwen caught the gap (should-fix): the docstring promises "added twice → receives twice", 0.3 builds the Server's sink registration on that promise, and no test checked it. Both test reviewers confirmed the fix in re-review; all six approved with no new findings. Orchestrator run: 9 passed in the file, 170 in the full suite.

### Dropped findings
- The `_broadcast_sinks` annotation in `__init__` is not quoted, although the docstring says to quote annotations (reviewer-deepseek, nit) → not sent. `__init__` is never proxied.
- `add_broadcast_sink` does not check that `fn` is callable, and the log line in `broadcast` reads `bp.name`/`bp.action`, so it would raise itself if `bp` is not a blueprint (reviewer-qwen, two nits) → not sent. Both only happen when a caller breaks the contract.

### Loose ends
- For 0.3 (reviewer-qwen, recorded in `decisions.md`): once the Server registers as a sink, a remote client can call `pm.broadcast`, since every public method can be proxied and `deserialize_obj` turns a dict carrying `_class_type` back into a real `ParameterBroadcastBluePrint`. That lets a client put any blueprint it likes on the PUB stream. `add_broadcast_sink` cannot be called over the wire, because a callable does not serialize to JSON. The exposure comes from the plan's "public methods are proxyable" design and is not a 0.2 defect.
- The fact that the client execs signature strings, and so breaks on unquoted class annotations, was left out of scope by the coder. For now the only guard is the docstring rule.

### Process notes
- plan-checker-deepseek's turn ended on a provider "Upstream error" with no report after about 10 minutes. It finished after a terminal nudge.
- Three permission requests were rejected. reviewer-deepseek asked for `~/.agents/roles` (the role file is in the worktree) and, in re-review, for a garbled path outside the repo. plan-checker-deepseek tried to write its report through a python heredoc whose target path was cut off, and was told to use the file-write tool.

## 0.3 Server registers sinks — 2026-09-23

`StationServer` in `src/instrumentserver/server/core.py` now has `_registerBroadcaster(instrument)`. If the instrument has `add_broadcast_sink`, the helper registers `self._broadcastParameterChange` as a Broadcast sink on it. It is called right after `self.station.add_component(new_instrument)` in `_createInstrument`, and in `__init__` in a loop over every Station component once the config instruments are loaded. A one-line comment above `_instrument_locks` notes that prose calls it the "instrument mutex" (ADR-0003); nothing was renamed. For the tests, `DummyBroadcasterInstrument(Broadcaster, Instrument)` was added to `testing/dummy_instruments/generic.py`. Its `emit_broadcast` method builds a `ParameterBroadcastBluePrint` for `param0`, broadcasts it and returns it. The server part of `test/pytest/test_broadcaster.py` has three tests, which brings the file to 12.

### Commit by commit
- `04c4cbc` The helper, the two call sites, the mutex comment, `DummyBroadcasterInstrument`, and two tests. `test_created_broadcaster_instrument_reaches_subclient` creates `bcaster` through `cli.find_or_create_instrument` and checks that the Server's sink is in the instrument's `_broadcast_sinks`. It then calls `emit_broadcast` through the proxy and checks that a `SubClient` gets exactly one Broadcast with the right name, action, value and unit. Exactly one means the Server registered only once. `test_plain_dummy_instrument_still_works_and_gets_no_sink` sets and gets `param0` on the plain dummy and checks that the server-side object has no `add_broadcast_sink`. The file also gained the `capture_broadcasts` / `wait_for_broadcasts` helpers, copied from `test/docs_verification/helpers.py` but using the `server_port` fixture's Broadcast port. The coder pointed out that nothing tested the config-load loop. Orchestrator run: 11 passed in the file, 172 in the full suite.
- `5167241` Fix from round 1, test only: `test_config_loaded_broadcaster_instrument_gets_sink`. The test writes a config YAML with a `cfg_bcaster` `DummyBroadcasterInstrument` (`initialize: True`) to `tmp_path` and runs it through `loadConfig`. It then builds a `StationServer` directly, without starting it, and checks that the component is a `Broadcaster` with exactly one sink, the Server's. The teardown closes the temp file, the wake-up socket pair and the instrument. Both test reviewers caught the gap: test-reviewer-qwen called it must-fix and test-reviewer-deepseek should-fix. The plan's Testing table says `test_broadcaster.py` covers "created **and** config-loaded instruments", but the `__init__` loop could be deleted with every test still green. During the fix the coder removed the loop for a moment to show that the new test fails without it. The commit leaves the loop in place, and both test reviewers confirmed the new test fails when the loop is removed. The coder skipped the optional `SubClient` check because a server that was never started has no bound PUB socket. The created-instrument test already covers the wire path. All six reviewers approved in re-review. Orchestrator run: 12 passed in the file, 173 in the full suite.

### Dropped findings
- plan-checker-qwen pointed out that `_registerBroadcaster` is camelCase, while plan rule 8 says new methods are snake_case → not sent. The task text gives that exact name.
- plan-checker-deepseek noted that the `__init__` loop registers on every Station component, not only the ones loaded from config → not sent. Right after `__init__` the Station holds only the config-loaded instruments, and this matches ADR-0003.
- test-reviewer-qwen noted that "gets no sink" is checked with `hasattr(add_broadcast_sink)`, which tests the dummy's class rather than the Server's behaviour → not sent. That check is valid because registration depends on that same `hasattr`.

### Loose ends
- Instruments that `_runInitScript` adds to the Station (it runs from `startServer`, after the `__init__` loop) get no sink (plan-checker-qwen, reviewer-qwen). The plan names only two entry points, so 0.3 followed it. This is question 1 for Marcos in `orchestration/RUNS.md` (run_e6f4c00ea2df): add a small follow-up task or accept the gap. Neither the working folder nor the plan records an answer yet.
- The 0.2 note has now come true: the Server is a sink, so a client can call `broadcast` on a Broadcaster proxy and put a Broadcast of its own on the PUB stream (reviewer-qwen). reviewer-qwen called it inert in practice, because callables do not survive JSON and a malformed `broadcast(dict)` goes down the logged sink-error path. This is question 2 in the same RUNS.md entry, also unanswered.
- `capture_broadcasts` / `wait_for_broadcasts` now exist in two places. RUNS.md suggests moving them into `conftest.py` once a third copy is needed (1.3 / 2.5).

### Process notes
- reviewer-deepseek went idle in round 0 after "Let me write my report", with no report and no worker_done. It finished after a nudge.
- In re-review, test-reviewer-deepseek stalled on a provider "Upstream error", and plan-checker-deepseek's output turned into garbage. Neither left a report. Both finished after nudges.
- test-reviewer-deepseek asked to run a garbled command with `mv` and broken redirections. It was rejected, and the reviewer was told to use the file-write tool.

## 0.4 Pre-existing fixes (D24, first two) — 2026-09-23

Two of the three pre-existing defects listed in D24 are fixed. In `src/instrumentserver/server/core.py`, `StationServer._newOrDeleteParameterDetection` now reads `kwargs.get("initial_value")` and `kwargs.get("unit", "")`. Before, a proxied `add_parameter("x")` with no initial value or unit raised a `KeyError` on the server, and the client got an error back. In `src/instrumentserver/apps.py`, `parameterManagerScript` passes `sub_port=args.port + 1, sub_host="localhost"` to `ParameterManagerGui`, so the GUI's Broadcast listener follows `--port` and no longer stays on the default port. The new test `test_add_parameter_without_initial_value_succeeds_and_broadcasts` in `test/pytest/test_param_manager.py` covers the first fix, and the two existing launcher tests in `test_apps.py` cover the second.

### Commit by commit
- `56ece34` The whole task in one commit. One change the task text did not ask for: the launcher's `--port` argument got `type=int`. Without it, a port given on the command line stays a string and `args.port + 1` raises `TypeError`. All three reviewers who raised it (both plan checkers and reviewer-deepseek) said it is needed for the expression the plan gives. Only this parser changed; `serverScript` and the other launchers still pass the port as a string, and `test_server_script_passthrough_args` still pins that. `test_param_manager_script_instrument_exists` and `test_param_manager_script_instrument_missing` now assert `ParameterManagerGui` is called with `mock_pm, sub_port=4568, sub_host="localhost"` for `--port 4567`. The new proxy test calls `params.add_parameter("x")` through the `param_manager` fixture and checks that `x` exists and that a `SubClient` on `server_port + 1` gets exactly one `parameter-creation` Broadcast named `parameter_manager.x`, with `value is None` and `unit == ""`. plan-checker-qwen confirmed the test fails on the old code, where the server's error reaches the client as an exception. Orchestrator run: 31 passed in the two files, 174 in the full suite. All six reviewers approved in round 0 with only nits. The fix list was empty, so there were no fix commits.

### Dropped findings
- `capture_broadcasts` / `wait_for_broadcasts` are copied word for word from `test_broadcaster.py` into `test_param_manager.py` (reviewer-qwen, test-reviewer-qwen, reviewer-deepseek, all nit) → not sent. See Loose ends.
- The launcher tests cover only `--port 4567`, not the default port (test-reviewer-qwen, test-reviewer-deepseek, nit) → not sent. The plan asks only to extend the two existing tests, and that was done. test-reviewer-deepseek's reasoning here is wrong in its details: it calls 4567 "an already-integer port", but `sys.argv` holds a string, so these tests do exercise the `type=int` conversion.

### Loose ends
- There are now two copies of `capture_broadcasts` / `wait_for_broadcasts`. Move them into `conftest.py` when a third is needed (1.3 / 2.5), as noted after 0.3.
- D24's third item, `ParameterManagerTreeView.onItemNewValue` calling `widget._setMethod(value)`, was left alone as planned. It belongs to task 5.1.

### Process notes
- plan-checker-deepseek and test-reviewer-deepseek stalled on a provider "Upstream error", and reviewer-deepseek's output turned into garbage. None of them left a report. The orchestrator's first nudge never reached their terminals because of a bug in its own shell command (an empty terminal handle), and it was sent again about 10 minutes later. After that, reviewer-deepseek wrote a full report but hit a provider error before worker_done, test-reviewer-deepseek's report ended in garbage, and plan-checker-deepseek wrote only a skeleton. All three finished after a second, more specific nudge.
- plan-checker-deepseek asked for a garbled `/Users:/Users/...` path outside the repo. It was rejected, and it was told to use the relative report path.

## 0.5 Broadcast action constants — 2026-09-24

`src/instrumentserver/blueprints.py` now defines six string constants for the `action` of a Broadcast: `PARAMETER_UPDATE`, `PARAMETER_CALL`, `PARAMETER_CREATION`, `PARAMETER_DELETION`, `PM_LOCK_UPDATE` and `PM_TYPE_UPDATE`. Their values are the unchanged wire strings (`"parameter-update"` … `"pm-type-update"`). `server/core.py`, `gui/instruments.py` and `client/application.py` use them wherever they used a literal before. `monitoring/listener.py` had no `parameter-` literal and did not change. `test_broadcast_action_constants_pin_the_wire_strings` in `test/pytest/test_broadcaster.py` pins all six values. This was the last task of Phase 0.

### Commit by commit
- `b3e6586` The constants, with a comment calling them the exact wire strings and saying that the two `PM_*` ones are emitted by Broadcaster instruments. No code emits them yet. The commit also replaces nine literals: the `parameter-update`/`parameter-call` Broadcasts in `StationServer`'s call path, the `parameter-creation`/`parameter-deletion` Broadcasts in `_newOrDeleteParameterDetection`, the four action checks in `ModelParameters.updateParameter`, and the one in `ClientStationGui.listenerEvent`. Three literals were left on purpose, and the orchestrator confirmed the list with `git grep`: the definitions themselves, the comment and log-parsing regex at `log.py:157-158`, and the `action="parameter-update"` default of `DummyBroadcasterInstrument.emit_broadcast` in `testing/dummy_instruments/generic.py`. Orchestrator run: 174 passed in the full suite.
- `eec0c25` Fix from round 1, test only: `test_broadcast_action_constants_pin_the_wire_strings` is a no-server test that asserts each constant equals its wire string. test-reviewer-qwen caught the gap (should-fix). Once every emitter and consumer in the repo shares the constants, a typo in a constant's value would leave the suite green and break external subscribers, and ADR-0003 says those subscribers parse the strings unchanged. test-reviewer-deepseek disagreed and said existing tests already guard the strings. The orchestrator checked with `git grep`: the literals in `test_base.py` and `test_broadcaster.py` compare literals to literals, or to the dummy's literal default, so only `test_param_manager.py:117` tests a string that comes from a constant. The finding was kept. Both test reviewers confirmed the fix in re-review; test-reviewer-deepseek now agreed with the orchestrator's call. All six approved. Orchestrator run: 13 passed in the file, 175 in the full suite.

### Dropped findings
- `log.py:158` still has `parameter-update` in its log-parsing regex, and the `emit_broadcast` default in `generic.py` keeps its literal (reviewer-qwen, both plan checkers, all nit) → not sent. Neither file is one of the modules the task names, and the wire value is the same.
- The `blueprints.py` comment says the `PM_*` actions are "emitted by" Broadcaster instruments, although no code emits them yet (reviewer-deepseek, nit) → not sent. The comment describes what D10/D26 plan.
- The new test's docstring claims the whole suite would pass if a constant drifted. That overstates it, since `test_param_manager.py:117` already pins `parameter-creation` (reviewer-qwen, re-review nit) → not sent.

### Process notes
- In round 0, test-reviewer-deepseek stalled on a provider "Upstream error" and plan-checker-deepseek's output turned into garbage. Neither left a report. After nudges, test-reviewer-deepseek wrote its report but stopped before worker_done, and plan-checker-deepseek hit two more provider errors, the last one on its report write. Both finished after further nudges.
- Four permission requests were rejected: reviewer-deepseek asked for `/tmp` and then sent a garbled request; test-reviewer-deepseek sent a garbled request; and in re-review plan-checker-deepseek asked for a garbled path outside the repo. Each was pointed back to writing its report file.
- In re-review, test-reviewer-deepseek's worker_done text came through garbled, but its report was at the right path.

## 1.1 `ManagedParameter` — 2026-09-24

`src/instrumentserver/params.py` now has `ManagedParameter(Parameter)`, the first task of Phase 1. It carries `lock: PMLockBluePrint | None`, a private `_target` (the Target parameter object), a read-only `locked` property (true when a Lock is present and `lock.locked`), a `path` property (the full dotted path, or the plain name when standalone) and `own_value()`. While locked, `get` answers with the Target's value (pulled on each get, ADR-0002), `set` raises `ValueError("<Follower path> is locked to <Target path>")`, and `snapshot_base` reports the Target's value; a `lock` entry is in the snapshot whenever a Lock exists, locked or not. `ParameterManager.add_parameter` creates `ManagedParameter`s and sets `path` to `f"{self.name}.{name}"`. `PMLockBluePrint(target, locked, _class_type="PMLockBluePrint")` is in `blueprints.py` and part of `BluePrintType`. The new `test/pytest/test_pm_locks.py` has 11 server-free tests; the Lock is wired by hand on the parameter objects, since the Lock API is task 1.2.

### Commit by commit
- `0f58c83` The class, the blueprint, and 9 tests (get redirect with pull on Target change, set raises and changes nothing, unlocked Lock exposes the own value, cache untouched by locking, three snapshot cases, `own_value` in every state, the manager creating `ManagedParameter`s). Three things the task text did not spell out:
  - Besides `get_raw`, the coder overrode `_wrap_get`. qcodes' get wrapper writes every answered value into the parameter's cache, so a locked get would have overwritten the Follower's own value, which unlocking must expose again. `test_locking_leaves_the_own_cache_untouched` checks this.
  - `lock` and `_target` are set before `super().__init__`, because an `initial_value` already runs `set_raw`.
  - `ParameterGroup.add_parameter` now uses `kw.setdefault("parameter_class", Parameter)` instead of forcing `Parameter`, so the manager's override reaches parameters created in submodules.
  Orchestrator run: 22 passed in `test_pm_locks.py` + `test_param_manager.py`, 184 in the full suite.
- `9c11376` Fix from round 0, two items:
  - The locked-set message used qcodes' `full_name`. Inside a manager that reads `q02_y is locked to q01_x`: underscore-joined, and without the instrument name because `ParameterGroup`s have no parent chain. reviewer-qwen caught the message and test-reviewer-qwen the test's blind spot (the test built its expected string from `full_name` too, so it could not tell). The orchestrator reproduced it and read the task's "full_name" as the plan's full dotted path (rule 4, D10, D19). The fix adds the `path` constructor argument and property, sets it in `ParameterManager.add_parameter`, and takes the Target half from `self.lock.target`. New test `test_set_while_locked_names_dotted_full_paths_inside_a_manager` checks `parameter_manager.q02.y is locked to parameter_manager.q01.x`.
  - With `update=True`, `snapshot_base` read the Target twice: once through the base snapshot's `get`, again in the override. Raised as a nit by both general reviewers and plan-checker-glm, and sent because a fix round was happening anyway. The override now runs only when `update is not True`. For a falsy `update` it still calls the Target's `get()`, not its cache, so each hop of a chain reads by its own state (D7); reviewer-glm had suggested the cache, and the orchestrator told the coder not to. New test `test_locked_snapshot_gets_the_target_once_per_snapshot` counts Target reads with a `CountingManagedParameter` subclass.
  All six reviewers approved in re-review, and each one that raised an item confirmed it fixed. Orchestrator run: 11 passed in `test_pm_locks.py`, 24 in the two named files, 186 in the full suite.

### Dropped findings
- The locked redirect is written twice, in `get_raw` and in `_wrap_get` (reviewer-glm, nit) → not sent. The plan asks for `get_raw` by name, and both copies are one identical line.
- No test covers the `setdefault` passthrough in `ParameterGroup.add_parameter` (test-reviewer-glm, nit) → not sent. No caller passes `parameter_class`; noted for 1.2.
- No `PMLockBluePrint` serialization round-trip test (test-reviewer-qwen, nit) → not sent. The plan puts wire tests in 1.3.
- The `value` override ignores `snapshot_value=False`, and with `snapshot_get=False` a locked `snapshot(update=True)` would report the own value (reviewer-qwen round 0, plan-checker-qwen round 1, nits) → not sent. The Parameter Manager never creates such parameters.

### Questions to Marcos
- Does the task text's `full_name` in the locked-set message mean the full dotted path (`parameter_manager.q02.y`) rather than qcodes' `full_name`? The orchestrator decided yes and flagged it for the run report. No answer is recorded yet.

### Loose ends
- Carried forward in `decisions.md` for later tasks: v1 `toParamDict` saves the Target's value for a locked parameter until 4.1 (reviewer-qwen); `ParameterBroadcastBluePrint.value` is annotated `int | None` and needs widening in 1.3 (reviewer-qwen); a parameter added over the wire straight on a submodule group (`pm.q01.add_parameter`) is a plain `Parameter` with no `path`, which 1.2's validation must handle (test-reviewer-qwen).
- The error message now takes the Target half from the stored `lock.target`, not the live Target object, so 1.2 owns checking that the stored Target exists.

### Process notes
- reviewer-qwen tried to write a scratch script to opencode's temp dir outside the repo. It was rejected, and the reviewer was told to use `orchestration/1.1/`; it ran and then deleted the script there, in both rounds.
- First run with the glm reviewers in place of deepseek: no stalls, no garbled output, and no nudges were needed.

## 1.2 Lock API on `ParameterManager` — 2026-09-24

`ParameterManager` in `src/instrumentserver/params.py` now has the D9 Lock API: `lock`, `unlock`, `relock`, `toggle_lock`, `remove_lock`, `get_lock`, `list_locks` and `followers_of`. Paths go in and come out relative to the Parameter Manager; the Target stored in `PMLockBluePrint` is the full dotted path. Every method validates before it changes anything: `_resolve_param` names an unknown path, `_require_lock` names a parameter with no Lock, and `_check_lock_allowed` refuses a self-lock or a cycle, walking Targets whether their Locks are locked or not (D7) and naming the whole chain. `remove_parameter` is overridden to remove every Lock whose Target is the removed parameter, locked or unlocked, before deleting (D3); `remove_all_parameters` and `fromParamDict` go through it. By the end of the task, Parameter Groups inside a Parameter Manager also route their `add_parameter`/`remove_parameter` to the root. `test/pytest/test_pm_locks.py` grew from 11 to 48 server-free tests.

### Commit by commit
- `be90053` The Lock API, the `remove_parameter` override, `ParameterGroup._iter_params` (yields every parameter in the tree with its relative path), and 23 tests on a `pm` fixture run under `monkeypatch.chdir(tmp_path)`. They cover the redirect and pull, re-targeting (`test_lock_re_targets_an_existing_lock`, `test_a_failed_re_target_leaves_the_old_lock_untouched`), two- and three-node cycles including one through an unlocked Lock, relock re-running the cycle check on hand-wired state, chains read hop by hop, and Lock cleanup on removal, including a chain middle. Before writing the code the coder asked three questions. The orchestrator answered two from the plan: calls on a parameter with no Lock raise `ValueError` naming the path, and a plain qcodes `Parameter` inside the tree can be a Target but not a Follower (`"... cannot carry a Lock"`, pinned by `test_lock_with_a_plain_group_parameter`). The third went to Marcos (see Questions). The coder's `ask` timed out after about 40 minutes, before the answer arrived, so it went ahead with strict raising for that case. Orchestrator run: 47 passed in the two named files, 209 in the full suite.
- `c636f5c` Fix round 1, sent before any review because the behaviour went against Marcos's answer, so reviewing it made no sense. `unlock` on an unlocked Lock and `relock` on a locked Lock now return after one `logger.info` line (`<path> is already unlocked; nothing to do` / `... is already locked; nothing to do`). The no-op `relock` does not re-run the Target or cycle checks and does not touch `_target`. `test_state_inconsistent_calls_raise_naming_the_path` became `test_calls_without_a_lock_raise_naming_the_path` plus two `caplog` tests; the `relock` one plants a sentinel on `_target` to show the mutation path never ran. The round-0 reviewers reviewed this commit together with `be90053`. Orchestrator run: 49 in the named files, 211 in the full suite.
- `8f7fb11` Fix round 2, from round 0:
  - `lock` now resolves both paths first and joins every failure into one `ValueError`, so `lock("nope1", "nope2")` names both. Before, it stopped at the first, against plan rule 3. Caught by plan-checker-glm and reviewer-glm (both should-fix). New test `test_lock_with_two_unknown_paths_names_both`.
  - `test_unknown_path_raises_naming_the_path_and_changes_nothing`, run for `unlock`, `relock`, `toggle_lock`, `remove_lock`, `get_lock` and `followers_of`. Only `lock` had an unknown-path test. Caught by both test reviewers (test-reviewer-glm must-fix, test-reviewer-qwen should-fix), citing the plan's rule that every error path has a test.
  - `test_relock_with_a_missing_remembered_target_raises_naming_both` hand-wires a Lock remembering `parameter_manager.gone`. The API itself cannot reach that state, since removing a Target removes its Locks. Raised by both test reviewers and plan-checker-qwen.
  Orchestrator run: 57 in the named files, 219 in the full suite.
- `3481f56` Fix round 3, from Marcos's decision on a finding held back in round 0. reviewer-qwen showed live that `pm.q02.remove_parameter("y")`, which a client can call over the wire because every public submodule method is proxied, skipped the root's cleanup: the Lock stayed in `list_locks()` and the Follower kept answering the deleted Target's last value through `_target`. Marcos chose to delegate to the root. Each Parameter Group now has `_root` and `_path_prefix`, set in `_get_parent(create_parent=True)` through a `_root_for_new_groups()` hook that the root overrides to return itself. With `_root` set, `ParameterGroup.add_parameter`/`remove_parameter` forward to the root with `<prefix><name>`. The plain creation path now ends in the new `_add_own_parameter`, so the root's own call does not route again, and a standalone group behaves as before. This also settles the 1.1 loose end: `pm.q01.add_parameter` now creates a `ManagedParameter` with the right `path`. `test_lock_with_a_plain_group_parameter` builds its plain `Parameter` through `_add_own_parameter`, the only way left. Four new tests: `test_group_remove_parameter_delegates_to_the_root`, `test_group_add_parameter_creates_a_managed_parameter`, `test_nested_group_add_parameter_creates_a_managed_parameter` and `test_standalone_group_keeps_plain_parameters`. In re-review all six approved; reviewer-qwen confirmed its finding fixed, and reviewer-glm checked the routing at depth 3 and found no recursion. Orchestrator run: 48 in `test_pm_locks.py`, 61 in the named files, 223 in the full suite.

### Dropped findings
- `get_lock`, `list_locks` and `followers_of` quote their return annotations although `PMLockBluePrint` is imported (reviewer-glm, reviewer-qwen, nit) → not sent, style only. The quotes are harmless; 0.2's rule to quote annotations for the proxy exec is a reason to keep them.
- `toggle_lock` checks the parameter and its Lock, then calls `unlock`/`relock`, which check again (reviewer-glm, nit) → not sent.
- No test that a `remove_parameter` on an unknown path leaves every Lock in place, and no Lock at depth 2 in the Lock API tests (test-reviewer-qwen, nits) → not sent; the orchestrator suggested folding them into 1.3's tests. `3481f56`'s nested-group test now locks at depth 2, but `list_locks`/`followers_of` keys at that depth are still unchecked.
- `test_calls_without_a_lock_raise_naming_the_path` matches without `re.escape` (plan-checker-qwen, nit) → not sent.
- Re-review nits, not sent: `lock("nope", "nope")` names the same path twice (plan-checker-glm), and the "`parameter_class` defaults to `qcodes.Parameter`" line in `ParameterGroup.add_parameter`'s docstring now describes only standalone groups (plan-checker-qwen; reviewer-qwen also noticed it).

### Questions to Marcos
- `unlock` on an already unlocked Lock and `relock` on an already locked one: raise, or do nothing? → Do nothing, but log at INFO level, so "the UI should be able to tell and do the right thing". Done in `c636f5c`.
- How should `add_parameter`/`remove_parameter` called directly on a Parameter Group behave (reviewer-qwen's held finding)? → Delegate to the root: groups hold a reference to the root Parameter Manager and route to it, and keep no Lock logic themselves (D15). Done in `3481f56`.

### Loose ends
- A group-level `remove_parameter` with `cleanup=True` now runs `remove_empty_submodules` on the root, so it also removes empty groups elsewhere in the tree (reviewer-qwen, noted, not a finding). This is the same as the root-level call, and empty groups hold no state.
- A Parameter Group attached to a manager by foreign code through a direct `add_submodule` keeps `_root = None` and skips routing (reviewer-glm; not reachable over the wire). reviewer-glm suggested a line in TEST_AUDIT.md. The orchestrator had also said to note the plain-`Parameter` case for TEST_AUDIT/1.3, but nothing for 1.2 is in `TEST_AUDIT.md` or `orchestration/RUNS.md` yet.
- The unused `full_name` accumulator in `_get_parent`, already noted after 0.1, is still there (reviewer-glm).
- For 1.3: `list_locks()` returns `Dict[str, PMLockBluePrint]`, and reviewer-glm found that `bluePrintToDict` already recurses into dict values, so the wire round-trip looks supported.

### Process notes
- The coder's `ask` timed out on its side before Marcos's answer came back, so it built the behaviour Marcos then overruled, which cost the pre-review fix round.
- While moving the coder's permission-dialog selection, the orchestrator sent Shift+Tab, which is opencode's agent switcher, and the coder terminal switched to the "Build" agent, which has no deny rules. The turn that was running kept running as Coder. The orchestrator pressed Tab to switch back and checked the bottom bar before the next dispatch. The first Enter on that dialog had also opened an "Always allow" confirm, which was cancelled; the prompt helper should send left-arrows before Enter.
- Two rejected permission requests in round 0: reviewer-qwen asked for `/tmp` and reviewer-glm tried to write a scratch file to opencode's temp dir. Both were told to use `orchestration/1.2/`, and they ran and deleted their scratch scripts there in both rounds.

## 1.3 `pm-lock-update` and proxy round-trip — 2026-09-24

Every `ParameterManager` Lock method that changes a Lock now emits one `pm-lock-update` Broadcast per affected Follower (D10) through the new private helper `_broadcast_lock_update(follower_path, lock)`. `name` is the full Follower path, and `value` is a `PMLockBluePrint`, or `None` when the Lock was removed. `lock`, `unlock`, `relock` and `remove_lock` emit directly, and `toggle_lock` emits through `unlock`/`relock`. The `remove_parameter` cleanup emits one `None` per dropped Lock, locked or unlocked, before it deletes the Target. Read-only methods, failed validations and the INFO-logged no-op paths emit nothing. `test/pytest/test_pm_locks.py` grew from 48 to 63 tests: server-free sink tests on a `pm_with_sink` fixture, plus the four proxy tests the task names, which run on the `param_manager` fixture.

### Commit by commit
- `d5f0c63` The emissions, docstrings stating when each method emits, and 13 tests. The proxy tests are `test_every_lock_method_is_callable_through_the_proxy`, `test_get_lock_and_list_locks_deserialise_to_pm_lock_blueprint`, `test_locked_follower_answers_get_with_the_target_value_over_the_wire` (10 while locked, 20 after the Target is set over the wire, the own value 3 after `unlock`) and `test_subclient_receives_pm_lock_update_and_none_after_remove_lock`. The sink tests cover each method, `test_noop_unlock_and_relock_emit_nothing`, `test_failed_lock_validations_emit_nothing` and the two `remove_parameter` cases. The commit also made three changes the task text did not name. The orchestrator flagged them for the reviewers, and all six judged them in scope:
  - `ParameterBroadcastBluePrint.value` is widened from `int | None` to `Any | None`, so it can carry a `PMLockBluePrint`. This settles the 1.1 loose end.
  - `dict_to_serialized_dict` in `blueprints.py` gained a `BluePrintType` branch. Without it, the dict of blueprints that `list_locks` returns went over the wire as `str(value)` and could not be rebuilt. test-reviewer-glm confirmed that the `list_locks` isinstance assertion depends on this branch.
  - `capture_broadcasts` / `wait_for_broadcasts` moved into `conftest.py` as session fixtures, and `test_broadcaster.py` and `test_param_manager.py` now use them. This is the third-copy move planned after 0.3 and 0.4.
  Orchestrator run: 87 passed in the three named files, 236 in the full suite.
- `d1a4332` Fix from round 0, four items:
  - Two ruff `I001` import-order errors, in `params.py` and `test_pm_locks.py`. reviewer-glm caught them (should-fix) by checking that the base was ruff-clean. The coder had reported "ruff clean", and the orchestrator confirmed that claim was wrong.
  - `unlock` and `relock` broadcast the stored `PMLockBluePrint` itself, so a sink that kept payloads saw earlier ones change on the next toggle. reviewer-glm caught this too (should-fix). Both methods now broadcast a fresh copy. The coder did the same for `lock()`, which had the same aliasing, and said so in the commit. New test: `test_broadcast_payloads_are_independent_of_the_stored_lock`.
  - `test_re_targeting_a_lock_emits_one_pm_lock_update_with_the_new_target`. Both test reviewers raised this as a nit, and it was sent because a fix round was happening anyway.
  - `test_failed_lock_validations_emit_nothing` gained failed `relock` / `toggle_lock` calls on a parameter with no Lock, and a refused cycle `relock` on a hand-wired chain. An `unlock` comes first, so the already-locked no-op cannot swallow the raise. Both test reviewers raised this as a nit. The coder replaced the existing `remove_lock("q02.y")` case with a `relock` case instead of adding to it.
  Orchestrator run: ruff clean, 89 in the named files, 238 in the full suite.
- `7ff0d71` Fix from round 1: puts the `pm.remove_lock("q02.y")` raise back into `test_failed_lock_validations_emit_nothing` (2 lines). test-reviewer-glm caught the regression (should-fix): after `d1a4332`, no test anywhere checked that a failed `remove_lock` emits nothing. All six reviewers approved in re-review, and test-reviewer-glm confirmed its finding fixed. Orchestrator run: 63 in `test_pm_locks.py`, 89 in the named files, 238 in the full suite.

### Dropped findings
- The Lock API comment block's sentence "Broadcasts that only report state are emitted after the change" is muddled (reviewer-glm, nit) → not sent. It is still in `params.py`.
- `value: Any | None` is a redundant union (reviewer-qwen, nit) → not sent, style only.
- In `test_broadcast_payloads_are_independent_of_the_stored_lock`, the `!=` assertion adds nothing beyond the two `is` assertions above it (test-reviewer-qwen, round 1 nit) → not sent. The fix list had asked for that line word for word.

### Questions to Marcos
- Should the INFO-logged no-op paths of `unlock`/`relock` emit `pm-lock-update`? The coder asked this before writing the code. The orchestrator answered from D10: no, since "one per affected Follower" and a no-op affects no Follower, so "emitted by every Lock method" means every method that changes a Lock. A test was required (`test_noop_unlock_and_relock_emit_nothing`). The orchestrator flagged the reading for Marcos in the run report, and plan-checker-glm asked for D10's wording to be read as amended by it. No answer from Marcos is recorded yet.

### Loose ends
- Dict-valued responses such as `list_locks` still go over the wire as `str(dict)` plus the quote handling in `ServerResponse.__init__`. That works for lab paths but would break if a value ever contained a quote (reviewer-qwen). This was already the case before 1.3. reviewer-qwen suggested an entry in `TEST_AUDIT.md`, but none is there yet.
- `ModelParameters.updateParameter` in the GUI ignores the new `pm-lock-update` action without error until task 5.1 (reviewer-glm, reviewer-qwen).
- Only `lock` and `remove_lock` are tested with a `SubClient` over the wire. The `unlock`/`relock`/`toggle_lock` and `remove_parameter` emissions are covered by the sink tests only (test-reviewer-glm; this matches the task text). A group-level `pm.q01.remove_parameter(...)` emission is not asserted either, although it routes through the same root method.
- The 1.2 suggestions to add a depth-2 Lock and an unknown-path `remove_parameter` check to 1.3's tests were not taken up.

### Process notes
- The coder tried to write a scratch file to opencode's temp dir outside the repo. It was rejected, and the coder used `orchestration/1.3/` and deleted the file afterwards.
- plan-checker-glm sent worker_done twice in round 0. Orca rejected the second one.
- No stalls or nudges were needed in any round.

## 2.1 Type registry and definitions — 2026-09-24

The root `ParameterManager` now has a Type registry, `self._types`, which maps each Type name to a `_TypeDefinition(name, parameters, nested)`. Entries are `_TypeEntry(default, unit, target)`, and Parameter Groups hold no Types (D15). The Type API is `add_type` (refuses `_globals` and duplicates), `remove_type` (refuses while any Type nests it, naming every nester), `list_types` (returns `List[str]`) and `get_type`. `get_type` returns the new `PMTypeBluePrint(name, parameters, nested, effective)` from `blueprints.py`, which is also in the `BluePrintType` union. `_effective_parameters` builds the effective set as `{path: {unit, from_type}}`. `_nested_cycle` runs first and refuses a cycle, naming the chain; it refuses a missing Nested Type too. `_collect_effective` then expands the Nested Types under their submodule names and collects every duplicated path into a single error. No Type method emits a Broadcast yet (that comes in 2.5). The new `test/pytest/test_pm_types.py` has 21 server-free unit tests.

### Commit by commit
- `83afee7` The dataclasses, the registry, the Type API, the effective-set helpers and 19 tests. `add_nested_type` belongs to 2.3, so the orchestrator's scope note said to raise on cycles from `_effective_parameters` and to build Nested Types in tests by putting `_TypeDefinition`s straight into `pm._types` (the `put_type` helper). The tests cover the definitions, three-tier expansion from the mock and its middle tier, and `test_the_same_type_nested_twice_is_not_a_cycle`. They also cover the refusals for a two-Type cycle, a self-nest, a missing Nested Type and one or two duplicated paths, plus full blueprint equality and a `toJson` → `deserialize_obj` round-trip. The coder found that the public methods need quoted return annotations: with `PMTypeBluePrint` unquoted, proxy method generation broke 8 tests in its own run. This is the 0.2 rule again. Orchestrator run: ruff clean, 19 passed in `test_pm_types.py`, 257 in the full suite.
- `3c275d2` Fix from round 0, three items:
  - `test_the_type_registry_lives_on_the_root_only`: after `pm.add_parameter("q01.IF")`, `pm.q01` has no `_types` and no `add_type`. Both test reviewers caught it (should-fix): no test touched a Parameter Group, so moving the registry there would have failed nothing.
  - `test_remove_type_removes_a_type_that_nests_other_types`: removing `qubit`, which nests `readout`, succeeds and leaves `readout` untouched. test-reviewer-glm caught it (should-fix), and the orchestrator confirmed that only the refusal direction was tested.
  - A `gap` row in `TEST_AUDIT.md`: `bluePrintToDict` stringifies scalar leaves and `deserialize_obj` parses them back as numbers, so a string `default` of `"10"` comes back through a proxy `get_type` as the int `10`. This was already true before 2.1 and affects every blueprint payload. reviewer-glm (nit) and reviewer-qwen (observation) raised it, and it went to the audit under plan rule 6 with no code change.
  All six reviewers approved in re-review, and both test reviewers confirmed their items fixed. Orchestrator run: ruff clean, 21 in `test_pm_types.py`, 259 in the full suite.

### Dropped findings
- `remove_type` counts a Type that nests itself as its own nester, so it can never be removed. The task says "any *other* Type" (reviewer-glm, test-reviewer-qwen, plan-checker-glm, plan-checker-qwen, all nits) → not sent. The state can only be built by hand until 2.3's `add_nested_type`, which refuses cycles. The orchestrator flagged it for the 2.3 spec to decide.
- `_collect_effective` lists a path that appears three or more times twice in the error message (plan-checker-glm, nit) → not sent, cosmetic.

### Loose ends
- For 2.3: settle the self-nesting `remove_type` case above and pin it in a test. `add_nested_type` must also do the cycle check the plan asks for; for now only `_effective_parameters` checks.
- `get_type` returns fresh dicts, so the blueprint cannot alias the registry, but only by construction: no test checks it (test-reviewer-qwen, observation).

### Process notes
- The orchestrator's watcher missed the six reviewers' ruff permission prompts for about 10 minutes in round 0. A prompt sweep was added to each wait cycle.
- Piping `uv run pytest | tail` from the orchestrator's session hung. Running the suite detached, with output to a log file, works.
- reviewer-qwen ran its full-suite runs in the background, logging to `orchestration/2.1/`, and deleted its logs afterwards in both rounds. There were no rejected permissions and no stalls.

## 2.2 Instance matching — 2026-09-24

`ParameterManager` in `src/instrumentserver/params.py` now answers the two D12/D16 matching queries. `instances_of(type_name)` returns the paths of every Parameter Group, at any depth, that carries every path of the Type's effective set with the declared unit. Values don't matter, the root is never an Instance, `_globals` and everything under it are skipped, and an empty Type has no Instances. `types_of(path)` returns the Types claiming a parameter, innermost first. A Type claims the parameter when one of its Instances sits above it and the parameter's path relative to that Instance is in the effective set. Matching is duck-typed and walks the tree on every query through the private helpers `_iter_submodule_groups`, `_carries_effective_set` and `_instances_of_effective`. Both queries change no state and emit no Broadcast. `test/pytest/test_pm_types.py` grew from 21 to 38 server-free tests.

### Commit by commit
- `6d1560b` The two queries, their helpers and 16 tests. The plan left some behaviour open, so the orchestrator wrote its reading into the coder spec: `types_of` takes a parameter path (the mock's `claims()` works per row), a remaining tie after depth and size is broken by Type name, and an unknown Type or path raises `ValueError` naming it. The coder added two readings of its own. `_globals` is skipped by name at any depth, not only at the root, and a Type that claims a parameter through two Instances is listed once, placed by its innermost Instance. Depth is `len(submodule_path)`. The string length ranks depth correctly because every claiming Instance is a dotted prefix of the parameter path. The tests cover the plan's five cases: the three-tier mock (`test_instances_of_finds_the_three_tier_instances`, `test_types_of_orders_innermost_first`), `test_a_unit_mismatch_excludes_the_submodule`, `test_extra_parameters_do_not_matter`, `test_two_types_on_one_submodule` and `test_q01_readout_is_an_instance_of_readout_on_its_own`. The other tests cover these cases:
  - a mismatch at one level leaving a deeper Instance
  - the Type-name tie-break
  - the root
  - `_globals` at two depths, with parameters built by the `put_globals_parameter` helper through `_add_own_parameter`
  - values being irrelevant
  - one Type nested at two submodules
  - the error paths, including a Parameter Group path given to `types_of`
  - an unclaimed parameter
  
  Orchestrator run: ruff clean, 37 passed in `test_pm_types.py`, 275 in the full suite.
- `ef1f2cf` Fix from round 0, test only: `test_a_type_claiming_through_two_instances_is_ordered_by_its_innermost_instance`. The test sets up Type `zzz = {x, a.x}` and Type `aaa = {a.x, top}`, with parameters at `a.x`, `a.top`, `a.a.x` and `a.a.a.x`. `zzz` has Instances at `a` and `a.a`, and `types_of("a.a.x")` must return `["zzz", "aaa"]`. If the `depth > known[0]` dedup ever falls back to keeping the first claim it sees, the Type-name tie-break puts `aaa` first. All four general and test reviewers raised this gap (should-fix). The `known is None or depth > known[0]` branch could be broken and every test would still pass. The fix list used test-reviewer-glm's scenario. The coder briefly flipped the branch locally to show the test catches the regression, then reverted it before committing. Two re-reviewers ran the same check in scratch scripts. All six approved in re-review, and all four who raised the item confirmed it fixed. Orchestrator run: ruff clean, 38 in `test_pm_types.py`, 276 in the full suite.

### Dropped findings
- The unit check is strict. A parameter created without a unit has `unit=None`, so it never matches a Type entry whose unit is `""` (plan-checker-qwen, nit) → not sent. The plan says nothing about this case. It matters for the unit propagation in 2.3 and the unit-conflict scan in 2.4 (see Questions).
- A user-made `q01._globals` group is excluded too, which goes beyond the root-level Globals the glossary defines (plan-checker-qwen, nit). No test covers the nested case (test-reviewer-glm, nit) → not sent. ADR-0001 says `_globals` is "excluded from matching at any depth", so the coder's reading stands, and 3.1 checks the exclusion again.
- The comment doesn't explain why `len(submodule_path)` is a safe measure of depth (reviewer-glm, nit), and the `types_of` docstring doesn't mention the cycle and duplicate errors it inherits from `_effective_parameters` (reviewer-qwen, nit) → not sent.
- Two tests wrap `instances_of` in `sorted()` although the docstring promises tree order (test-reviewer-qwen, nit) → not sent, because the plan fixes no order. The 5.5 instances pane may want the order pinned.
- `put_globals_parameter` creates plain `Parameter`s and its docstring cites a 3.1 refusal that doesn't exist yet (test-reviewer-qwen, nit). No test checks that cycle and duplicate errors pass through `instances_of` (test-reviewer-glm, nit) → not sent. The second state can't be reached once 2.3's `add_nested_type` refuses cycles.

### Questions to Marcos
- The orchestrator flagged these readings for the run report: `types_of` takes a parameter path; a remaining tie is broken by Type name; unknown names raise; `_globals` is excluded at any depth; a `None` unit doesn't match a declared `""`. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 2.3/2.4: decide whether a parameter with no unit counts as carrying `""` (see above). For now `_carries_effective_set` compares `param.unit` to the declared unit exactly.
- `types_of` recomputes every Type's effective set and Instances on each call. That is what ADR-0001 asks for (no cache), but the cost grows with the number of Types times the tree size.
- No proxy tests for `instances_of`/`types_of` yet; they belong to 2.5.

### Process notes
- Reviewers checked their findings with scratch scripts in `orchestration/2.2/` in both rounds. The orchestrator read each script before allowing it to run, and the reviewers deleted them afterwards. One scratch tempdir left under `round-0/` was removed by the orchestrator. There were no rejected permissions, no stalls and no nudges.
