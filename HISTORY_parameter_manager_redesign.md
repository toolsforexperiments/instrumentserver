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

## 3.3 Deletion interplay — 2026-09-25

`ParameterManager.remove_parameter` now clears the Type Locks whose stored Target it deletes (D18). This covers a Globals parameter or any explicit Target. After the 1.2 Lock cleanup it sets `_TypeEntry.target` to `None` on every own entry of every Type that pointed at the removed parameter. The Broadcasts go out after the mutation, in this order: one `pm-lock-update` with `None` per dropped Follower, then one `pm-type-update` per affected Type in registry order, then the deletion. The deletion Broadcast is the Server's own `parameter-deletion`. `remove_type` and `remove_type_parameter` keep their behaviour, which is now asserted: the Type Locks go, and the Globals parameters and every Instance Lock stay. `test/pytest/test_pm_types.py` grew from 161 to 180 tests.

### Commit by commit
- `6b033a3` The cleanup loop in `remove_parameter`, docstring updates in the class, `remove_parameter`, the Globals section comment and `_apply_type_locks_to_new_instances`, and 17 new tests. The orchestrator's readings in the coder spec set these rules:
  - any Type Lock Target counts, not only Globals parameters
  - own entries only
  - order: Lock updates, then Type updates, then the deletion
  - `remove_type` and `remove_type_parameter` stay unchanged and are only asserted
  - whatever `remove_all_parameters` turns out to do is accepted and pinned

  The caller check showed that `remove_all_parameters` routes through `remove_parameter`. It deletes the Followers before the Globals Target, so it emits a single `pm-type-update` and no `pm-lock-update` (`test_remove_all_parameters_emits_the_type_lock_clearing`). The Type definitions stay for 4.3. The coder rewrote the 3.2 interim test `test_add_instance_skips_the_type_lock_when_the_target_is_gone`, whose comment said it held only until 3.3. It became `test_after_a_deletion_cleared_the_type_lock_a_new_instance_gets_no_lock`, which also checks that a re-declared `lock_type_parameter` recreates the Globals Target on demand. The defensive skip for a missing stored Target stays, documented as reachable only through a registry inserted by hand. The new tests include:
  - unit: a Globals Target, two Types sharing one explicit Target, an ordinary explicit Target, a Target of ordinary Locks only, a Target of both ordinary Locks and Type Locks, a Follower removal, and the refusal (`KeyError` and `ValueError`, with `lock_state` covering `_types`)
  - `test_remove_type_leaves_the_globals_parameters_and_instance_locks` and `test_remove_type_parameter_takes_the_type_lock_with_it`
  - six sink tests on order and silence
  - `test_removing_a_globals_type_lock_target_over_the_wire`: a `SubClient` sees two `pm-lock-update`s with `None`, the `pm-type-update` and `parameter-deletion`

  Orchestrator run: ruff clean, 178 in `test_pm_types.py`, 416 in the full suite.
- `fc60b13` Fix from round 0, three items:
  - The rewrite in `6b033a3` had removed the only test of the kept stale-Target skip in `_apply_type_locks_to_new_instances`. test-reviewer-glm (should-fix) and reviewer-glm (nit) caught it. `test_add_instance_skips_a_hand_inserted_stale_target` sets `pm._types["qubit"].parameters["IF"].target` to a missing path. It asserts one warning naming `'q07.IF'` and "does not exist", and a `q07.IF` with no Lock.
  - `test_two_entries_sharing_a_removed_target_emit_one_type_update` checks for one `pm-type-update` per Type, not one per cleared entry (test-reviewer-qwen, nit). The orchestrator kept it because it pins the task's "for each affected Type".
  - A `TEST_AUDIT.md` row, "Locks — removing a parameter". It records that `remove_parameter` raises `KeyError` for a missing leaf but `ValueError` for a missing Parameter Group, while `_get_param` raises `ValueError` for both (reviewer-qwen, nit). This dates from 1.2 and is left alone per plan rule 6.

  All six approved in re-review with no findings, and each raiser confirmed their item fixed. Orchestrator run: ruff clean, 180 in `test_pm_types.py`, 418 in the full suite.

### Dropped findings
- No test removes the Target of a Type Lock declared on a Nested Type's own entry (test-reviewer-glm, nit) → not sent. That case runs the same own-entry loop. The outer Type's effective set then shows `target: None` without a `pm-type-update` of its own, which is consistent with reading 1 but not pinned. test-reviewer-glm accepted the drop in round 1.

### Questions to Marcos
- The orchestrator flagged its coder-spec readings for Marcos: any Target counts, the Broadcast order, `remove_type`/`remove_type_parameter` unchanged, and the `remove_all_parameters` consequence accepted. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 4.3: after `remove_all_parameters` the Type definitions stay, with their Type Locks cleared. `switch_to_profile` has to clear Types wholesale.
- `TEST_AUDIT.md`, "Locks — removing a parameter": the `KeyError`/`ValueError` mismatch. The 1.2 and 3.3 refusal tests pin both types.
- plan-checker-glm (observation): the `pm-type-update` loop calls `get_type` after the entries are cleared. A registry corrupted by hand so that `get_type` raises would make `remove_parameter` raise before the deletion. The public API can't reach that state, and every Type-editing method has the same pattern.

### Process notes
- plan-checker-glm's round-1 worker_done was rejected by Orca because of a garbled handle. After one nudge it resent, and a later duplicate was rejected as already settled, which did no harm. There were no stalls and no rejected permissions.

## 4.1 Writer — 2026-09-25

`ParameterManager.toParamDict()` now returns the D19 version-2 profile document, `{"version": 2, "parameters": {...}, "types": {...}}`, and `toFile` writes it with `json.dump(..., indent=2, sort_keys=True)` as before. `parameters` is keyed by full paths and stores each parameter's own value (`ManagedParameter.own_value()`), its unit and, on Followers only, `lock: {target, locked}`. `types` stores every Type's entries (`default`, `unit`, full-form `target` or `null`) and its Nested Types. The new `schemas/parameter_manager_v2.json` and `serialize.validateParameterManagerV2` check the whole document and then run the `parameters` map through the unchanged `validateParamDict`. `fromParamDict` got a minimal reader shim so profile round trips keep working until 4.2. The new `test/pytest/test_pm_persistence.py` has 21 tests.

### Commit by commit
- `8c5db87` The writer, the schema (plus `PM_V2_SCHEMA_PATH` in `instrumentserver/__init__.py`), `validateParameterManagerV2`, the reader shim and 19 tests. The orchestrator's readings in the coder spec set these rules:
  - the signature `toParamDict(self, simpleFormat=False, includeMeta=["unit"])` stays (rule 7), and `simpleFormat` is documented as ignored
  - `parameters` is built from `serialize.toParamDict([self], simpleFormat=False, ...)`, then own values are substituted and `lock` added. A locked Follower's snapshot reports the Target's value, which is why the substitution is needed.
  - the shim: no `version` key means the legacy flat map, loaded exactly as before. `version: 2` is validated, then only `parameters` is loaded (value, unit, `deleteMissing`), and `lock` and `types` are ignored until 4.2. Any other version raises `ValueError` naming it.
  - `validateParamDict`, `isSimpleFormat`, the Server's `serialize.fromParamDict`, `switch_to_profile` and `remove_all_parameters` stay untouched

  The new private `_create_managed_parameter` is the `_get_parent(..., create_parent=True)` + `_add_own_parameter` pair that `_ensure_global_target` used to inline. Both `_ensure_global_target` and the shim now call it, so a missing `_globals.*` parameter in a file gets created instead of hitting the 3.1 refusal in `add_parameter`. `test_param_manager.py` had five flat-shape assertions in three tests, and they now read `["parameters"][...]`. The schema is shipped by the existing `schemas/*.json` package-data glob, with no `pyproject.toml` change. The tests cover:
  - the writer: version and keys, `simpleFormat` ignored, `test_locked_follower_saves_its_own_value_and_the_lock`, `locked: false`, no `lock` key without a Lock, a Globals parameter saved, the full `types` section, the full-form Type Lock Target, `types == {}`
  - the file: `jsonschema.validate` against the new schema, and the file text equal to `json.dumps(doc, indent=2, sort_keys=True)`
  - the shim: legacy flat and simple-format files, a version-2 round trip through `fromFile`, `test_globals_parameter_round_trips_through_the_internal_path`, `deleteMissing` both ways, the shim ignoring `lock`/`types` (without asserting they are not restored), the refusal of versions `3` and `"2"`, and two schema refusals

  Orchestrator run: ruff clean, 32 in the two named files, 437 in the full suite.
- `d36053c` Fix from round 0, five items:
  - `test_include_meta_selects_the_per_parameter_metadata`: `includeMeta=[]` reduces an entry to `{"value": 123}` while a Follower keeps its `lock`, and `["unit", "label"]` adds `label`. No test had varied `includeMeta`, which rule 7 protects (test-reviewer-glm, should-fix).
  - Three more cases in `test_invalid_document_is_refused_by_the_schema`. `vals: 42` passes the v2 schema and is refused only by `parameters.json`, so deleting that leg of `validateParameterManagerV2` now fails a test (both test reviewers, should-fix). A missing top-level `types` key (both test reviewers, nit, folded in). A Type entry without `target`.
  - The shim's `_globals.` branch sits in the load loop both formats share, so a legacy flat file with a `_globals.*` key now creates the parameter where it used to raise. That departs from reading 3's "exactly today's behaviour" for legacy files. test-reviewer-qwen (should-fix) caught it. The orchestrator decided create-on-load is intended for both formats (D18, "saved") and pinned it with `test_legacy_flat_file_creates_a_globals_parameter_on_load`. The TEST_AUDIT row "Profiles — loading Globals parameters" went from `gap` to `covered`.
  - The `types` side of the schema is now strict: `required` and `additionalProperties: false` on the per-Type and per-entry objects. reviewer-glm, reviewer-qwen and plan-checker-qwen raised it as a nit. It was kept because both reviewer models raised it and 4.2 builds Type loading on these keys.
  - Two `gap` rows in `TEST_AUDIT.md` for older defects (rule 6). "Profiles — loading a file": `fromFile` never forwards `deleteMissing`, so the GUI's `deleteMissing=False` load runs with `True` (reviewer-glm and the coder). "Profiles — file validation": both schemas use `patternProperties` without `additionalProperties: false`, so a malformed parameter key passes validation (plan-checker-qwen).

  There were no source changes outside the schema. All six approved in re-review, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 34 in the two named files, 439 in the full suite.

### Dropped findings
- The `toParamDict` docstring says values come from the cache and "never `get`". For a locked Follower, `snapshot_base` does call `get()` on the Target, though the saved own value is from the cache (reviewer-qwen, nit) → not sent. The wording is still in `params.py`.
- `test_locked_follower_saves_its_own_value_and_the_lock` checks `toParamDict()` output rather than reading the file back (plan-checker-glm, nit) → not sent. The file-text and schema tests write the same locked-Follower case to disk.
- Round 1 nits, none sent. The rewritten TEST_AUDIT row says every missing parameter goes through the internal path, when only `_globals.*` ones do (reviewer-glm, reviewer-qwen); it goes to the 4.2 coder spec. A test comment says `parameters.json` refuses unknown keys, but the `vals` case is refused by its type constraint (reviewer-glm). The per-Type `required` and both `additionalProperties: false` have no refusal case of their own (test-reviewer-glm).

### Questions to Marcos
- The orchestrator flagged its coder-spec readings for Marcos: the v2 shape, `simpleFormat` kept but ignored, the new validator, the parameters-only shim with Globals created through the internal path, and the Server reader left alone. It also flagged the round-0 create-on-load decision for legacy files. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 4.2 (from reviewer-glm, recorded in `decisions.md`): loading a document while a parameter is locked in-session raises mid-loop on `set` (D6), with earlier entries already loaded. D20's order must unlock or clear Locks before values, or load own values through the cache.
- For 4.2: the shim ignores `lock` and `types`. The tests deliberately do not assert that they stay unrestored, so 4.2 can restore them without rewriting tests. The strict `types` schema is what 4.2's Type loading can rely on.
- `TEST_AUDIT.md`: "Profiles — loading a file" (`fromFile` drops `deleteMissing`) and "Profiles — file validation" (`patternProperties` gap), both `gap`. The wording of "Profiles — loading Globals parameters" is to be corrected in 4.2.

