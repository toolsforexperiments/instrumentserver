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

## 2.3 Type edits with Instance side effects — 2026-09-24

`ParameterManager` now has the six D16 Type edits: `add_type_parameter`, `remove_type_parameter`, `set_type_parameter_default`, `set_type_parameter_unit`, `add_nested_type` and `remove_nested_type`. Each one validates everything before it touches the registry or the tree. The side effects follow D13 and key off the Instances that exist before the edit (`_instances_before_edit`), both the edited Type's and those of every Type nesting it (`_nesting_prefixes`). Missing parameters are created once each through the root's `add_parameter`, with the entry's default and unit, and a parameter already at a target path is left alone. `_check_creation_targets` refuses targets that cannot be created. `_effective_parameters` now sits on the new `_expand_effective`/`_effective_entries`, which also carry the full `_TypeEntry` and the defining Type. The edits emit no Broadcast yet (2.5), and `_TypeEntry.target` stays `None` (Phase 3). `test/pytest/test_pm_types.py` grew from 38 to 75 server-free tests. They include one effect test per D13 row and `test_a_failed_validation_leaves_the_tree_and_registry_byte_identical`, which compares `list()`, every value and unit, and a deep copy of `_types` around each failing call.

### Commit by commit
- `6724148` The six methods, their helpers and 29 tests. The orchestrator wrote nine readings into the coder spec for points the plan leaves open:
  - side effects target the Instances found before the edit, including those of outer Types
  - an existing parameter is never overwritten
  - `remove_type_parameter` and the two `set_type_parameter_*` methods act on the Type's own entries only, and a path reached only through a Nested Type raises, naming the Type that defines it
  - `add_nested_type` refuses cycles (checked with `_nested_cycle` on a copied registry), an occupied submodule, `_globals` as the first submodule segment, and a duplicated path in the effective set of the Type or of any Type nesting it
  - no Broadcasts and no Target handling

  With cycles refused, the 2.1 self-nesting `remove_type` case can no longer be built through the API. `test_add_nested_type_refuses_a_self_nesting` pins that. The coder added three readings of its own: an empty entry path or empty segment is refused, a target whose final segment is an existing Parameter Group is refused, and dotted submodule names are accepted. All six reviewers judged these in scope. The 2.1/2.2 tests now build their Types through the public API. `put_type` is kept only for states the API refuses to build. Orchestrator run: ruff clean, 67 in `test_pm_types.py`, 305 in the full suite.
- `bd4b457` Fix from round 0, seven items:
  - `add_nested_type` could raise half-way through. When the Nested Type's effective set held a path and a dotted extension of it (`b` and `b.c`, buildable while the Type has no Instances), each target passed the pre-check on its own. The registry was written, `q01.s.b` was created, and then `q01.s.b.c` failed. plan-checker-glm and reviewer-glm both reproduced it (must-fix). `_check_creation_targets` now refuses a target that is a strict segment-prefix of another target of the same edit, and names both. The fix list also allowed refusing this shape when the Type is defined. The coder did not do that, because the fix list's own test scenario needs `{b, b.c}` to be buildable. New test: `test_add_nested_type_refuses_conflicting_creation_targets`.
  - `add_type_parameter` checked the new path only against the edited Type's own effective set. If `qubit` nests the empty `readout` and owns `readout.window`, then `add_type_parameter("readout", "window")` succeeded, and every later `qubit` query raised the duplicated-path error. plan-checker-glm raised this (must-fix) and the orchestrator confirmed it in the code. The method now refuses `prefix + path` already in any nesting Type's effective set. New test: `test_add_type_parameter_refuses_a_path_that_collides_in_a_nesting_type`.
  - Five test-only pins:
    - `test_add_nested_type_refuses_a_target_blocked_by_a_parameter_group`: test-reviewer-glm, who showed by mutation that turning off the check left the suite green
    - `test_add_nested_type_accepts_a_dotted_submodule_name`: both test reviewers
    - `test_add_nested_type_refuses_a_submodule_name_with_empty_segments`: test-reviewer-glm and plan-checker-qwen
    - `test_add_nested_type_builds_the_three_tier_case`: test-reviewer-qwen
    - `test_add_nested_type_leaves_an_existing_parameter_at_the_target_alone`: reviewer-qwen

    The byte-identical test gained five failing calls. The coder briefly turned off `_check_creation_targets` locally to show that a test catches it. The orchestrator checked that the commit left no trace of this.

  Orchestrator run: ruff clean, 74 in `test_pm_types.py`, 312 in the full suite.
