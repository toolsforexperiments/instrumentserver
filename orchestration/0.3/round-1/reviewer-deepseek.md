# 0.3 — reviewer-deepseek — round 1

Verdict: approve

## Previous findings

Both of my round-0 findings were **dropped by the orchestrator** (decisions.md, "Round 0 merge", lines 45-46: "Not sent: nit"). No fix was requested from the coder on my account; the only fix-list item was the config-load path gap raised by the test-reviewers.

- N1 — nit (src/instrumentserver/server/core.py:148-152, registration in `__init__` before `broadcastSocket` exists): dropped by orchestrator. Harmless, as my round-0 note said.
- N2 — nit (test peeks at private `_broadcast_sinks`; per-test dummy method): dropped by orchestrator. No change warranted.

## Did the fix commit break or weaken anything?

No. `5167241` is test-only (`test/pytest/test_broadcaster.py`, +46 lines); there is no `src/` change, so no runtime behaviour changed and nothing in my focus area (production correctness/clarity) was touched. Suite is fully green:

- `uv run pytest test/pytest/test_broadcaster.py` → 12 passed in 7.45s (was 11).
- `uv run pytest test/pytest/` → 173 passed in 66.55s.

The new `test_config_loaded_broadcaster_instrument_gets_sink` test is mutation-sensitive for the code it pins: if the `__init__` loop (core.py:151-152) were removed, `component._broadcast_sinks` would be empty and `assert server._broadcastParameterChange in component._broadcast_sinks` would fail. It also asserts exactly one registration (`len(component._broadcast_sinks) == 1`), matching the created-instrument test's exactly-one message, so a careless double-registration in the config path would be caught here. It uses the `server_port` fixture (no fixed port, per D27), constructs a never-started `StationServer` directly — correct, since the loop runs in `__init__` and no socket bind/thread is needed — and its `finally` block closes the temp file, the socketpair, and the `cfg_bcaster` instrument, so it leaves no qcodes state behind that could disturb the other tests in the same file.

The `loadConfig` unpack matches the function's actual 7-tuple return (config.py:192-200), and the YAML written mirrors the production config shape the quickstart config uses.

## New findings

None in my scope (correctness, clarity, consistency). The change is purely additive test coverage of the config-load registration path, which closes the one real coverage gap the round-0 test-reviewers raised (and that the plan's Testing-table row for `test_broadcaster.py` names: "created and config-loaded instruments").

## Notes

- Verified the fix commit with `git show 5167241 --stat` and `git show 5167241`: only `test/pytest/test_broadcaster.py` touched; the `__init__` registration loop in `core.py` is intact.
- Reviewed the new test in the context of `loadConfig` (instrumentserver/config.py:21-200), `StationServer.__init__` (core.py:106-199), and the existing server tests in the file.
- Whole suite re-run by me: 173 passed in 66.55s.