### Process notes
- Two permissions were rejected in round 0. test-reviewer-qwen and reviewer-qwen each tried an inline `uv run python - <<'EOF'` heredoc that could not be read in full. Each reran its check as a scanned probe script in `orchestration/4.1/round-0/` and deleted it afterwards.
- The coder left a `mkdtemp` scratch folder under `orchestration/4.1/`, which the orchestrator removed. There were no stalls and no nudges.

## 4.2 Reader — 2026-09-25

`ParameterManager.fromParamDict` now loads the whole version-2 profile document through the new `_load_v2_document`, and `fromFile` inherits this. The legacy flat map (no `version`) still loads parameters only and leaves Types and Locks alone. `_collect_v2_document_problems` validates the document before anything changes and joins every problem into one `ValueError`. After that the load runs in D20's order: it drops the Locks of every parameter the document lists, loads the parameters, writes the Types straight into `_types` with no Instance side effects, and puts each stored Lock back as stored. The Broadcasts go out once, after the whole load succeeds. `test/pytest/test_pm_persistence.py` grew from 21 to 41 tests, with a new checked-in fixture, `test/pytest/fixtures/parameter_manager-legacy.json`.

### Commit by commit
- `b6ee025` The reader and 16 tests. The orchestrator's readings in the coder spec set these rules:
  - Validation covers the schema (`validateParameterManagerV2`) and more. Every key must carry the `<name>.` prefix. Type names must not be `_globals` or empty. Every Nested Type must be a Type of the document, with no Nested Type cycle and no path twice in an effective set. Every `lock.target` and non-null Type `target` must be a `parameters` key of the document, and each missing Target is named with the Followers or `<type>.<entry>`s that refer to it. The document's Locks must hold no self-lock and no cycle.
  - Load order: (a) the Locks on listed parameters go first, so setting a stored own value on a locked Follower cannot raise (D6; this was the 4.1 loose end); (b) the parameters, with the old `deleteMissing` semantics, and Globals through `_create_managed_parameter`; (c) the Types, and with `deleteMissing=True` every Type the document does not define is removed; (d) each Lock is set directly with its stored Target and `locked` state, after `_check_lock_allowed`.
  - Broadcasts: one `pm-type-update` per Type written, one with `None` per Type removed, then one `pm-lock-update` per Lock that ended different from before, in tree order. Nothing is emitted for values, and no `parameter-creation`/`parameter-deletion` is re-emitted. The docstring says a GUI must refresh its structure after a profile load (for 5.1).
  - `fromFile` still does not forward `deleteMissing` (rule 6, TEST_AUDIT row "Profiles — loading a file").

  To validate the document's Types without touching the registry, `_require_type`, `_expand_effective` and `_collect_effective` gained an optional `types` argument. The reader passes them a candidate registry built from the document. During the load the coder detaches `_broadcast_sinks` and restores them in a `finally`, so `remove_parameter`'s own Broadcasts do not mix into the load's single report. The commit also corrects the wording of the TEST_AUDIT row "Profiles — loading Globals parameters": only `_globals.*` parameters take the internal path (reading 6). The coder reported one possible edge: with `deleteMissing=False`, step (d)'s `_check_lock_allowed` might raise mid-load. All six reviewers judged it unreachable, because validation requires every Target to be a key of the document and step (a) has already cleared those parameters' Locks. reviewer-glm and test-reviewer-glm each confirmed this with a probe. The tests cover:
  - the four the plan names: `test_legacy_fixture_file_loads_values_and_units`, `test_version_two_document_round_trips_exactly` (document equality, pull-on-get, own values, both Lock states), `test_missing_targets_are_all_named_and_change_nothing` and `test_partial_instances_are_not_completed_and_get_no_type_lock`
  - up-front refusals: a Nested Type missing from the document, a Nested Type cycle, a duplicated effective path, a Lock cycle, a self-lock, and a key of another instrument
  - `test_a_listed_parameter_without_a_lock_entry_loses_its_lock` and `test_a_locked_follower_loads_its_own_value_and_the_files_lock_state`
  - `deleteMissing` both ways, Broadcast order and content for one load, and `test_legacy_load_leaves_types_and_locks_untouched`

  Orchestrator run: ruff clean, 50 in the two named files, 455 in the full suite.
- `f99f580` Fix from round 0, six items:
  - `test_a_complete_instance_gets_no_type_lock_on_load`: the document completes `q01` into a `qubit` Instance whose `octave_gain` entry has a Type Lock, and carries no `lock` entries. After the load, `instances_of("qubit") == ["q01"]`, `list_locks() == {}`, and `list()` holds exactly the document's four keys. test-reviewer-glm caught the gap (should-fix). The partial-Instance test could not catch Type Locks being applied on load, because its `q01` never matches the Type.
  - `test_invalid_type_names_in_the_document_are_refused_up_front`: `_globals` and `""` are both named in one message, and nothing changes or is emitted. Both test reviewers caught it (should-fix): the check existed but no test ran it.
  - `test_target_validation_is_document_relative` and `test_nested_type_validation_is_document_relative`: a Target or Nested Type that exists in-session but not in the document is refused. test-reviewer-glm caught it (should-fix). Every earlier refusal test used names that existed nowhere, so a regression to "accept it if it exists in-session" would have gone unnoticed. This is also the coder's reported edge.
  - The 4.1 test `test_the_shim_ignores_the_lock_and_types_sections` became `test_parameters_load_with_own_values_from_a_v2_file_with_locks_and_types`, with its docstring reworded and its assertions unchanged. test-reviewer-glm raised it as should-fix, and plan-checker-glm, plan-checker-qwen and test-reviewer-qwen as nits. The `pm-type-update` payload check in `test_delete_missing_removes_absent_parameters_types_and_locks` went from `is not None` to `== pm.get_type("kept")` (test-reviewer-qwen, nit, folded in).
  - The redundant `and deleteMissing` inside the `if deleteMissing:` loop is gone (reviewer-glm, reviewer-qwen, nits). It was sent because both reviewer models raised it and it is one line.
  - `TEST_AUDIT.md`: the "Profiles — file validation" row now also mentions documents holding both `params.q01` and `params.q01.x`, or a bare `params._globals`. These pass validation and then fail mid-load or shadow a submodule, a hole inherited from the legacy reader (reviewer-glm). A new `gap` row, "Types — empty Type name": `add_type("")` succeeds, so such a manager is written by `toFile` and then refused by the reader (test-reviewer-glm, nit).

  All six approved in re-review, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 54 in the two named files, 459 in the full suite.

### Dropped findings
- The `assert target_param is not None` in step (d) would be skipped under `python -O` (reviewer-qwen, nit) → not sent. The value cannot be `None` after validation, and the codebase already uses asserts for such states.
- The loop variable `spec` for a document Type could be `type_spec` (plan-checker-qwen, nit) → not sent.
- Round 1: the extended "Profiles — file validation" row puts the bare `params._globals` key under the wrong failure. It actually fails on the reserved Globals name in `add_parameter`, and the shadowing happens only when the dotted key comes first (reviewer-qwen, nit) → not sent. The wording is to be corrected when the row is next touched.

### Questions to Marcos
- The orchestrator flagged its coder-spec readings for Marcos: the validation list, the load order with Locks cleared first, `deleteMissing` also removing Types, Broadcasts after the load with no creation/deletion re-emission, and `fromFile` left not forwarding `deleteMissing`. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- For 5.1: a profile load emits no `parameter-creation`/`parameter-deletion`, so the GUI must refresh its structure after a load (stated in the `fromParamDict` docstring).
- `TEST_AUDIT.md` gaps still open: "Profiles — loading a file" (`fromFile` drops `deleteMissing`), "Profiles — file validation" (now also key collisions), and "Types — empty Type name".
- The decisions.md note on the coder's mid-load edge overstates it; the reviewers showed it cannot be reached. No test loads a changed unit onto an existing parameter, which was already the case before this task (test-reviewer-glm).

### Process notes
- Seven permissions were rejected in round 0. The coder asked for `/tmp`. reviewer-qwen asked for opencode's temp directory. plan-checker-qwen mistyped the repo path as `/Users/marcof2/...`. plan-checker-glm, test-reviewer-glm and reviewer-glm each tried an inline `uv run python - <<'EOF'` heredoc, and test-reviewer-qwen an inline `python -c`, none of which could be read in full. Each reran its check as a scanned probe under `orchestration/4.2/round-0/`. All probes and logs were deleted afterwards. There were no stalls and no nudges.

## 4.3 Profiles — 2026-09-25

`ParameterManager.switch_to_profile` now follows D20: it saves the current profile as the version-2 document `toFile` writes, clears parameters, Types and Locks with the new private `_clear_all()`, and then loads the new profile through `fromFile` (legacy flat map or version 2). `_clear_all` deletes every Type straight out of `_types` and emits one `pm-type-update` with `None` per Type, in registry order. It then calls `remove_all_parameters`, which is unchanged and emits its usual `pm-lock-update` `None`s. `test/pytest/test_pm_persistence.py` grew from 41 to 48 tests. The task finished in one commit with no fix round.

### Commit by commit
- `925967c` `_clear_all`, the new clear step in `switch_to_profile` and seven tests. The orchestrator's readings in the coder spec set these rules:
  - take the plan's second option: `remove_all_parameters` keeps its signature and behaviour (rule 7), so a direct call still leaves the Type definitions in place, as 3.3 pinned
  - Types go before parameters, so `remove_parameter` finds no Type Lock to clear and emits no extra `pm-type-update`
  - `switch_to_profile` validates first (an unknown profile raises `ValueError` and nothing is saved), then save → `_clear_all` → load, then `selectedProfile` as before
  - `refresh_profiles`/`list_profiles` stay unchanged, and a test asserts it

  Deleting from `_types` directly, rather than calling `remove_type` for each Type, is needed because `remove_type` refuses a Type that another Type nests (reviewer-glm and plan-checker-qwen both checked this). The coder's caller check found one production caller of `switch_to_profile`, the GUI's `loadProfile` at `gui/instruments.py:851`, which keeps working unchanged. The tests share a helper, `make_profile_switch_manager`, which builds a profile `typed` holding two Types (one nesting the other), an Instance, a Type Lock whose Globals Target has its own value, an explicit-Target Lock and an unlocked Lock. It saves that profile next to a parameter-only profile `empty`. The tests:
  - `test_switching_to_a_profile_without_types_or_locks_clears_them`, the plan's named test: no Type, no Lock, no `_globals` submodule, only the new profile's parameter
  - `test_switching_back_restores_types_locks_and_the_globals_parameter`: `get_type` equal, `list_locks()` equal, the Globals value back, and the Followers pulling again
  - `test_the_switch_saves_the_leaving_profile_as_a_version_two_document`: it changes a value after the helper's own save, so only the switch's save can have written it
  - `test_switching_to_a_legacy_flat_profile_leaves_no_type_or_lock`
  - `test_clear_all_emits_type_updates_then_lock_updates_and_nothing_else`: two `pm-type-update` `None`s in registry order, then one `pm-lock-update` `None`, and nothing else
  - `test_switch_to_an_unknown_profile_raises_and_saves_nothing`: file contents and `st_mtime_ns` unchanged, and no new file
  - `test_refresh_and_list_profiles_are_the_same_around_a_switch`, including a second manager whose own profile file is created by the switch's save

  The existing switching tests in `test_param_manager.py` and the `remove_all_parameters` tests in `test_pm_types.py` and `test_pm_locks.py` pass unchanged. All six reviewers approved in round 0 with no must-fix or should-fix findings. Orchestrator run: ruff clean, 61 in the two named files, 466 in the full suite.