- `bcaaa77` Fix from round 1: the nester check added in `bd4b457` raised on the first collision, so it named only one nester or one path. Plan rule 3 asks for all of them. Four reviewers in three roles caught it (plan-checker-glm, plan-checker-qwen, reviewer-qwen, test-reviewer-qwen). The round-0 fix list had asked for the singular ("naming the nester and the path"), and the orchestrator ruled that the plan rule wins. The check now collects every `(path, nester)` pair and raises once, in the same format `add_nested_type` uses. New test: `test_add_type_parameter_names_every_nesting_type_collision` (one nester nesting the edited Type at `a` and `b`). The byte-identical test's `holder` setup was widened to two submodules. In re-review all six approved, and all four raisers confirmed the fix. Orchestrator run: ruff clean, 75 in `test_pm_types.py`, 313 in the full suite.

### Dropped findings
- `_instances_before_edit` takes the Type → prefixes map but uses only its keys. The `new_path in new_paths` half of `add_nested_type`'s collision check can never be true. The `created` sets have a bare `set` annotation (reviewer-qwen, nits) → not sent.
- The `elif shorter.startswith(...)` branch of `bd4b457`'s prefix check can never run, because the paths are sorted (reviewer-qwen, plan-checker-qwen, nits; plan-checker-glm noted it too) → not sent. It is still in `_check_creation_targets`.
- No `isinstance(..., ManagedParameter)` assertion on the created parameters, and no test that the edits emit nothing (test-reviewer-glm, nits) → not sent; 2.5 tests the emissions.
- No per-method test that `remove_type_parameter` and the two `set_type_parameter_*` methods refuse an unknown Type (plan-checker-qwen, nit) → not sent. They share `_require_type`, which is already pinned.
- No dedicated test for two different nesters colliding on the same path (test-reviewer-qwen, round 2 nit) → not sent. The fix list allowed either case, the coder chose one nester at two submodules, and the code path is the same.

### Questions to Marcos
- The orchestrator flagged the nine coder-spec readings for the run report. It also flagged that a Type whose effective set holds both `b` and `b.c` can still be built while it has no Instances, and can never match. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 3.1: a Type entry path may contain a `_globals` segment (`add_type_parameter("qubit", "_globals.x")` is accepted), and a non-first `_globals` segment in a submodule name is accepted too. D12/D18 do not say whether this is allowed (plan-checker-qwen, reviewer-qwen). Side effects go through `add_parameter`, so 3.1's refusal there will reach them, but `add_type_parameter`'s own validation should match it.
- A `{b, b.c}` Type stays in the registry without harm: every edit that would write it into the tree is now refused before it changes anything (reviewer-glm).
- For `set_type_parameter_unit`, reaching the outer Types' Instances changes nothing that can be seen: every such Instance already contains an Instance of the nested Type. test-reviewer-glm recorded this so that nobody counts it as coverage.
- The 2.2 question of whether a parameter without a unit (`None`) carries a declared `""` is still open. 2.3 creates side-effect parameters with the entry's unit, `""` by default.
- Nothing from 2.3 is in `TEST_AUDIT.md`.

### Process notes
- The coder went idle after about 6 minutes of thinking, with no edits and no worker_done. The orchestrator nudged it to continue.
- In round 1, all five reviewers still running stopped with "Cannot connect to API" during a short Lumen outage. The orchestrator nudged each of them to resume.
- test-reviewer-qwen asked for `/tmp` in round 0. This was rejected, and it was told to use `orchestration/2.3/`. Reviewers used scratch scripts under `orchestration/2.3/` in every round, and each was checked for writes before it ran and deleted afterwards. reviewer-qwen made several read-only `python -c` qcodes lookups, which its role file advises against.

## 2.4 `add_instance` — 2026-09-24

