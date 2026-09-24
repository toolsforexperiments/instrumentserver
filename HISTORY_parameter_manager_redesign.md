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