### Dropped findings
None of these were sent, since there was no fix round:
- If the load step fails (corrupt JSON, or a version-2 document the 4.2 validation refuses), the switch has already saved and cleared, so the manager is left empty (reviewer-glm, nit; test-reviewer-qwen, nit, asking for a test that pins it). This follows from D20's order, and before 4.3 the same path already cleared the parameters. 4.3 only adds the Types and Locks to what gets cleared. reviewer-glm suggested that a later task could read and validate the target document before saving and clearing. The orchestrator flagged this for Marcos.
- The `_clear_all` Broadcast test depends on the order `_to_tree` removes parameters in: Parameter Groups first, then root parameters. `follower` goes after its Target, so its dropped Lock is announced, while `q01.IF` goes before its Globals Target, so its Lock dies unannounced. Both test reviewers raised this as a nit, and test-reviewer-glm suggested a comment line for the `q01.IF` half. A change in removal order would make the test fail loudly, not pass silently.
- `_clear_all` builds the `pm-type-update` `None` Broadcast inline, the third copy next to `remove_type` and `_broadcast_type_update` (reviewer-glm, nit). `_broadcast_type_update` can't be reused because it calls `get_type` on the Type that was just removed.
- The tests move into `tmp_path` with `monkeypatch.chdir` instead of setting `workingDirectory` as reading 5 worded it (plan-checker-glm, nit). The result is the same.

### Questions to Marcos
- The orchestrator flagged its coder-spec readings for Marcos (a private `_clear_all` with `remove_all_parameters` untouched, and validate → save → clear → load), along with the emptied manager after a failed load. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- `does_profile_exist` matches by substring (reviewer-qwen, pre-existing). A name that is a substring of an existing profile file passes the check, and the switch then saves, clears and loads a missing file, which `fromFile` only warns about, so the manager ends up empty. `decisions.md` sends it to TEST_AUDIT at 6.3. No `TEST_AUDIT.md` row exists yet.
- test-reviewer-glm: the switch-level tests alone can't show that `_clear_all` did the clearing, because the 4.2 reader with `deleteMissing=True` also removes Types the document doesn't define. `test_clear_all_emits_type_updates_then_lock_updates_and_nothing_else` pins the clear step directly.
- For Phase 5: the GUI's `loadProfile` now clears Types and Locks on a switch too.

## 5.1 Client-side state and broadcast handling — 2026-09-25

The Parameter Manager GUI now keeps a client-side copy of the Types and Locks. `PMState` is a plain class in `gui/instruments.py`, owned as `ParameterManagerGui.state`, with `types` keyed by Type name and `locks` keyed by the Follower's path relative to the Parameter Manager (the form `list_locks()` returns). `refresh(instrument)` re-reads both, and `apply_lock`/`apply_type` replace one entry or drop it on `None`. `ModelParameters` gained two signals, `lockChanged(str, object)` and `typeChanged(str, object)`. `updateParameter` emits them for `pm-lock-update` and `pm-type-update` without touching any model item, and `connectSignals` wires them to the state. `ParameterManagerTreeView.onItemNewValue` now calls `widget._setMethod(value)` (D24 item three). The new `test/pytest/test_pm_gui.py` has 9 tests.

### Commit by commit
- `9928d03` `PMState`, the two signals and their routing, the D24 fix and 7 tests. The orchestrator's readings in the coder spec set these rules:
  - the state is refreshed at the end of `__init__`, in `refreshAll`, in `loadProfile` and in `loadFromFile`
  - the two signals carry `fullName`, the same instrument-name strip the other branches use. For a Lock that is the Follower's relative path and for a Type the bare Type name. Several reviewers checked this against `_broadcast_lock_update` and `_broadcast_type_update` in `params.py`, and checked that `SubClient` delivers `bp.value` as a blueprint or `None`.
  - the D24 fix copies `ParametersTreeView.onItemNewValue`, including its `try/except RuntimeError` with a debug log. `ParameterWidget` defines `_setMethod` for every input kind, so no forwarding to the inner widget was needed.
  - nothing else in the GUI changes (no Lock column, tints or panels; those are 5.2 onwards)

  The tests use the module-scoped Server on `server_port` and build the GUI with `sub_port=server_port + 1`. A second `Client` drives the Parameter Manager, and every cross-client assertion uses `qtbot.waitUntil`. An autouse fixture moves the module into a temporary working directory, and the `pm` fixture writes one profile there, because `ParameterManagerGui.__init__` calls `loadProfile`. The helper `_wait_until_broadcasts_arrive` handles the zmq slow joiner: it adds throwaway probe Types until one of them reaches the state. The tests:
  - `test_pm_state_helpers_work_without_a_server`: `refresh`, `apply_lock` and `apply_type` against a local `ParameterManager`
  - `test_state_on_construction_holds_types_and_locks_created_before`
  - `test_lock_broadcasts_from_a_second_client_update_the_state`, the plan's named test: `lock`, then `unlock` (`locked` goes False), then `remove_lock` (the key is gone)
  - `test_type_broadcasts_from_a_second_client_update_the_state`: `add_type`, `add_type_parameter`, `remove_type`
  - `test_type_lock_from_a_second_client_updates_types_and_locks`: the Type entry's `target` and the Instance Locks both appear. It declares an explicit Target, because the default Globals Target would send a `parameter-creation` into the pre-existing crash described under Loose ends.
  - `test_a_second_clients_set_reaches_the_tree_widget`
  - `test_refresh_all_refills_the_state_from_the_server`, with the listener stopped

  Orchestrator run: ruff clean, 17 in the three named GUI files, 473 in the full suite.
- `d5c5ded` Fix from round 0, four items:
  - `test_load_profile_refreshes_the_state_without_broadcasts`: with the listener stopped, the second Client adds a Type, and after `gui.loadProfile()` the Type is in `gui.state`. Nothing had covered the refresh in `loadProfile`. It is the one that matters, because 4.2's profile load sends no `parameter-creation`/`parameter-deletion` and `loadProfile` calls `super().refreshAll()`, which skips the override's refresh (test-reviewer-glm, should-fix).
  - `test_on_item_new_value_uses_the_parameter_widget_set_method`: a stub widget with no `paramWidget.setValue` sits in `view.delegate.parameters`, and `onItemNewValue` is called directly on a `ParameterManagerTreeView` over a local `InstrumentBase`. The live test could not tell the fix from the old code: Proxy parameters carry no validators, so every Parameter Manager row is an `AnyInput`, and there `_setMethod` is `paramWidget.setValue` (test-reviewer-qwen, should-fix; test-reviewer-glm, nit).
  - The refreshes in `__init__` and `loadFromFile` are gone, since `loadProfile` and `refreshAll` already refresh at those points (reviewer-glm and plan-checker-glm, nits, one-line removals). The comment on the `pm-lock-update` branch now cites D10 instead of D22 (reviewer-glm, nit, folded in).
  - Two `gap` rows in `TEST_AUDIT.md` for the defects the coder found (rule 6): "Parameter Manager GUI — live creation from another client" and "Profiles — GUI start with no profile file".

  The commit shows only those two removals and the comment in `src/`. All six approved in re-review, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 19 in the three named GUI files, 475 in the full suite.

### Dropped findings
- Nothing asserts that the two PM Broadcasts leave the model's items alone (both test reviewers, nit) → not sent. The risk is low, and 5.2/5.3 will give these actions model effects on purpose.
- `loadFromFile`'s path through `refreshAll` has no test of its own (test-reviewer-qwen, nit) → not sent. It is the same `PMState.refresh` that the `refreshAll` test covers, and 5.4/5.5 exercise files more.
- The `loadProfile` comment blames missing creation/deletion Broadcasts for the Types/Locks refresh, when a profile load does send `pm-type-update`/`pm-lock-update` diffs (plan-checker-qwen, nit) → not sent. The comment is still in `loadProfile`.
- Round 1 nits, none sent: the stub test's `ModelParameters` gets no `sub_port`, so its `SubClient` subscribes to the default Broadcast port 5556. It never binds, but it is a fixed port under D27's rule (test-reviewer-glm, reviewer-qwen). The inner stub's recording list is never read (reviewer-qwen). Also left from round 0: the broad `except Exception` in `_wait_until_broadcasts_arrive` (reviewer-qwen).

### Questions to Marcos
- The Lumen coin budget kept running out, and when all six round-1 re-reviews were blocked by it the orchestrator stopped to ask what to do → Marcos topped up the budget and said to finish 5.1 and report back.
- The orchestrator flagged its coder-spec readings for Marcos: a plain `PMState` class, where it is refreshed, signals that only route and touch no model item, and the D24 fix copying `ParametersTreeView`. No answer is recorded yet, in the working folder or in `orchestration/RUNS.md`.

### Loose ends
- `TEST_AUDIT.md`, "Parameter Manager GUI — live creation from another client": a parameter that another Client creates while the GUI is open raises `AttributeError` in `updateParameter`'s `parameter-creation` branch. `nestedAttributeFromString` runs on the stale Proxy blueprint, even though `update()` is called first. All six reviewers confirmed the branch is unchanged from `dc15389`. This means the default-Target flow of `lock_type_parameter` has no GUI-level test until the crash is fixed (plan-checker-glm).
- `TEST_AUDIT.md`, "Profiles — GUI start with no profile file": `switch_to_profile` raises when no profile exists, so the GUI cannot be built until there is one.
- For 5.2/5.3: `lockChanged` and `typeChanged` only update `gui.state`. The Lock column and the Type tints can read the state or connect to the signals.

### Process notes
- `decisions.md` records the Lumen coin budget running out three times in fix round 1. The first time, one nudge after about 10 minutes got the coder going again. The second time, opencode scheduled a retry in about 48 minutes, and the fix edits sat uncommitted on disk while the orchestrator waited. After the retry the coder ran the suite green, but the budget ran out a third time before it committed, and a nudge got "No healthy endpoints for model glm-5.3-flash". It committed once the provider recovered.
- All six round-1 re-reviews then hit the exhausted budget as soon as they were dispatched, and the orchestrator stopped for Marcos (see Questions).
- Two coder permissions were rejected. The first was a probe run whose `tempfile.mkdtemp()` wrote outside the repo, which the coder reran with its temp directory under `orchestration/5.1/`. The second was a request for `/tmp` in fix round 1. The coder also proved both new tests fail by temporarily changing `instruments.py` from a backup under `orchestration/5.1/`. The orchestrator's diff check of `d5c5ded` showed the file restored, and the backup and logs were deleted.

## 5.2 Tabs, tints and gutter bands — 2026-09-28

`ParameterManagerGui` now puts its existing content on tab 0 ("Parameters", `self.parametersTab`) of a `QTabWidget` (`self.tabs`). Tab 1 ("Types", `self.typesTab`) is an empty placeholder for 5.5. The module-level pure function `compute_claims(types, parameters)` in `gui/instruments.py` ports the mock's `claims()`. It takes `PMState.types` and the model's `{path: unit}` rows and returns a `Claim(type, instance, stack)` for every claimed parameter and submodule row. `TypePalette` hands out the five light `TINT_PALETTE` entries (`tint`, `tintAlt`, `bar`) in Type creation order. `ParameterManagerGui.apply_tints` sets `BackgroundRole` on all four columns of each claimed row and clears it on unclaimed ones. The new `ModelParameterManager` adds a fourth logical column (`GUTTER_COLUMN = 3`), which the view shows at visual position 0, 12 px wide, painted by `GutterDelegate`. `test/pytest/test_pm_gui.py` grew from 9 to 25 tests.