`ParameterManager.add_instance(type_name, name)` writes a Type's effective set into the Parameter Group `name` (D14). `name` is a dotted submodule path relative to the Parameter Manager, so nested Instances such as `q02.ro` work, and the Parameter Groups on the way are created. Everything is validated before anything is created. The Type must exist. An empty name, an empty segment, or `_globals` as the first segment is refused, naming the offending name. The unit-conflict scan runs over every effective path and raises once, naming each existing parameter whose unit differs from the declared one, with both units. Last, `_check_creation_targets` checks for blocked targets. Missing entries are then created with the entry's default and unit through `add_parameter`, so they are `ManagedParameter`s. Existing parameters keep their value and unit. An empty Type creates nothing, not even the submodule, but the name refusals still run first. The method returns `None` and emits no Broadcast (2.5). `test/pytest/test_pm_types.py` grew from 75 to 90 server-free tests.

### Commit by commit
- `23b42e2` `add_instance` and 13 tests. The orchestrator's five readings in the coder spec covered the name rules, validation before any creation (reusing 2.3's `_check_creation_targets`), creation through `add_parameter`, an empty Type creating nothing, and returning `None`. 2.3 only passed Instance paths that already exist, so the coder reworked `_check_creation_targets` to walk the Instance path itself. A segment that is an existing parameter now blocks every target below it and is named. A missing Parameter Group stops the check, because it will be created on the way and nothing below it can clash. The now-unused `_group_at` was deleted. All six reviewers checked that for 2.3's callers the new walk ends at the same group `_group_at` returned, so 2.3's behaviour is unchanged. The tests cover these cases:
  - creation with defaults and units (`ManagedParameter`, full `path`, then listed by `instances_of`)
  - keeping an existing entry
  - a dotted name
  - the three-tier mock matching at all three tiers (`test_add_instance_builds_the_three_tier_case`)
  - a unit conflict on two paths
  - a target blocked by a parameter, a name blocked by a root parameter, and a target taken by a Parameter Group
  - the `b`/`b.c` conflicting targets
  - `_globals`, empty segments, an unknown Type and an empty Type

  Nine `add_instance` refusals were added to `test_a_failed_validation_leaves_the_tree_and_registry_byte_identical`. Orchestrator run: ruff clean, 88 in `test_pm_types.py`, 326 in the full suite.
- `97fb5a4` Fix from round 0, test only, two items:
  - `test_add_instance_refuses_the_globals_submodule_on_an_empty_type`: nothing pinned that the `_globals` refusal fires before the empty-Type early return. If the `if not effective: return` moved up, `add_instance("empty", "_globals")` would pass silently. Both test reviewers caught it (should-fix), and so did reviewer-glm (nit). Following test-reviewer-glm's nit, both this test and `test_add_instance_refuses_the_globals_submodule` now pin the offending name in the message, not only the reason.
  - `test_add_instance_refuses_a_unit_conflict_on_a_nested_effective_path`: the scan had only been tested on top-level paths. The new test puts `q01.readout.IF` at unit `V` against the three-tier `qubit` and expects the full dotted path in the message, with nothing created. test-reviewer-qwen (should-fix) and reviewer-glm (nit) caught it.

  All six approved in re-review, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 90 in `test_pm_types.py`, 328 in the full suite.

### Dropped findings
- The docstring says a successful call makes `name` an Instance "unless the Type is empty". That is also false for a name with a non-first `_globals` segment: `add_instance("qubit", "q01._globals")` creates the parameters, but matching skips the name (reviewer-glm, nit) → not sent, left for 3.1.
- Docstring wording: `_check_creation_targets` says `add_instance` "names" missing Parameter Groups, which it does not. `add_instance` says a name "starts with" `_globals` when the code compares the first segment (reviewer-qwen, nits; plan-checker-qwen noted the same) → not sent. Both wordings are still in `params.py`.
- No test calls `add_instance` twice on the same name (test-reviewer-glm, nit) → not sent.
- The empty-segment refusal is not pinned on an empty Type (test-reviewer-glm, round 1 nit). The fix list kept only the `_globals` half of their round-0 item → not sent. They suggest adding `pm.add_instance("empty", "")` next time the file is touched.

