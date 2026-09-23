# 0.2 — test-reviewer-qwen — round 0

Verdict: changes-needed

## Findings

### F1 — should-fix
- Where: test/pytest/test_broadcaster.py (gap; belongs next to the sink registration tests, lines ~27–58)
- What: The commit documents, in the `Broadcaster` class docstring, that "adding the same sink twice makes it receive every Broadcast twice", and the coder flagged no-deduplication as an explicit judgement call, but no test pins this behaviour down.
- Why: The plan says "sinks stored in a list" (task 0.2), and task 0.3 makes the Server register itself as a sink per instrument — a double registration would silently double every wire broadcast to all GUIs and Listeners. Without a test, a future "fix" that deduplicates (or a change to `remove_broadcast_sink`, which removes only the first matching entry) would pass CI while changing the contract the next task builds on.
- Suggested fix: Add `test_adding_the_same_sink_twice_delivers_twice`: setup — one `Broadcaster`, add the same sink (e.g. `received.append`) twice; action — one `broadcast(make_bp())`; expected — the sink receives the blueprint twice (`len(received) == 2`), and one `remove_broadcast_sink` call leaves one active sink (a second broadcast is still delivered once).

## Notes

- Tests run: `uv run pytest -q test/pytest/test_broadcaster.py` → `8 passed in 0.01s`. Full suite: `uv run pytest -q` → `169 passed, 4 warnings in 58.55s`.
- Per-test check (all 8 tests in the new file): each would fail if the feature were broken — no-sink no-op fails if empty fan-out raises; single-sink/reach tests fail if `broadcast` skips sinks; ordering test fails if fan-out order changes; the exception test fails both if the exception is not logged (asserts exactly one ERROR record on `instrumentserver.base` with `exc_info` set, and that the message names the failing sink) and if it stops the remaining sinks (`received == [bp]`); removal tests fail if removal is a no-op. `test_parameter_manager_is_a_broadcaster` / `test_parameter_manager_broadcast_reaches_sink` fail if the mixin is not mixed into `ParameterManager` (also exercises the `Broadcaster.__init__` → `ParameterGroup.__init__` MRO chain on a real construction).
- Layer and naming: all tests are server-free unit tests, matching the task's "unit part" of `test_broadcaster.py` (the server part is task 0.3). Names use the plan/CONTEXT vocabulary (Broadcast, sink, no-op, Broadcaster); the module docstring correctly defers the server part to a separate task.
- Quoted-annotation fix is covered indirectly: the three new public methods appear in `dir(ParameterManager)` and are not shadowed by the qcodes base class, so `bluePrintFromInstrumentModule` includes them and every test that builds a Parameter Manager proxy (`param_manager` fixture in `test_param_manager.py`, `test_basic_functionality.py`) execs the new signature strings in `_makeProxyMethod`. I verified `str(inspect.signature(...))` renders the quoted annotations as string literals, which the client's `exec` accepts; the full-suite pass confirms it. An explicit proxy-level test for `broadcast` lands with task 0.3, as planned.
- Considered, not findings: sink removed mid-broadcast (the implementation iterates a copy of the list; the plan does not require this edge) and passing a wrong-typed blueprint to `broadcast` (plan does not require it). "No emissions yet" on `ParameterManager` is a scope rule, not a named test — left to the plan checker.
- No pre-existing tests were weakened, deleted or skipped by this commit; it adds one new test file only.