### Commit by commit
- `6052b32` The tabs, `compute_claims`, the palette, `ModelParameterManager`, `GutterDelegate` and 15 tests. The orchestrator's coder spec set nine readings:
  - Matching mirrors `instances_of` client-side. Every effective path must exist with the declared unit, compared as strings. The root, any path with a `_globals` segment and an empty Type never match.
  - The Claiming Type is the innermost Instance, then the larger effective set, then the Type name. The name tie-break is not in the mock but matches `types_of`.
  - A Nested Type's entries credit the Nested Type at and below its submodule. So `q01.readout.bw` gets `readout` with stack `["qubit", "readout"]`. The helper `_nested_claim_prefixes` derives the submodule chain the way `params.py` expands the effective set.
  - Palette slots follow creation order. A removed Type frees its slot, a new Type takes the lowest free slot, and slot 0 is reused when all five are taken (the mock's `freeTint`).
  - `tintAlt` goes on odd sibling rows, and the stack is cut to 3 for drawing.
  - The gutter column is added without renumbering columns 0/1/2, through a new `modelType` keyword on `InstrumentParameters` that defaults to `ModelParameters`, so the generic instrument GUI is unchanged.
  - Every live Type edit must avoid creating a parameter, because of the 5.1 crash in the `parameter-creation` branch (TEST_AUDIT.md).

  The coder added four things of its own:
  - The palette helper is `self.typePalette`, not `self.palette`, which would shadow `QWidget.palette`.
  - Recompute has three explicit paths: after `state.refresh` in `refreshAll`/`loadProfile`, `typeChanged` → `_onTypeChanged`, and a new `structureChanged` signal emitted after `parameter-creation`/`parameter-deletion` Broadcasts. `newItem` fires mid-load and `modelRefreshed` fires before `state.refresh`, so neither could be used.
  - `ModelParameters` pins the model to 3 columns after loading, so `ModelParameterManager` widens it again and `_ensureGutterItems` puts back the gutter items.
  - macOS needed `setMinimumSectionSize(GUTTER_WIDTH)`, and the gutter header setup is guarded on `columnCount()`, so 5.1's 3-column D24 stub test still works.

  The tests: eight no-server `compute_claims` tests (unit match, `_globals` at any depth, root, empty Type, innermost Nested Type, two-level nesting ending in stack `["qubit", "readout", "pulse_window"]`, larger set wins, name tie-break), four palette tests, `test_the_parameters_view_moves_into_a_tab_widget`, and two live tests. `test_tints_follow_a_second_clients_type` is the plan's named test. It uses `q01.IF`/`q01.readout.bw` (Hz), `q02.IF` (V) and `other.x`, all created before the GUI. A second Client adds `qubit` with its entries, and the test checks the tint and gutter stack `["qubit"]` on `q01`/`q01.IF`, with none on the wrong-unit and unrelated rows. The tint goes away after `remove_type_parameter` empties the Type and after `remove_type`. `test_refresh_all_recomputes_tints_after_a_model_reload` covers the reload path with the listener stopped. reviewer-qwen confirmed with offscreen Qt probes that the layout re-parenting and the tree branches on the name column work. Orchestrator run: ruff clean, 34 in the three named GUI files, 490 in the full suite.
- `cd39235` Fix from round 0, four items:
  - `test_a_deletion_broadcast_recomputes_the_tints`: `q01.IF`/`q01.bw` exist before the GUI, and the second Client's `qubit` claims both. After `remove_parameter("q01.bw")`, the `q01.bw` row is gone, `q01.IF` has no background on any column and an empty gutter stack, and `q01` is untinted. Nothing had tested the `structureChanged` path. Deletion is safe to test live, since only the creation branch crashes. Both test reviewers raised it (should-fix).
  - The positive tint checks now cover all four items instead of `[:3]`, as "on all columns" asks. This applies to both live tints and the reload test. test-reviewer-qwen raised it as should-fix and test-reviewer-glm as a nit. The `_tint` closure moved to a module helper, `_type_tint`.
  - The tab test now checks the gutter wiring: `visualIndex(GUTTER_COLUMN) == 0`, `sectionSize == GUTTER_WIDTH`, a `GutterDelegate` on the column, `gui.view.gutterDelegate.typePalette is gui.typePalette` and `treePosition() == 0`. Before, deleting `moveSection` or the delegate install would have left every test green. test-reviewer-glm raised it (should-fix).
  - Plan rule 8: the six new non-override methods became snake_case (`apply_tints`, `_on_type_changed`, `_model_parameters`, `_collect_parameters`, `_apply_tints_to_rows`, `_ensure_gutter_items`). Overrides (`insertItemTo`, `updateParameter`, `paint`, `sizeHint`) and the signal name `structureChanged` keep camelCase. Both plan checkers raised it as a nit, and each said the reading's `applyTints()` name and the camelCase GUI module argued the other way. The orchestrator sent it anyway because it is a plan rule. The `src/` diff is renames only.

  All six approved in re-review, and every raiser confirmed their item fixed. Orchestrator run: ruff clean, 35 in the three named GUI files, 491 in the full suite.

### Dropped findings
- The cut of the stack to 3 is never seen, because the deepest test has a stack of exactly 3 (test-reviewer-glm, nit) → not sent.
- The live tests take the expected colour from `gui.typePalette` itself, and the claimed Type always sits in slot 0. The tint/tintAlt parity is not pinned either (test-reviewer-glm, test-reviewer-qwen, nits) → not sent. Reading 8 allowed "tint (or tintAlt)".
- No pixel test of `GutterDelegate.paint` (test-reviewer-qwen nit; the optional part of test-reviewer-glm's wiring finding) → not sent. The fix list said no pixel test was needed.
- `ModelParameterManager.insertItemTo` copies about 10 lines of `ModelParameters.insertItemTo` (reviewer-glm), `TypePalette.sync` is annotated `Any` (reviewer-glm, reviewer-qwen), and the `setColumnCount` round-trip lacks a comment (reviewer-qwen). All nits, not sent; they are still in the code.

### Loose ends
- A `parameter-update` for a parameter the model does not know adds a row through the base update branch without a recompute, so the row stays untinted until the next one (reviewer-glm, and a reviewer-qwen observation). Logged in `decisions.md` for 5.6 polish.
- `apply_tints` reads units from the model's unit column, which only updates on reload. After a second Client's `set_type_parameter_unit`, the recompute uses stale units (reviewer-glm). Logged for 5.5, when unit edits become reachable from the GUI.
- Convention recorded for 5.3–5.6: new non-override GUI methods are snake_case, while Qt overrides and signals stay camelCase. plan-checker-glm suggested that Marcos settle rule 8 against the GUI's camelCase. The orchestrator decided it without asking him, and no answer from Marcos is recorded.
- The tint parity is stored per row item, so re-sorting the tree can put two rows with the same colour next to each other (reviewer-qwen). The mock does the same.

### Process notes
- The coder's shell tool timed out after 150 s on every test run it waited on in line, and the coder took this for pytest hangs. Detached runs writing to logs under `orchestration/5.2/` worked.
- Four permission requests were rejected:
  - the coder's `pkill -9 -f test_gui_navigation`, which would have killed other agents' runs of that file
  - reviewer-qwen's request for `/tmp`
  - reviewer-qwen's inline Qt heredoc, which came through truncated in the prompt
  - a mistyped path outside the repository from test-reviewer-qwen
- The orchestrator session stopped in fix round 1, after the 2026-09-25 implementation commit, while the coder was waiting on a permission prompt. It resumed on 2026-09-28, and the fix commit and re-reviews followed that day.

## 5.3 Lock column, toggle, context menu, arm strip — 2026-09-28

`ModelParameterManager` gains a fifth logical column, `LOCK_COLUMN = 4` ("locked to"), shown between the unit and the delegate column. Its text comes from the pure function `lock_column_text` over `PMState.locks`: `locked to <target>`, `unlocked · <target>` or `target ×N`. Each row's delegate widget has a `lockButton`, visible when the row has a Lock and filled with `LOCK_COLOUR` while locked, which calls `toggle_lock`. The context menu gets "Lock to…" and "Unlock". The new `LockArmStrip` sits under the toolbar and offers the Targets ranked by `rank_lock_targets`, and `ParameterManagerGui.pick_lock_target` shows the Server's error text in it. `ParameterWidget.set_read_only` renders a locked Follower read-only, and `followers_reaching` finds the rows to repaint on a `parameter-update`. `test_pm_gui.py` grew from 25 to 42 tests.

### Commit by commit
- `c215c5c` The column, button, menu entries, arm strip, repaint and 15 tests. The orchestrator's coder spec set sixteen readings. The main ones:
  - Every displayed or compared Target goes through `relative_path`, because `PMLockBluePrint.target` is the full path while `PMState.locks` keys are relative. The Follower text wins over the `target ×N` note, as the mock's `rec.lockedTo || srcNote(p)` does. `target ×N` counts unlocked Locks too, as `followers_of` does.
  - The Lock column is added without renumbering columns 0–3, and `moveSection` puts it at visual index 3. The setup is guarded on `columnCount()` for 5.1's 3-column D24 stub test. `_ensure_gutter_items` became `_ensure_extra_items`, and the tints now cover all five columns.
  - `apply_locks()` is the only writer of the column text, the button's visibility, tooltip and `locked` property, and the read-only flag. It runs after `state.refresh` in `refreshAll`/`loadProfile`, on `structureChanged`, and from the new `_on_lock_changed`, which then repaints the Follower and every row that `followers_reaching` returns.
  - `followers_reaching` follows locked hops only (D7), de-duplicates, and stops on a cycle. `_on_item_new_value` uses it to refresh Follower rows with `setWidgetFromParameter`. The base `onItemNewValue` wiring is unchanged.
  - Cycles are not filtered client-side. The Server's refusal is shown instead.
  - The plan's Design reference says lock.svg/unlock.svg are already in `resource/icons/`. They were not, so the coder copied them from the mock's assets, added them to `resource.qrc` and regenerated `resource.py` with pyrcc5. reviewer-glm found it byte-identical to a fresh run.

  The coder's own interpretations: `LOCK_COLOUR = "#7e5bef"`, the mock's `--log-value` token, taken from its `colors.css` (the spec's fallback `#7b3fa0` was not used). `set_read_only` skips the no-set `QLabel` case so it never re-enables a set button that construction disabled. The menu actions are enabled in an `aboutToShow` slot. `unlock.svg` is registered but unused. The spec said a server-side `ValueError` comes back as the same type. It actually arrives as a generic `Exception`, so `pick_lock_target` catches `Exception`. On Return with a text that matched no candidate, the strip picked `candidates[0]`. The fix commit replaced that.

  The tests: eight no-server tests of `relative_path`, `lock_column_text`, `followers_reaching` (chain, unlocked middle hop, cycle) and `rank_lock_targets`; `test_lock_arm_strip_picks_cancels_and_shows_errors`; `test_parameter_widget_set_read_only`; and five live tests. Those are `test_arm_via_context_menu_pick_a_row_and_toggle` (the plan's named flow: arm via the menu, click the `q02.IF` row, `get_lock` on the Server, toggle both ways, menu Unlock), `test_a_cycle_attempt_shows_the_error_and_stays_armed`, `test_setting_the_target_from_a_second_client_repaints_the_followers` (with the chained `q03.IF`), `test_a_second_clients_lock_shows_in_the_column_and_button` and `test_refresh_all_shows_a_lock_made_while_the_listener_was_stopped`. All parameters are created before the GUI, to avoid the 5.1 `parameter-creation` crash. Orchestrator run: ruff clean, 50 in the three named GUI files, 506 in the full suite.
- `5e83ead` Fix from round 0, nine items:
  - `self.proxyModel.filterFinished.connect(self.apply_locks)`. A filter cycle, or the trash toggle, makes `restoreCollapsedDict` reopen the persistent editors as fresh `ParameterWidget`s, so a locked Follower came back with its button hidden and its input editable. reviewer-glm found it with a Qt probe, and the orchestrator confirmed it in `base_instrument.py`. New test: `test_a_filter_cycle_re_applies_the_lock_state`.
  - `LockArmStrip._on_return_pressed` now ports the mock's `armKeyDown`. An exact candidate is picked; otherwise the completer's first filtered match (`setCompletionPrefix`, then row 0 of `completionModel()`); with no match, nothing. The old code locked "garbage" to the first ranked candidate. reviewer-qwen raised it as should-fix and reviewer-glm as a nit. The orchestrator ruled that reading 10's "first completion" meant the filtered list. The strip test now checks `"garbage"` → nothing and `"q03"` → `q03.IF`.
  - Plan rule 8: `makeLockWidget`, `onLockToActionTrigger`, `onUnlockActionTrigger` → `make_lock_widget`, `_on_lock_to_action_trigger`, `_on_unlock_action_trigger`. plan-checker-glm raised it as must-fix, reviewer-glm as should-fix and plan-checker-qwen as a nit. The pre-existing `makeRemoveWidget`/`onStarActionTrigger` are grandfathered.
  - Test gaps raised by the test reviewers:
    - the `lockChanged` value repaint: `_getMethod()` goes 2.0 → 1.0 → 2.0 across lock, unlock and relock in the named flow (both test reviewers, should-fix)
    - the Lock column's visual index, width (`LOCK_COLUMN_WIDTH`) and header text in the tab test (test-reviewer-qwen should-fix, test-reviewer-glm nit)
    - Escape pressed on the tree, not only in the line edit (test-reviewer-qwen)
    - the completer's `activated` path (both)
    - the `aboutToShow` enabling rule, in the new `test_the_context_menu_lock_actions_enable_by_the_lock_state` (both)
  - A `gap` row in `TEST_AUDIT.md` (see Loose ends).

  All six approved in re-review, and every raiser confirmed their item fixed. test-reviewer-qwen checked that the new `filterFinished` connection runs after the base class's `restoreCollapsedDict` one. Orchestrator run: ruff clean, 52 in the three named GUI files, 508 in the full suite.

### Dropped findings
- The two copied SVGs each carry about 8 KB of C2PA/JUMBF provenance metadata (reviewer-glm, nit) → not sent. It does not change behaviour, and stripping it means regenerating `resource.py`. It is still in both files.
- No test pins the error label's colour to "the existing alert colour" (plan-checker-qwen). The reading was under-specified; reviewer-glm checked that the `red` used matches the design system's `#ff0000` token.
- Round-0 test nits, not sent: the lock button tooltips are unasserted, the diamond de-dup case in `followers_reaching`, and clicking a submodule row while armed.
- Round-1 nits, none sent: the empty-text early return in `_on_return_pressed` is untested (test-reviewer-glm). The `LockArmStrip` class docstring and the strip test's docstring still describe the old Return rule, and the module docstring omits the two new live tests (plan-checker-qwen, test-reviewer-qwen).

### Loose ends
- `TEST_AUDIT.md`, "Parameter Manager GUI — `parameter-update` for a row with no widget": the pre-existing `ParameterManagerTreeView.onItemNewValue` indexes `self.delegate.parameters[itemName]` without a guard and raises `KeyError`. The new `_on_item_new_value` uses `.get` (reviewer-qwen).
- The stale Return docstrings above are still there. The orchestrator suggested that a later task touching `LockArmStrip` refresh them.
- The icons: `decisions.md` flags for Marcos that the plan's Design reference was wrong about lock.svg/unlock.svg. 5.6's qrc check now only has to verify them. No answer from Marcos is recorded.
- The convention from 5.2 was extended: the `on…Trigger` slot family gets no exemption from snake_case in 5.4–5.6.
- 5.2's loose end, where a `parameter-update` for an unknown row adds an untinted row, is untouched.

### Process notes
- The coder sat idle for about 20 minutes after its read pass, with no edits and no message. One nudge in the terminal got it going again, the same pattern as in 2.3.
- The first test-reviewer-glm terminal had no opencode on its PATH, so the dispatch failed with `agent_unconfigured`. The orchestrator closed it and started a new terminal.
- The orchestrator blanked its own list of reviewer handles with a bad shell pipeline. Five reviewers waited on permission prompts for about 10 minutes until the orchestrator swept them.
- Five permission requests were rejected, all inline Python probes that came through truncated in the prompt: one from the coder, and one each from reviewer-glm, reviewer-qwen, plan-checker-glm and plan-checker-qwen. Each reran its probe as a scratch file under `orchestration/5.3/`.
- The watcher's mkdir-prefix rule let the coder's icon `cp` through automatically. The orchestrator would have allowed it anyway, and it tightened the rule afterwards.

## 5.4 Locks panel — 2026-09-28

The Parameters tab now holds `gui.view` and a new `LocksPanel` side by side in a horizontal `QSplitter` (`self.locksSplitter`, stretch 3:2). The panel is hidden until the checkable toolbar action `self.locksAction` (lock icon, `Ctrl+Shift+L`, REGISTRY key `toggle_locks`) shows it. Its rows come from the pure function `build_lock_rows(locks, types, instrument_name)`, which returns `LockRow`s: Targets at depth 0, Type Lock Targets first and labelled `[type: <t>] <target>`, and Followers nested beneath them, recursively for chains. The panel only emits signals, and `ParameterManagerGui` slots (`_on_panel_toggle_lock`, `_on_panel_remove_lock`, `_on_panel_lock_all`, `_on_panel_remove_rule`, `_lock_selection_from_panel`) make the Server calls and show errors or skipped Locks on the panel's `noteLabel`. `test_pm_gui.py` grew from 42 to 53 tests.

### Commit by commit
- `74d2d9f` The splitter, `LocksPanel`, the row model, the per-row controls and 10 tests (shortcuts.py gains one REGISTRY entry, added last because `test_shortcuts.py` pins the first key). The orchestrator's coder spec set thirteen readings. The main ones:
  - The panel keeps `rowWidgets` per path. A locked Follower's value cell is a read-only label whose tooltip names the end of its chain, found by the new `lock_root`, which follows locked hops only (D7). Every other row (plain Target, Type Lock Target, unlocked Follower) gets a `ParameterWidget` doing a plain `set`.
  - Follower rows get a lock/relock toggle and a remove button. Type Lock rows get "lock all" and "remove rule" and use the first `(Type, entry)` pair when there are several, as the mock does. A row that is both a Follower and a Type Lock Target gets only the Type Lock controls.
  - "lock all" passes the entry's stored Target to `lock_type_parameter`, because `target=None` re-points the entry to the Globals default. The skipped paths it returns show as `skipped: <p1>, <p2>` on the note.
  - `refresh_locks_panel` runs at the end of `apply_locks` and `_on_type_changed`, and when the action shows the panel, but only while the panel is shown. `LocksPanel.refresh_values` repaints values in place from `_on_item_new_value` and `_on_lock_changed`, for the same path set they already compute (X plus `followers_reaching`).
  - `selectedLabel` follows the tree's current row. "Lock selection to…" calls `arm_lock` for it, or shows "Select a parameter in the tree first." on a submodule row.
  - Every live test creates its parameters before the GUI, and every live `lock_type_parameter` passes an existing Target (`tshared`), because of the 5.1 `parameter-creation` crash.

  The coder's own choices: 5.3's `make_lock_widget` now builds its button through the shared module-level `make_lock_button` and `lock_button_tooltip`, with the tree's behaviour unchanged (reviewer-glm and plan-checker-qwen checked it). `LockArmStrip` is untouched, so its stale Return docstring from 5.3 stays. Two test-side fixes: one `waitUntil` was racing the rebuild, and `pm.get("q02.IF")` read the proxy's stale parameters dict, so the test uses `pm.q02.IF.get()`.

  The tests: four no-server tests of `build_lock_rows` (a plain Target with a locked and an unlocked Follower, the chain `q03 → q02 → q01` nested with `q02` once, the Type Lock Target sorted first with `type_locks == [("dqubit", "IF")]`) and `lock_root`; `test_the_locks_action_toggles_the_panel`; and five live tests. `test_the_panel_rows_reflect_list_locks_and_remove_from_the_panel` holds the plan's three named tests: the chain's rows and widget kinds, the remove button removing `q03.IF`'s Lock on the Server, a second Client's `other.x` Lock appearing live, and a second Client's unlock flipping `q01.IF`'s toggle and giving it an editor. The others are `test_the_type_lock_rows_lock_all_and_remove_rule`, `test_the_panel_value_editor_sets_the_target`, `test_lock_selection_to_arms_the_tree_row` and `test_a_panel_action_error_shows_on_the_note_label`. Orchestrator run: ruff clean, 62 in the three named GUI files, 518 in the full suite.
- `ad3afba` Fix from round 0, five items:
  - `test_the_panel_value_editor_sets_the_target` now has the second Client set `q02.IF` to 21 and waits for the root editor and `q01.IF`'s read-only label to show it. Neither has a local echo, so a no-op `refresh_values` fails. The second Client's proxy is now built after `_make_live_parameters`, since attribute access resolves through the blueprint fetched when the proxy is built. Both test reviewers raised it (should-fix).
  - New test `test_the_lock_all_note_names_the_skipped_followers`: the second Client re-targets `dq01.IF` to a new root parameter `talt`, and "lock all" shows `skipped: dq01.IF` while `dq01.IF` stays locked to `talt` (D17). The fix list allowed a sibling test instead of extending the Type Lock test. Both test reviewers raised it (should-fix).
  - The Type Lock test now pins the stored Target after "lock all": the entry's `target` stays `tshared`, `dq01.IF` is locked to `tshared`, and no `_globals` parameter exists. Before, a `target=None` call would only have failed indirectly, through the avoided creation crash. It also waits for `gui.state` before the rebuilt-button wait. test-reviewer-glm raised it as should-fix and test-reviewer-qwen as a nit.
  - `test_a_panel_action_error_shows_on_the_note_label` now clicks the panel's toggle button (unlock, then lock again, re-reading the button from `rowWidgets` after each rebuild). Before, only the signal was emitted. test-reviewer-glm raised it (should-fix), and the orchestrator confirmed by grep that no test clicked a panel toggle.
  - Plan rule 2: `build_lock_rows`'s helper `link` became `target_of`, and its docstring and sort comment lost "link" and the mock's "group rows first". The unit test became `test_build_lock_rows_nests_followers_under_a_plain_target`. Both plan checkers raised it as a nit, and both noted that the orchestrator's reading 4 had quoted the mock's names. It was sent because it is a plan rule, as in 5.2 and 5.3. The `src/` diff is wording and the rename only.

  All six approved in re-review with no new findings. Orchestrator run: ruff clean, 63 in the three named GUI files, 519 in the full suite.

### Dropped findings
- On a `pm-lock-update` with the panel shown, `_on_lock_changed` rebuilds the panel (which reads every value) and then `refresh_values` reads the same values again (reviewer-glm, nit) → not sent. Reading 6 prescribes both, and the panel is small.
- The `else path` fallback for the stored Target in `_build_row_widgets` can never run, because `build_lock_rows` only records pairs with a Target (reviewer-glm, nit) → not sent. It is still in the code.
- Test nits, not sent: the multi-Type label `[type: <t1>, <t2>]`, the cycle guards in `build_lock_rows`/`lock_root`, the tooltips, the `Ctrl+Shift+L` keypress and `expandAll` are all unasserted (test-reviewer-glm, test-reviewer-qwen).

### Loose ends
- A successful "Lock selection to…" does not clear a stale error on the note, while the mock clears it on a successful arm (reviewer-qwen). Logged in `decisions.md` for 5.6 polish.
- Text typed into a panel editor but not set is lost on every rebuild (any Lock or Type Broadcast, a creation/deletion Broadcast, a filter keystroke). The tree behaves the same since 5.3, and the mock kept drafts (reviewer-qwen).
- The `LocksPanel` docstring says every Follower row has the toggle and remove buttons, which is not true for a Follower that is also a Type Lock Target (reviewer-qwen).
- The 5.1 `parameter-creation` crash (TEST_AUDIT.md) still means no GUI test covers a Type Lock on the default Globals Target. 5.3's stale `LockArmStrip` Return docstrings are also still there.

### Process notes
- The coder sat idle for about 15 minutes after its read pass, and one nudge got it going, the same pattern as in 2.3 and 5.3.
- Two permission requests were rejected. The coder's `rm -rf orchestration/5.4` would have deleted the orchestrator's files (the 2.4 coder tried the same), so it deleted its own logs by name instead. plan-checker-qwen asked to access opencode's temp directory under `/var/folders`, outside the repo.

## 5.5 Types tab — 2026-09-28

The "Types" tab (`self.typesTab`) now holds a `TypesPane` (`self.typesPane`). It is a horizontal `QSplitter` with three panes: the type list (`typeList`: name, number of Instances, number of effective parameters, tinted from `gui.typePalette`); the entries of the selected Type as a tree (`entriesView`); and its Instances (`instancesView`). Each pane has its own strip and note line. The pane only emits camelCase signals, and `ParameterManagerGui` slots (`_on_pane_*`, `arm_type_lock`) make the Server calls. The rows come from new pure functions: `type_entry_rows` (returning `EntryRow`s), `instances_of_type`, `also_types` and `parse_default_text`. The task also fixed the pre-existing crash in `ModelParameters.updateParameter`'s `parameter-creation` branch, which Marcos approved as an exception to plan rule 6 (see Questions to Marcos). `test_pm_gui.py` grew from 53 to 71 tests.

### Commit by commit
- `7c92542` The creation-branch fix, `TypesPane`, the pure functions, the Type Lock re-target and 17 tests. The orchestrator's coder spec set twelve readings. The main ones:
  - Reading 0, the creation fix. The branch now resolves the element first. On `AttributeError` it calls `self.instrument.update()` (only if the instrument has `update`, that is, a Proxy Instrument) and resolves again. If that also fails, it logs at debug level and adds no row. Before the fix, `update()` ran only when the path was missing from `self.instrument.list()`. That is a remote call, and it already contained the new parameter, so the stale Proxy was never refreshed. The `TEST_AUDIT.md` row "Parameter Manager GUI — live creation from another client" became `fixed`. The module docstring no longer describes the creation trap. reviewer-glm and reviewer-qwen checked the fix against `client/proxy.py` and `helpers.py`.
  - The pane widgets are named attributes, and every string comes from the mock with "source" changed to "target" and "include" changed to "nested type". Own entries get an editable default, whose text goes through `ast.literal_eval` and falls back to the raw string, plus Remove and a Type Lock toggle. The toggle calls `lock_type_parameter` with the Globals default, or `unlock_type_parameter`. While an entry is locked it also shows a re-target button and the relative Target. Nested entries are read-only and show "defined by <type>". Nested submodule rows show `type: <t>`, and a Remove button for the selected Type's own Nested Types.
  - The re-target goes through the arm strip. `arm_type_lock` sets `armed_type_lock`, switches to the Parameters tab and arms the strip with "Target for type <type> · <path>". The candidates are ranked by `rank_lock_targets` with a new optional `arm_rel`. On a pick, `pick_lock_target` calls `lock_type_parameter(type, path, target=picked)`. `arm_lock` and `cancel_arm` clear both kinds of arm. Skipped Locks from either the toggle or the re-target show as `skipped: …` on `entriesNote`.
  - `refresh_types_pane` runs at the end of `apply_tints`. So `refreshAll`, `loadProfile`, `typeChanged` and `structureChanged` all rebuild the panes. The panes also rebuild after every pane action, and the selected Type is kept across rebuilds.

  The coder's own choices:
  - It extracted `_instance_candidates` from `compute_claims` so the new matching could share it; the behaviour of `compute_claims` is unchanged.
  - `type_entry_rows` has a third argument, `instrument_name=""`, used to make stored Targets relative.
  - `requestedType` carries a just-added Type across the gap before its `pm-type-update` Broadcast arrives.
  - A `_building` guard keeps the selection slot quiet during a rebuild.
  - The entries pane calls `deleteLater` on its index widgets before `removeRows`. The instances pane does not (see Dropped findings).

  The tests:
  - Seven no-server tests of `type_entry_rows` (the segment-sorted tree, deeper Nested Types, an unknown Type), `instances_of_type`, `also_types`, `parse_default_text` and `rank_lock_targets` with a Type Lock arm.
  - Four live regression tests for reading 0: a second Client's parameter under an existing submodule and in a new submodule, a second Client's `add_instance` (rows, widgets and tint), and the GUI's own Proxy calling `add_instance`.
  - Six live Types-tab tests. `test_the_types_tab_creates_a_type_and_an_instance` is the plan's named test. It creates Type `qubit`, entry `IF` and Instance `q10` through the widgets, checks `get_type` and `pm.q10.IF` on the Server and the tint on the `q10.IF` tree row, and then shows that a second Client's entry `bw` appears in the pane and as `q10.bw`. The others are `…_edits_entries_and_nested_types`, `…_type_locks_toggle_and_retarget` (the Globals-default Type Lock, now testable live), `…_names_skipped_locks_on_the_note`, `…_show_button_and_also_types` and `…_shows_server_errors_and_empty_names`.

  Orchestrator run: ruff clean, 80 in the three named GUI files, 536 in the full suite.
- `edceebc` Fix from round 0, five items:
  - The named test now inlines the widget steps and asserts the type list's counts: parameters `1`, then `2` after the second Client's `bw`; Instances `0`, then `1` after `q10`. Nothing had asserted those columns before. Both test reviewers raised it (should-fix).
  - The Type Lock re-target failure path: `pick_lock_target("no.such.path")` shows the Server's text on the strip, which stays armed with `armed_type_lock == ("qubit", "IF")`, and the entry's Target is unchanged. test-reviewer-glm raised it as should-fix and test-reviewer-qwen as a nit.
  - The nested strip's "Submodule must not be empty." guard, which had no test (test-reviewer-qwen, should-fix).
  - New `test_instances_of_type_with_a_nested_type`: the Instance matches only when the nested entry is present with the right unit. There is also a truly empty Type in the registry. Before, the empty-Type check passed an unknown name and so tested a different branch. test-reviewer-qwen raised it as should-fix and test-reviewer-glm as a nit.
  - `TypesPane._request_add_entry` now strips the unit text. D12 compares units exactly, so a trailing space would silently leave the Type with no Instances. The edit test types `"Hz "` and checks that the Server stores `"Hz"`. reviewer-qwen called it a nit. The orchestrator kept it because it is a silent matching failure and a one-line fix.

  All six approved in re-review with no new findings. Orchestrator run: ruff clean, 81 in the three named GUI files, 537 in the full suite.

### Dropped findings
- reviewer-qwen said (should-fix) that the instances pane's Show buttons pile up, because `_rebuild_instances` removes rows without deleting their index widgets. reviewer-glm's probe said Qt deletes them. The orchestrator ran its own probe: once deferred deletes are flushed, no widgets pile up. reviewer-qwen's probe had only called `processEvents`. Not sent. In round 1, reviewer-qwen agreed after a probe with a real event loop. Its matching note about the 5.4 `LocksPanel` fell with it. The entries pane's `deleteLater` is therefore redundant but harmless.
- Not sent: the creation branch's "cannot resolve → no row" guard is untested, and several one-line cell checks are missing: the unit column, the Target label, the Return commit, and `.locked` after toggle-off (test-reviewer-glm N2, N3).
- Also not sent: the nested-Type combo offers Types that would form a cycle, and the Server's refusal shows instead (plan-checker-qwen). The word "source" in `arm_type_lock`'s docstring means Qt's source model (plan-checker-qwen). Width comments quote the mock's numbers (plan-checker-glm).

### Questions to Marcos
- The named test needs parameters created while the GUI is open, which hits the 5.1 crash logged in `TEST_AUDIT.md`. The orchestrator's probe showed that every creation shape failed and that a forced `update()` fixed them all. Should 5.5 fix it as an exception to plan rule 6? → "fix it in 5.5".

### Loose ends
- The entries note is not cleared after a clean re-target, so a stale error or `skipped:` line can stay (reviewer-glm, reviewer-qwen). With no Type selected, the strips silently do nothing, and the labels read "parameters of " (reviewer-glm). All three are logged in `decisions.md` for 5.6 polish, next to 5.4's stale-note loose end.
- `test_a_deletion_broadcast_recomputes_the_tints` still has a stale docstring saying creation "stays off-limits" (test-reviewer-qwen).
- 5.2's loose end about stale units after `set_type_parameter_unit` is still open. The Types tab has no unit editor, so the GUI cannot reach it yet.
- A stray untracked profile, `parameter_manager-parameter_manager.json`, sat in the repo root: parameters `hello.salud`/`salud`, unit `q`, a Lock, apparently from a manual GUI run. Every `ParameterManager` built in the repo root loads it, which made `test_pm_locks.py` fail (2 failures). The coder asked whether to delete it. The orchestrator said no, because it is Marcos's data, and kept it moved aside at `orchestration/5.5/stray-parameter_manager-parameter_manager.json` (git-ignored). It is flagged for Marcos: a profile file in the repo root breaks the suite.

### Process notes
- The coder sat idle after its read pass, and one nudge got it going, the same pattern as in 5.3 and 5.4.
- The coder moved the stray profile out of the repo root first and asked about it afterwards. The orchestrator had allowed the move because it could be undone.
- Three permission requests were rejected: test-reviewer-qwen (twice) and plan-checker-glm asked to access opencode's temp directory under `/var/folders`, outside the repo.

## 5.6 Delete-Target confirmation and polish — 2026-09-28

`ParameterManagerGui.removeParameter`, where both the row's delete button and the `delete_item` shortcut end up, now asks the Server for `followers_of(fullName)`. When the parameter has Followers, it shows a `QMessageBox` (`self.removalDialog`, object name `removalDialog`, title "Remove Target?") with the text "Removing <path> also removes the Locks of:" and one `<follower> (locked|unlocked)` line per Follower. The box has Ok and Cancel, Cancel is the default, and Cancel returns without calling the Server. Three REGISTRY entries were added to `gui/shortcuts.py`: `lock_to` (Ctrl+L, `_lock_current_item`), `unlock_item` (Ctrl+U, `_unlock_current_item`) and `show_types` (Ctrl+Shift+Y, `_toggle_tabs`). The task also closed the polish loose ends that 5.3–5.5 had logged for it. `resource.qrc` already listed `lock.svg`/`unlock.svg`, so it was not changed. This task closes Phase 5.

### Commit by commit
- `f4923e3` The confirmation, the shortcuts, the polish and five new tests. The orchestrator's coder spec set seven readings. The main ones:
  - If the `followers_of` call raises, the Followers are computed on the client instead, from `self.state.locks` (locked and unlocked alike, with Targets compared through `relative_path`). The locked/unlocked label on each line comes from the state.
  - The shortcuts are appended after `toggle_locks`, so `jump_filter` stays the first key. `register_tooltip` puts the key in the tooltips of `view.lockToAction` and `view.unlockAction`. Ctrl+L and Ctrl+U do nothing on a submodule row or when nothing is selected, and Ctrl+U also does nothing unless the Lock is locked. None of the three keys collides with a REGISTRY entry or a hard-coded `QShortcut`.
  - Polish:
    - (a) `ModelParameterManager.updateParameter` now emits `structureChanged` when a `parameter-update` adds a row the model did not know. It compares the new `_has_row` before and after, so the new row gets its tint and gutter band right away.
    - (b) A successful "Lock selection to…" resets `locksPanel`'s note, and a Type Lock re-target that skips nothing resets `typesPane`'s entries note.
    - (c) With no Type selected, the three Types-tab strips are disabled and the labels read "parameters"/"instances".
    - (d) Four stale docstrings were fixed: `LockArmStrip`, the arm-strip test, `LocksPanel`, and `test_a_deletion_broadcast_recomputes_the_tints`.

  The tests:
  - `test_removing_a_target_confirms_and_cancel_keeps_the_server_untouched`, the plan's named test. It cancels on both delete paths and checks that `has_param`, `get_lock` and the state are unchanged after a wait. The Ok path then drops the Target, the Lock and the Lock column. A parameter without Followers is removed with no dialog.
  - `test_the_lock_shortcuts_are_in_the_registry` and `test_the_lock_shortcuts_arm_unlock_and_switch_tabs`, which uses real `qtbot.keyClick`s.
  - `test_lock_and_unlock_icons_ship_in_the_resources`, which runs without a server.
  - `test_a_parameter_update_for_an_unknown_row_recomputes_the_tints`.
  - One-line assertions for (b) and (c) in existing tests.

  The plan's manual end-to-end check was done as a script instead, because no worker can run a GUI by hand (see Loose ends). The scratch script `orchestration/5.6/e2e_param_manager.py` started an in-process Server on a free non-default port and built the GUI with the same wiring as `apps.parameterManagerScript`. A second Client then made changes, and all five checks passed ("e2e PASS 5/5"): the broadcast-listener probe, the tree row appearing, the value widget repainting, the Lock column and lock button updating, and the tint appearing. The script was deleted afterwards. Orchestrator run: ruff clean, 103 in the four named GUI files, 542 in the full suite.
- `e32078a` Fix from round 0, four items:
  - New `test_removing_a_target_falls_back_to_the_client_side_followers`. It monkeypatches the Proxy Instrument's `followers_of` to raise, and checks that the dialog still names `q01.IF (locked)` and that Cancel leaves the Server untouched. test-reviewer-glm raised it as should-fix and test-reviewer-qwen as a nit.
  - The named test gains a second Follower, `q03.IF`, whose Lock is unlocked. It asserts `q03.IF (unlocked)` and that Cancel is the default button. test-reviewer-qwen raised it as should-fix and test-reviewer-glm as a nit. test-reviewer-qwen's round-1 probe confirmed that under PyQt5 `defaultButton()` returns the widget, so the identity check is valid.
  - `removalDialog` goes back to `None` once `exec()` returns, on both paths, as its docstring says. reviewer-glm, reviewer-qwen and plan-checker-qwen all raised it as a nit. The orchestrator sent it because the code stated something false.
  - The `known_row`/`added_row` guard now treats `PARAMETER_CALL` like `PARAMETER_UPDATE`, since the base branch adds a row for both. The `structureChanged` docstring now names both cases, and the polish test also drives a `parameter-call` for `q03.IF`. Both general reviewers raised it as a nit. Reading 5(a) had named only `parameter-update`, and plan-checker-qwen noted the same gap as out of scope.

  All six approved in re-review. The round-1 fix list is empty. Orchestrator run: ruff clean, 104 in the four named GUI files, 543 in the full suite.

### Dropped findings
- Not sent (test-reviewer-glm F3): Ctrl+L with no current row at all is untested (only the submodule-row no-op is), and the key hints in the two actions' tooltips are not asserted.
- Not sent (test-reviewer-qwen F3): the second Ctrl+U press, the one on an already-unlocked Follower, does not set the current row again first, so it might pass without testing anything. test-reviewer-glm noted that it could not fail anyway, because the Server's `unlock` of an unlocked Lock is a no-op.
- Round-1 nit (test-reviewer-qwen): the GUI test does not assert that `q03.IF`'s unlocked Lock is dropped on Ok. The 3.3 deletion-interplay tests cover that at the API layer.

### Questions to Marcos
- The coder asked (through the orchestrator) what to do because macOS ignores `QMessageBox.setWindowTitle`, so asserting the title would fail there. → Answered by the orchestrator, not Marcos: keep the `setWindowTitle` call, and have the tests check the object name `removalDialog`, the text and the standard buttons instead.

### Loose ends
- Flagged for Marcos: the plan asked for a manual end-to-end check, and a script stood in for it. A by-hand run is still worth doing once: `instrumentserver --port 5600`, then `instrumentserver-param-manager --port 5600`, and a second Client changing a value. The plan asks for the result to be noted under the task. It is recorded in `orchestration/5.6/decisions.md`, but it was not yet in the plan at `e32078a`, where the task still reads `[~]`.
- Still open from earlier tasks: 5.2's stale units after `set_type_parameter_unit`, and 5.4's text lost from a panel editor on rebuild.

### Process notes
- The coder's first named-test run hung, because a modal dialog blocked pytest before the `QTimer`-driven canceler was in place. The coder profiled its own pytest with `sample` and killed it by pid.
- The orchestrator deleted run logs the coder had left behind.

## 6.1 User Guide: `docs/user_guide/parameter_manager.md` — 2026-09-28

The stub `docs/user_guide/parameter_manager.md` is now the full User Guide page. It has eight level-2 sections: "Concept", "Hierarchical parameters", "Types", "Locks", "Type Locks and Globals", "Profiles and files", "The GUI" and "Using it from measurement code". The GUI section has five screenshot placeholders and a keyboard shortcuts table. The verification script `test/docs_verification/user_guide/verify_parameter_manager.py` has one `section_*` function per page section and uses only the shared helpers. It runs in a throwaway `verify_pm_*` directory, so no profile file is left behind. The task added three docstring rows and one tests row to `TEST_AUDIT.md`, and changed no source code. This task opens Phase 6.

### Commit by commit
- `da417a9` The page, the script and the `TEST_AUDIT.md` rows. The orchestrator's coder spec set seven readings. The main ones:
  - Reading 1 defined "following the docs protocol" (plan rule 9). The script exercises every claim before it goes on the page. The site builds with no new warnings. The style rules of `PLAN_docs_refactor.md` apply. Screenshots are placeholder admonitions with light/dark paths under `docs/_static/user_guide/parameter_manager/`. The six reviewers stand in for the docs plan's GRILL/REVISE loop with Marcos, and the coder commits (the standing exception on this worktree). The orchestrator flagged this reading for Marcos in `decisions.md`.
  - Reading 2 names the script `verify_parameter_manager.py`, following the docs convention `verify_<page>.py`. The plan text's `parameter_manager.py` is treated as a slip, and this is recorded in `decisions.md`.
  - Reading 3 fixed the section order and what each section covers. Reading 5 sent docstring problems to `TEST_AUDIT.md` rows instead of edits. The rows added are `ParameterGroup.has_param` (no docstring), `ParameterGroup.get`/`set` (no docstrings, and on a Proxy Instrument they resolve to QCoDeS' local `InstrumentBase.get`/`set`), and `ParameterManager.fromFile` (it documents `deleteMissing` but never forwards it, and it names a file the code never uses). A tests-table row was added for "Type Locks and Globals".

  At the start, `sphinx-build` was missing from the uv environment. `uv run --group docs` (the same as CI's docs group) fixed that. "Zero Sphinx warnings" was read as "none from this page": the build still shows 3 ADR toctree warnings that were there before, and they are left for 6.3. Orchestrator run: ruff clean, script 8/8 sections OK, docs build with only the 3 old warnings, 543 in the full suite.
- `d1dcd42` Fix from round 0, eleven items. Every reviewer asked for changes:
  - The Globals note was wrong, and so was the tests row that repeated it. They said QCoDeS reserves underscore names, so attribute access cannot reach `_globals`. The orchestrator's probe showed that attribute access does work, on a fresh Proxy or after `pm.update()`. Only a Proxy built before the Globals parameter existed raises `AttributeError`, because its Blueprint is cached. What is really unavailable is the dotted `pm.get`/`pm.set`: on the Proxy these are QCoDeS' local shorthands, and a dotted path raises `KeyError`. That is why the page uses `Client.call`. The note, the `TEST_AUDIT.md` row and the script's four assertions now say this. Raised by reviewer-glm, reviewer-qwen, test-reviewer-qwen and plan-checker-qwen (must-fix). test-reviewer-glm's request to assert the `AttributeError` was reworded to the stale-Proxy case.
  - The page claimed the Server window shows the Parameter Manager widget. It opens the generic instrument widget unless the station config's `gui` entry names `instrumentserver.gui.instruments.ParameterManagerGui`, as `serverConfig.yml` does. The page now says so, and presents the launcher as the sure way to get the widget. Raised by plan-checker-glm, reviewer-glm, test-reviewer-qwen and plan-checker-qwen.
  - Three GUI wordings were fixed to match what shipped in 5.3–5.5:
    - The gutter bands go outermost first, up to three.
    - The arm strip lists the same relative path on another Instance first, then paths containing it, then the rest.
    - On a locked Type entry, the re-target button and the Target path sit beside the Type Lock toggle. The page had said the toggle doubles as the re-target button.

    Each was raised by three or four of the general reviewers and plan checkers.
  - "Profiles and files" now starts with the `add_parameter`/`lock` block the script runs, so you can reproduce the shown document from an empty Parameter Manager (test-reviewer-qwen, reviewer-glm, plan-checker-qwen). `refresh_profiles()` is shown as `sorted(...)`, because the API returns the files in directory order (both test reviewers and reviewer-qwen). The `deleteMissing=False` example did nothing, since it loaded a document that omitted nothing. It became a document with `temp.extra` dropped, loaded both ways (plan-checker-qwen, a nit sent because the docs plan asks for concrete examples).
  - Legacy note. reviewer-glm and test-reviewer-glm disagreed about whether a Lock survives the legacy load. The fix list had the script observe what happens and the prose match it. The page now shows a legacy flat file loading, and the note says the reader writes no Types and no Locks. Parameters the file does not list are removed, and their Locks with them. A Lock whose parameters stay is untouched.
  - New script assertions for page claims that nothing checked yet. The default `remove_parameter` prunes the emptied Parameter Group. `add_instance` keeps an existing value and unit. A submodule with the wrong unit is not an Instance. `remove_type` of a Nested Type is refused. A Globals parameter is saved in the profile. One `pm-type-update` Broadcast per Type edit, and one `pm-lock-update` per Lock method. The D8 refusal of a cross-manager `lock`. Raised mainly by test-reviewer-glm (must-fix), with test-reviewer-qwen, reviewer-glm, reviewer-qwen and plan-checker-qwen.
  - Two one-line wordings. The Parameter Manager logs the skipped-Instance warning, not the Server. Ctrl+Shift+Y switches between the two tabs.

  Orchestrator run: ruff clean, script 8/8, same 3 build warnings, 543 in the full suite.
- `b8a99d2` Fix from round 1, two items, script only:
  - `d1dcd42` had moved the `remove_lock("q02.IF")` capture ahead of the Target deletion. That dropped the check that a Follower of a surviving Target keeps its Lock, and it left a muddled comment. The script now deletes `q01Data.IF`, asserts `q01.IF` is unlocked with its own value `5000000.0` and that `q02.IF` is still locked to `q01.IF`, and only then captures the one `pm-lock-update` from `remove_lock`. Raised by test-reviewer-glm (must-fix), test-reviewer-qwen (should-fix), reviewer-glm and plan-checker-glm.
  - `capture_one_broadcast` returned the snapshot that `cap.wait_for(1)` took when the first message arrived, so its 0.2 s sleep never affected the four `count == 1` checks. It now returns `list(cap.messages)` after the sleep, inside the `with` block. reviewer-qwen raised it alone, and the orchestrator confirmed it in `helpers.py`.

  All six approved in round 2 with no findings. Orchestrator run: ruff clean, script 8/8, same 3 build warnings, 543 in the full suite.

### Dropped findings
- The page speaks in the present tense about pages that are still stubs: "the Technical Guide page above lists them all" and "server.md explains where profile files end up" (reviewer-glm N2, plan-checker-qwen F6). The links resolve, so this was left for 6.3's final pass. The same nit came up again in round 1 and was not sent.
- Round 2, plan-checker-qwen, not blocking: surviving a restart is covered only indirectly, and `unlock`/`relock`/`lock_type_parameter` have no Broadcast captures of their own.

### Loose ends
- The five screenshot placeholders (tree with tints, arm strip, Locks panel, Types tab, delete confirmation) are waiting for Marcos to capture them. Each has a ready-to-uncomment `{image}` pair next to it.
- 6.3 should fix the 3 ADR toctree warnings and re-check the stub-page forward references once 6.2 and `server.md` are written.
- New `TEST_AUDIT.md` gaps: the `has_param`, `get`/`set` and `fromFile` docstrings. The `fromFile` row points out that `deleteMissing` never reaches the loader, and the page documents that behaviour with a note. The stale-Proxy `AttributeError` on `_globals` has no direct pytest.

### Process notes
- plan-checker-qwen wrote its round-0 report but did not send worker_done. One nudge with the exact send command fixed it.
- The watcher's local-port-check rule auto-allowed a chained command from test-reviewer-qwen that also ran an unscanned probe (`probe_shadow.py`). The probe was scanned afterwards, and the rule now rejects chained commands.
- Two permission requests were rejected. test-reviewer-qwen tried to `rm -rf docs/build`, which is shared with the other reviewers, and redid its cleanup without it. plan-checker-qwen mistyped a path outside the repo.
- All six reviewers run the verification script on the helpers' fixed port, so in round 2 several found the port busy. They waited or retried in loops. The `verify_pm_*` directories they saw belonged to other reviewers' runs, not leaks.

## 6.2 Technical Guide: `docs/technical_guide/broadcasts.md` — 2026-09-28

The stub `docs/technical_guide/broadcasts.md` is now the full Technical Guide page. It has six level-2 sections: "What triggers a Broadcast", "The wire format", "SubClient", "External forwarding", "The Broadcaster contract" and "The Parameter Manager's actions". It links to the User Guide's Parameter Manager page, `server.md`, `monitoring.md` and `blueprints_and_proxies.md`. The verification script `test/docs_verification/technical_guide/verify_broadcasts.py` has one `section_*` function per page section and runs in a throwaway `verify_broadcasts_*` directory. The shared helpers gained `capture_raw_frames` and `RawFrameCapture`, a plain `zmq.SUB` on its own thread, because `capture_broadcasts` decodes inside the `SubClient` and never hands over the raw frames. The task added seven docstring rows and one tests row to `TEST_AUDIT.md`, and changed no source code.

### Commit by commit
- `44141d8` The page, the script, the helper and the `TEST_AUDIT.md` rows. The orchestrator's coder spec set eight readings. The main ones:
  - Reading 1 carried over 6.1's meaning of "following the docs protocol": the script exercises every claim first, no build warnings from this page, the docs plan's style rules, the reviewers in place of GRILL/REVISE, and one commit by the coder.
  - Reading 2 named the script `verify_broadcasts.py`, since the plan gives only the folder.
  - Reading 3 fixed the six sections and what each covers. The wire format is shown twice: as the two raw frames a plain SUB socket receives (topic = instrument name, then the JSON of the `ParameterBroadcastBluePrint` dict with `_class_type`), and as the Blueprint that `decode`/`deserialize_obj` rebuild from it.
  - Reading 6 verifies external forwarding in-process: `startServer(ipAddresses={"externalBroadcast": "tcp://127.0.0.1:<free port>"})` through the helpers' `server(**kwargs)`, and a raw SUB on that address that receives the same two frames as the main socket.
  - Reading 5 sent docstring problems to `TEST_AUDIT.md` instead of edits. The docstring rows are `base.sendBroadcast` (`:param messages:` for a parameter named `message`), `base.recvMultipart` ("Recieves" and garbled wording), `SubClient.__init__` (the `sub_port` "should not be changed" note is wrong for any non-default Server), the `SubClient.update` signal comment (it names two of the six actions), `ParameterBroadcastBluePrint` (it omits the `PMTypeBluePrint` payload), `StationServer._broadcastParameterChange` (it does not mention the external socket) and `startServer` (no parameter docs at all). The tests row: no pytest starts a Server with an external Broadcast address.

  Orchestrator run: ruff clean, script 6/6 sections OK, docs build with only the 3 old ADR warnings, 543 in the full suite. The script's log also shows a non-fatal `NotImplementedError` traceback from the Server asking the config-loaded `DummyBroadcasterInstrument` for its IDN.
- `da12f46` Fix from round 0, four items. The commit message says "round 1", but the fix list is `round-0/fix-list.md`. Five of the six reviewers asked for changes, and plan-checker-qwen approved with five nits:
  - The page said registering the same sink twice means receiving everything twice, and nothing checked it. The script now adds the sink twice, sees two deliveries, removes it once and sees one more delivery, then removes it again and sees none. The page adds "removing it once leaves it registered once". Raised by plan-checker-glm, reviewer-qwen, test-reviewer-glm (must-fix) and test-reviewer-qwen.
  - The `pm-lock-update` and `pm-type-update` payloads had been checked only by `action` and the inner `_class_type`. Both are now compared as complete dicts equal to the page's two examples (`"locked": "True"`, `"target": "None"`, the `effective` map and so on). Both test reviewers raised it (should-fix).
  - `add_nested_type` creates parameters as a side effect (`params.py` calls `_broadcast_parameter_creation` there), but the page left it out of the list of side-effect creators, and four Type-editing methods had no capture. The page now lists it and gives its order: `parameter-creation`s, then the applied Type Locks' `pm-lock-update`s, then one `pm-type-update` per affected Type, the edited Type first. The script now asserts one `pm-type-update` each for `set_type_parameter_unit`, `remove_type_parameter` and `remove_nested_type`, and the `add_nested_type` order on Type `qubitline` with Instance `ql01` and a Nested Type `pulse` that carries a Type Lock. Raised by plan-checker-glm, reviewer-glm (must-fix), test-reviewer-qwen (should-fix) and plan-checker-qwen.
  - Five one-line wording fixes. By severity these were nits, but each was a factual slip on a wire-format page, and a fix round was happening anyway:
    - A "next section" pointer that was two sections off.
    - Frame 2 carries only the scalar fields as strings. A Blueprint `value` travels as a nested dict.
    - The fan-out claim now says two SUB sockets each received the frames, which is what the script runs.
    - `lock_type_parameter`/`unlock_type_parameter` are no longer called "Lock methods and Type methods at once". `unlock_type_parameter` removes only the rule and touches no Lock.
    - The GUI's `SubClient` receives every Broadcast of its own instrument, not every Broadcast.

  All six approved in round 1. Orchestrator run: ruff clean, script 6/6, same 3 build warnings, 543 in the full suite.

### Dropped findings
- The page's opening sentence names the Server's own GUI as a subscriber (reviewer-glm). Not sent: its embedded instrument widgets, such as `ParameterManagerGui`, do subscribe with a `SubClient`, and `how_it_works.md` uses the same wording.
- Not sent from test-reviewer-glm: the page's claim that emission happens under the held instrument mutex is not observed directly (hard to test cleanly), and `hasattr` versus `isinstance` registration cannot be told apart (no duck-typed instrument class exists).
- Style nits not sent: lowercase "client" in four places (the site is mixed, and `quickstart.md` uses lowercase), and "the instrument's instrument mutex" (both reviewer-qwen).
- Round-1 nit (test-reviewer-qwen): the "edited Type first" order among several affected Types is pinned by reading the code only. The script's scenario has a single affected Type.

### Loose ends
- The eight new `TEST_AUDIT.md` rows listed under `44141d8` are open `gap`s.
- 6.3 still owes the 3 ADR toctree warnings and the check of forward references to stub pages. 6.2's page is now written, and `server.md` is next.
- The non-fatal IDN `NotImplementedError` traceback from `DummyBroadcasterInstrument` shows up in every script run. Nothing tracks it.

### Process notes
- All six reviewers run the script on the helpers' fixed port, so the port contention seen in 6.1 got worse: in both rounds, reviewers spent long stretches in wait-and-retry loops. In round 1 the orchestrator told the five still retrying to rely on its own passing run at `da12f46`. It also rejected reviewer-glm's 200-attempt tight retry loop, which would have starved the shared port.
- A killed reviewer run left an empty `verify_broadcasts_vd8xyzcn/` directory. test-reviewer-qwen's probe showed that the script's `workspace()` does clean up when the port is taken, so this was not a script bug. test-reviewer-qwen removed the directory with the orchestrator's approval.
- The coder's inline heredoc Python probe was rejected, because the spec allows probes only as files under `orchestration/6.2/`. It redid the probe as a file.

## 6.3 Bookkeeping — 2026-09-29

This task closes the plan's paperwork. `PLAN_docs_refactor.md` now lists the sections the two new pages actually have, all done. `TEST_AUDIT.md` gained six tests rows for gaps and defects that earlier tasks had left without one. `CONTEXT.md` and ADRs 0002 and 0003 were corrected where they no longer matched the shipped behaviour. Two leftovers from 6.1 were also closed: `'adr'` joins `exclude_patterns` in `docs/conf.py`, so the three ADR toctree warnings are gone and the docs build has zero warnings, and the User Guide's forward reference to `server.md` was reworded. No source code, tests or verification scripts changed.

### Commit by commit
- `966f961` The bookkeeping, one commit across seven files. The orchestrator's coder spec gave seven readings. The main ones:
  - Reading 1: in the docs plan, replace each page block's bullets with its level-2 sections, all `[x]`. `parameter_manager.md` now has eight bullets and `broadcasts.md` six. The docs plan keeps no record of finished pages beyond the checkboxes.
  - Reading 2: add `TEST_AUDIT.md` rows only for gaps that have no row yet, and edit an existing row only if its state is wrong. Four rows were added:
    - `covered`: the side-effect `parameter-creation`s, `add_nested_type` included, pinned by seven tests in `test_pm_types.py`.
    - `waived`: the claim that a Broadcast is emitted while the instrument mutex is held, which 6.2 dropped.
    - `gap`: `hasattr` versus `isinstance` registration, since there is no duck-typed instrument to test with.
    - `gap`: the 4.3 loose end that `does_profile_exist` matches by substring.

    The "Profiles — loading a file" row keeps its `gap` state, and its notes now open by calling it a product defect left open: `fromFile` ignores `deleteMissing`. The 5.5 creation-branch row already read `fixed`. The stale-Proxy `AttributeError` was already in the notes of the Type Locks and Globals row, so it got no new row.
  - Reading 3: the glossary may get wording fixes only. Three entries changed:
    - Broadcaster: the `None` payloads, and "it emits no `parameter-deletion`". The old text said the Parameter Manager re-emits deletions, but `params.py` never emits one. That makes D22's deletion clause empty: nothing removes parameters as a side effect.
    - Target: the tree marks Targets and counts their Followers whether the Locks are locked or unlocked, and deleting a Target also clears Type Lock rules.
    - Globals: `add_parameter` refuses the name, and a Globals parameter can otherwise be read, set and saved like any other.
  - Reading 4: an ADR may change in its Consequences only. ADR-0002 gained the Type Lock clearing on Target deletion. ADR-0003's second bullet was rewritten: no `parameter-deletion`, and no creation or deletion Broadcasts from a profile load or from `remove_all_parameters`. ADR-0001 was checked and left unchanged. Before review, the orchestrator confirmed in `params.py` that `_broadcast_parameter_creation` is called from exactly four places.
  - Reading 6: "the Technical Guide page above lists them all" is true now that `broadcasts.md` is written. The `server.md` sentence was reworded to say that profile files end up in the Server process's working directory, which the page already states, and to link `server.md` only as the Server's page.

  The coder left the 1.3 dict-response loose end without a row, arguing that 1.3's `BluePrintType` branch had superseded it. It also flagged the `does_profile_exist` row as a judgment call. Orchestrator run: ruff clean, both scripts all sections OK, docs build with zero warnings, 543 in the full suite.
- `d59ad5f` Fix from round 0, four items, in three files:
  - The Globals entry now names the second way its parameters get created: "by a Type Lock or by a profile load that lists one" (`fromParamDict` calls `_create_managed_parameter`). test-reviewer-glm raised it as should-fix and reviewer-glm as a nit.
  - New `gap` row for the 1.3 loose end. `ServerResponse.toJson` still sends a top-level dict as `str(dict)` (`blueprints.py` :770-773), so a value containing a quote does not survive the trip, and `list_locks` is the documented case. Only the happy path is pinned. The commit shows the coder's "superseded" reading was wrong: 1.3's branch fixes Blueprint values inside the dict, not the top-level `str()`. Raised by both test reviewers (should-fix).
  - New `gap` row for the 1.2 loose end. A Parameter Group that foreign code attaches through `add_submodule` keeps `_root = None` and skips routing. A plain `Parameter` can be a Target but not a Follower. Raised by test-reviewer-qwen (should-fix).
  - A bullet in the docs plan was renamed to "External forwarding", to match the page's section title (plan-checker-qwen, a nit sent because a fix round was happening anyway).

  All six approved in round 1. Orchestrator run: ruff clean, both scripts OK, zero build warnings, 543 in the full suite.

### Dropped findings
- The Target entry's "marked as such in the tree" leaves out the GUI rule that a row that is both Follower and Target shows its Follower text (reviewer-qwen, plan-checker-qwen). Not sent: the wording predates this task, and the User Guide page documents the rule.
- The Claiming Type entry leaves out the code's final tie-break by Type name. The coder left it alone because neither page documents it.
- Round 1 (reviewer-qwen, test-reviewer-glm): the new "Hierarchical parameters" row's Page column reads `user_guide/parameter_manager.md (future)`, although the page exists. The marker was copied from the fix list, and older rows carry it too. Not sent, and flagged for Marcos as a one-word cleanup.

### Loose ends
- Four of the six new `TEST_AUDIT.md` rows are open `gap`s. The other two are the `covered` and `waived` rows. `fromFile` ignoring `deleteMissing` and the `does_profile_exist` substring match are product defects that were left unfixed.
- The `(future)` markers in the `TEST_AUDIT.md` Page column are now inconsistent and could be cleaned up in one pass.
- `server.md` is still a stub. The User Guide no longer promises anything specific from it.

### Process notes
- Two reviewer docs-build requests were rejected. plan-checker-glm aimed at the same build folder as reviewer-glm, and reviewer-qwen used cwd-relative paths that would have landed outside `round-0/`. Both retried with their own explicit paths.
- plan-checker-qwen created a stray `docs/orchestration/6.3/round-0` directory by mistake and removed it with approval.
- The port contention on 5555 continued: several reviewers ran the User Guide script in sleep-and-retry loops in both rounds.