### Questions to Marcos
- The orchestrator flagged its five coder-spec readings for the run report. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 3.1: a `_globals` segment after the first is accepted in `add_instance` names, as it already is in 2.3's `add_nested_type`.
- The 2.2 question of whether a parameter with no unit (`None`) carries a declared `""` now reaches the unit-conflict scan too, which compares `existing_unit != entry.unit` exactly. The reviewers disagree on what happens. test-reviewer-glm, test-reviewer-qwen and both plan checkers read the code as treating `None` against `""` as a conflict. reviewer-glm ran a probe and reported that qcodes turns a missing unit into `""`, so the case would not come up. The commits do not settle this and no test pins it.
- No test pins a call that mixes a matching-unit parameter and a conflicting one. reviewer-qwen checked it with a probe.
- Nothing from 2.4 is in `TEST_AUDIT.md`.

### Process notes
- At the end of implementation the coder tried `rm -rf orchestration/2.4`. It was rejected because the orchestrator's files live there, and the coder was told to leave the folder.
- Reviewers checked their findings with scratch scripts under `orchestration/2.4/`. Each was scanned before it ran and deleted afterwards. plan-checker-glm ran the full suite detached to a log file in both rounds, because piping it hangs (see 2.1). Neither log is left in the folder. There were no stalls and no nudges.

## 2.5 `pm-type-update` and side-effect broadcasts — 2026-09-24

The Type API in `src/instrumentserver/params.py` now emits its own Broadcasts (D22, ADR-0003). All eight Type-editing methods (`add_type`, `remove_type` and the six 2.3 edits) emit `pm-type-update` through the new `_broadcast_type_update`, with the Type's fresh `PMTypeBluePrint`. An edit that changes the effective set of outer Types emits one update per affected Type, the edited one first, then each nester in `_nesting_prefixes` order. `remove_type` emits one update with a `None` payload. Every parameter that `add_type_parameter`, `add_nested_type` or `add_instance` actually creates emits a `parameter-creation` through `_broadcast_parameter_creation`, whose payload mirrors the Server's `_newOrDeleteParameterDetection`. Kept parameters and direct `add_parameter` calls emit nothing, and neither do refused calls or the read-only queries. `test/pytest/test_pm_types.py` grew from 90 to 111 tests: server-free sink tests on a `pm_with_sink` fixture, and four proxy tests that follow `test_pm_locks.py`.

### Commit by commit
- `9de2239` The emissions and 18 tests (14 sink, 4 proxy). The orchestrator's eight readings in the coder spec set these rules:
  - which methods emit (the Phase 3 `lock_type_parameter`/`unlock_type_parameter` don't exist yet)
  - outer Types get their own update
  - `add_instance` emits only `parameter-creation`s
  - payload shapes mirror 1.3 and the Server
  - creations go first, in creation order, then the Type updates, all after the whole mutation
  - refused calls emit nothing
  - `set_type_parameter_unit`'s propagation emits no value Broadcast

  The coder added two readings of its own. `set_type_parameter_default` emits for the edited Type only, because `effective` carries unit and `from_type` but no defaults, so no outer blueprint changes. Creations are collected during the loop and broadcast after it. All six reviewers judged both readings as fitting the plan. The sink tests include one per method, plus these:
  - `test_add_instance_emits_one_creation_per_created_parameter`
  - `test_add_instance_emits_nothing_for_kept_parameters`
  - `test_read_only_type_queries_emit_nothing`
  - `test_failed_type_validations_emit_nothing`, which runs about 19 refusals and, with two direct `add_parameter` calls under the sink, also pins the plan's "none for direct `add_parameter`"
  - `test_type_broadcast_payloads_are_snapshots_of_their_time`

  The four proxy tests are the plan's list:
  - `test_every_type_method_is_callable_through_the_proxy` (all 13 D16 methods, `instances_of`/`types_of` included)
  - `test_get_type_and_list_types_deserialise_over_the_wire`
  - `test_subclient_sees_pm_type_update_and_creations_from_a_second_client`
  - `test_the_first_clients_proxy_shows_the_created_parameters_after_update`

  Orchestrator run: ruff clean, 108 in `test_pm_types.py`, 346 in the full suite.
- `80635c3` Fix from round 0, test only, three tests:
  - `test_pm_type_update_reaches_every_type_of_a_three_tier_nesting_chain`: every sink test nested only one level (`put_nested_instance`), so a `_nesting_prefixes` walk that stopped at direct nesters would have passed the suite and left the outermost Type's blueprint stale on every GUI. The test uses `put_three_tier_registry` and `add_type_parameter("pulse_window", "amp", ...)`, then expects exactly three updates in the order `pulse_window`, `readout`, `qubit`, with `readout.pw.amp` in `qubit`'s `effective`. Both test reviewers caught it (should-fix).
  - `test_add_type_parameter_emits_no_creation_for_kept_parameters` and `test_add_nested_type_emits_no_creation_for_kept_parameters`: the kept-parameter rule had a sink test only for `add_instance`, not for the two 2.3 creation loops. Both general reviewers raised it as a nit. The orchestrator sent it anyway, because both models of one role raised it, the test was cheap and a fix round was happening regardless.

  The coder backed up `params.py` under `orchestration/2.5/`, applied two temporary mutations to show that the new tests fail, and restored the file. The orchestrator and three reviewers checked that `git diff 9de2239..80635c3 -- src/` is empty. All six approved in re-review with no findings, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 111 in `test_pm_types.py`, 349 in the full suite.

### Dropped findings
- The wire-level `add_instance` test creates only one parameter, so "one `parameter-creation` per created parameter" is shown over the wire only for n=1 (test-reviewer-glm, nit). The only multi-creation sink test creates `q01.IF` then `q01.octave_gain`, which is also alphabetical order, so a loop that sorted paths would still pass (test-reviewer-qwen, nit) → not sent. Multiplicity and order rest on the sink tests.
- `remove_type` builds its `None` broadcast inline, because `_broadcast_type_update` calls `get_type` on the Type that was just deleted (reviewer-glm, nit). Both type-update sites spell the name as `f"{self.name}.{type_name}"` instead of `_full_path` (reviewer-qwen, nit) → not sent. The strings are identical.
- The creation-broadcast loop appears three times. The refused-call battery lacks the `_check_creation_targets` refusals (plan-checker-glm, nits). The `ParameterManager` class docstring leaves out the `None` payload and "per affected Type". A proxy-test comment says "propagated unit" where no Instance existed yet (plan-checker-qwen, nits) → not sent. All four are still in the code.

### Questions to Marcos
- The orchestrator flagged its eight coder-spec readings for the run report. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- The 2.2 loose end on proxy coverage of `instances_of`/`types_of` is closed by `test_every_type_method_is_callable_through_the_proxy`. The 2.1 loose end on `get_type` aliasing is now partly pinned by `test_type_broadcast_payloads_are_snapshots_of_their_time`.
- For 3.2: `lock_type_parameter`/`unlock_type_parameter` must emit `pm-type-update` too (D22).
- The wire tests' negative counts (`len(received) == 1` right after `wait_for_broadcasts`) could in principle race a late Broadcast, as in `test_pm_locks.py`. The strong forms of those claims live in the sink tests (test-reviewer-glm, observation).
- Nothing from 2.5 is in `TEST_AUDIT.md`.

### Process notes
- reviewer-qwen's `git -C` commands with a line-wrapped path slipped past the whitelist several times and needed manual approval. They were read-only and all were allowed. Its scratch script under `orchestration/2.5/` was re-scanned before each of its three runs and deleted afterwards. Reviewers and the coder ran the suite to log files in the folder and removed them. There were no rejected permissions, no stalls and no nudges.

## 3.1 `_globals` rules — 2026-09-24

`ParameterManager.add_parameter` now refuses, with a `ValueError` naming the path and creating nothing, any name that is `_globals` or starts with `_globals.` (D18). Parameter Groups route `add_parameter` to the root, so the refusal covers `pm._globals.add_parameter(...)` style calls too. The new private `_ensure_global_target(type_name, path)` creates `_globals.<type_name>.<path>` on demand for one of the Type's own entries. It creates it as a `ManagedParameter` with the entry's default and unit and a full-form `path`, emits one `parameter-creation`, and returns the relative path. An existing parameter is kept with its value and emits nothing. Nothing public calls it yet (3.2 will). `add_instance`'s 2.4 refusal and 2.2's matching exclusion are asserted again. `test/pytest/test_pm_types.py` grew from 111 to 124 tests: twelve unit tests and one proxy test.

### Commit by commit
- `8daf195` The refusal, the helper and 13 tests. The orchestrator's six readings in the coder spec set these rules:
  - "under `_globals`" means the first dotted segment, and a `_globals` segment after the first stays allowed (not widened)
  - the refusal lives on the root `add_parameter`
  - the helper acts on the Type's own entries only (a path reached only through a Nested Type raises, naming the defining Type, as in `set_type_parameter_default`)
  - it is idempotent and refuses a unit conflict on an existing Globals parameter, naming the path and both units
  - it bypasses the public refusal through `_get_parent(..., create_parent=True)` + `_add_own_parameter`
  - it emits one `parameter-creation` when it creates and no `pm-type-update`

  The coder added one reading of its own: a target path that is an existing Parameter Group is refused too. Every refusal test also checks that `list()` is unchanged. The tests include:
  - `test_add_parameter_refusal_covers_the_parameter_group_routing`
  - `test_add_instance_still_refuses_the_globals_submodule`
  - `test_globals_parameters_stay_excluded_from_matching`, which builds a full Instance shape at `_globals.qubit` and `_globals.deep.qubit`
  - `test_ensure_global_target_emits_one_creation_and_is_idempotent`
  - `test_a_globals_parameter_is_an_ordinary_parameter` (set, read, and a Lock Target)
  - `test_add_parameter_refusal_over_the_wire`, which catches a bare `Exception`, because the Client rebuilds a plain `Exception` from the Server's error message

  Orchestrator run: ruff clean, 124 in `test_pm_types.py`, 362 in the full suite.
- `175ff5a` Fix from round 0, two items:
  - `_ensure_global_target` had its own segment walk for a parameter on the way and a Parameter Group at the target. That repeated `_check_creation_targets` line for line. reviewer-qwen (should-fix) and reviewer-glm (nit) raised it. The walk is now `self._check_creation_targets([("_globals", f"{type_name}.{path}")])`. The two affected tests pass unchanged, because the helper only wraps the same reasons in "cannot create parameter '<path>': ...".
  - A `TEST_AUDIT.md` row, "Profiles — loading Globals parameters". `fromParamDict`/`fromFile` create missing parameters through the public `add_parameter`, so a profile with a `_globals.*` key now raises on load. reviewer-qwen reproduced it and reviewer-glm noted it. It is left for the Phase 4 reader (4.2) per plan rule 6.
- `402e53d` Fix from round 1, comment only. The new comment in `175ff5a` called the Globals target "an Instance at the reserved Globals submodule". That breaks D18 and plan rule 2. reviewer-qwen (should-fix) and both test reviewers (nit) caught it. The comment now says the target sits under the Globals submodule, "which is never an Instance (D18)", and that the `(Instance path, relative target)` pair is reused only for the walk. All six approved in re-review with no findings. Orchestrator run: ruff clean, 124 in `test_pm_types.py`, 362 in the full suite.

### Dropped findings
- Globals parameters are created without the `vals=Anything()` and `set_cmd=None` that the public `add_parameter` path gives (reviewer-glm, reviewer-qwen, nits) → not sent. Only the snapshot's `vals` meta differs, and nothing reads it. The orchestrator suggested folding both paths into one internal creation helper later.
- No positive test that a non-first `_globals` segment (`add_parameter("q01._globals.x")`) is still allowed (test-reviewer-qwen, nit) → not sent. A later task that widens the check will break no test.
- No test for a root parameter named `_globals` blocking the helper (reviewer-qwen, nit) → not sent. That case can now be built only through the internal path.
- The `add_parameter` docstring says a name "starts with it" where the code checks `startswith("_globals.")` (plan-checker-qwen, nit) → not sent. The wording is still in `params.py`.

### Questions to Marcos
- The orchestrator flagged its six coder-spec readings for the run report, especially keeping non-first `_globals` segments allowed. It also flagged the `vals` difference and the profile-load gap. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- The RUNS.md question for 3.1 is not settled. A `_globals` segment after the first is still accepted in `add_parameter` names, Type entry paths, `add_nested_type` submodule names and `add_instance` names, and matching then skips that submodule without saying so.
- For 4.2: the reader must create `_globals.*` parameters through the internal path (`TEST_AUDIT.md`, "Profiles — loading Globals parameters").
- For 3.2: `_ensure_global_target` is ready for the Type Lock declaration to call.

### Process notes
- Two permissions were rejected. In round 0, reviewer-qwen tried an inline `python -c` script that changed into a `tempfile.mkdtemp()` outside the repo. It reran its check as a scanned script under `orchestration/3.1/round-0/`. In round 1, plan-checker-qwen tried a command that wrote to `/tmp/x`. Reviewers' scratch scripts and logs under `orchestration/3.1/` were scanned before they ran and deleted afterwards. There were no stalls and no nudges.

## 3.2 `lock_type_parameter` / `unlock_type_parameter` — 2026-09-25

`ParameterManager.lock_type_parameter(type_name, path, target=None)` declares a Type Lock on one of the Type's own entries (D17). It stores the Target on `_TypeEntry.target` in full form (`parameter_manager._globals.qubit.IF`), which `PMTypeBluePrint.parameters[path]["target"]` now shows. With no `target` it creates the default Globals Target through 3.1's `_ensure_global_target`. It then puts an ordinary locked Lock on that parameter in every current Instance through `lock()`/`relock()`. Instance parameters with a Lock on another Target are skipped, named in one `logger.warning` and returned as a list of relative paths. `unlock_type_parameter` clears the stored Target only, and every Lock stays. The new `_apply_type_locks_to_new_instances` runs at the end of `add_instance`, `add_type_parameter` and `add_nested_type`. It gives every submodule that became an Instance during the edit the Type Locks of its Type, pre-existing parameters included. Broadcasts go out in this order: `parameter-creation`s, then `pm-lock-update`s, then `pm-type-update`. `test/pytest/test_pm_types.py` grew from 124 to 161 tests.

### Commit by commit
- `682ab21` The two methods, `_classify_lock_application` (lock / relock / none / skip for one parameter), the creation-path application and 31 tests. The orchestrator's nine readings in the coder spec set these rules:
  - full-form stored Target
  - own entries only, via `_require_type_entry`
  - validate first, with an up-front self-lock and cycle check across all Instances that names every offender
  - a re-declare with a different Target skips the Followers still locked to the old one
  - `unlock_type_parameter` on an entry with no Type Lock is an INFO no-op that emits nothing
  - only the edited Type gets a `pm-type-update`

  Two coder questions changed reading 6. It had said only *created* parameters get Type Locks. The orchestrator answered from D17 ("new Instances ... get it at creation") that the unit is the Instance. A submodule that becomes an Instance (instances after the edit minus instances before) gets the Type Locks on all its parameters at those paths, kept ones included. Second, `add_type_parameter` can never complete a new Instance under the 2.3 loops, because it only writes into existing Instances. So its test became a negative one (`test_add_type_parameter_applies_no_type_locks`). `add_nested_type` can complete one, so it walks the union of `_nesting_prefixes` of the outer Type and the Nested Type (`test_add_nested_type_applies_the_nested_type_lock_under_the_submodule`). The coder made one judgment call. On the creation path, a Lock that would close a cycle or hit a parameter that cannot carry a Lock is skipped with the warning, so the three creation methods never raise. `lock_type_parameter` raises up front instead, and also checks "cannot carry a Lock" there. The tests cover the plan's list and more:
  - apply, the default Globals Target, skip-with-warning (`caplog`), no skips means no warning
  - a new Instance auto-locked, a kept parameter locked with its value and unit unchanged, a missing stored Target skipped
  - rule removal leaves the Locks (`test_unlock_type_parameter_leaves_every_lock_in_place`), `test_an_instance_falling_out_keeps_its_locks`
  - re-declare re-applies, re-declare with a different Target, an explicit ordinary Target
  - refusals: unknown Type, non-own entry, missing Target, self-lock, cycle, and `test_lock_type_parameter_names_every_offending_path`
  - five sink tests on Broadcast order and silence
  - two proxy tests: the skipped list and the full-form `target` over the wire, and a `SubClient` receiving the Type Lock Broadcasts from a second client

  Orchestrator run: ruff clean, 155 in `test_pm_types.py`, 393 in the full suite.
- `efbafc6` Fix from round 0, four items:
  - `_apply_type_locks_to_new_instances` classified every application against the state before the batch, but each `lock()` checks again against the Locks that earlier applications in the same batch had already made. reviewer-qwen (must-fix) built a case: `z1` locked to `q05.b`, `z2` locked to `q05.a`, and Type Locks on `a`→`z1` and `b`→`z2`. There `add_instance("T","q05")` created `q05.c`, locked `q05.a`, then raised a cycle error, leaving the Instance half-locked. The orchestrator reproduced it. The loop now catches `ValueError` from `lock()`/`relock()` and records the exception text as that parameter's skip reason (`test_add_instance_skips_an_application_the_batch_made_a_cycle`).
  - Tests for the coder's creation-path skips: `test_add_instance_skips_a_parameter_that_cannot_carry_a_lock` and `test_add_instance_skips_an_application_that_would_close_a_cycle` (both test reviewers).
  - The `relock` branch at creation: `test_add_instance_relocks_a_follower_that_fell_out_and_came_back` (both test reviewers). The outer-side `add_nested_type` variant the fix list asked for cannot be built, because a submodule that carries the outer Type's full pre-nesting set is already an Instance. The orchestrator accepted the coder's three-tier substitute, `test_add_nested_type_locks_a_pre_existing_parameter_through_two_levels`.
  - `test_lock_type_parameter_with_no_instances_stores_the_rule`: declare first, add the Instance later (test-reviewer-qwen, should-fix).

  All six approved in re-review, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 161 in `test_pm_types.py`, 399 in the full suite.

### Dropped findings
- The `seen` set in `_apply_type_locks_to_new_instances` de-duplicates by parameter path alone. Two different defining entries with different Targets that reach one path in the same edit would drop the second without a warning (reviewer-glm, reviewer-qwen, nits) → not sent. reviewer-glm found no way to reach it through the public API. The plan does not say which Target should win. Flagged for Marcos.
- "Only the rule goes" wording in the docstring and section comment, and "stores the rule" in the round-1 test name (reviewer-glm, plan-checker-glm, then five reviewers in round 1, nits) → not sent, because it mirrors D17. Reading 8 of the coder spec says "rule" alone is not a glossary term, and the wording is still in `params.py` and `test_pm_types.py`.
- Self-lock and cycle messages are pinned with one offender only. Broadcast order is not pinned for `add_nested_type` or for a mixed re-declare (test reviewers, nits) → not sent.

### Questions to Marcos
- Both coder questions (Type Locks apply to the whole new Instance, kept parameters included; D17's "an `add_type_parameter` that completes them" has no reachable case) were answered by the orchestrator from D17 and flagged for Marcos, along with the nine readings and the `seen` de-dup. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 3.3: a stored Target that no longer exists is skipped with a warning on the creation path, until deletion clears Type Locks.
- plan-checker-qwen: suppose a Nested Type sits at a dotted, deeper position (`add_nested_type("M", "s.s2", "N")`). A new Instance of `M` that this edit completes would not get `M`'s own-entry Type Locks. This is recorded in `decisions.md` only, not fixed and not tested.
- Nothing from 3.2 is in `TEST_AUDIT.md`.

### Process notes
- Marcos told the run during 3.2 to continue through every phase instead of stopping at the end of Phase 3 (`orchestration/RUNS.md`).
- The coder went idle after the orchestrator answered its first question, with no edits and no worker_done. One nudge got it moving again.
- Four permissions were rejected. reviewer-qwen and test-reviewer-qwen each asked for opencode's temp directory outside the repo. Each also first ran a scratch script (`repro_cross_target.py`, `scratch-verify.py`) that changed into a temp directory outside the repo. Both scripts were rewritten to run from their round folder, and were scanned and allowed. All scratch files and logs under `orchestration/3.2/` were deleted afterwards.
