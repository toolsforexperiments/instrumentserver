# 0.4 — test-reviewer-qwen — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/test_param_manager.py:63-97
- What: `capture_broadcasts` and `wait_for_broadcasts` are copied verbatim from test_broadcaster.py:166-202.
- Why: two identical SubClient-capture helpers now live in two test modules; if the capture pattern changes (e.g. thread join, slow-joiner delay) both copies must be updated. Not a plan rule — the plan's Testing section does not require a shared helper, and the coder's docstring notes the pattern is deliberately followed.
- Suggested fix: none required for this task; if a third module needs it (test_pm_locks.py / test_pm_types.py), factor it into a shared test helper.

### F2 — nit
- Where: test/pytest/test_apps.py:355, 386
- What: both launcher tests pass `--port 4567` on argv; the default-port path (`args.port = 5555` → `sub_port=5556`) is not exercised.
- Why: the plan only names "extend the two existing param-manager launcher tests to assert the kwargs", which is done; the default-port branch is the same one code line and the argparse default was already an int, so the risk of an uncaught regression there is negligible.
- Suggested fix: optionally add a third launcher test without `--port` asserting `sub_port=5556`; not blocking.

## Notes

- Tests run: `uv run pytest test/pytest/test_apps.py test/pytest/test_param_manager.py` → `31 passed in 12.61s`. Full suite: `uv run pytest` → `174 passed, 4 warnings in 69.09s` (the 4 warnings are pre-existing `PytestUnknownMarkWarning` for the `integration` mark, unrelated to this commit).
- Plan's named tests, all present and meaningful:
  - `test_apps.py` — the two existing param-manager launcher tests (`test_param_manager_script_instrument_exists`, `test_param_manager_script_instrument_missing`) were extended to assert `ParameterManagerGui` is called with `sub_port=4568, sub_host="localhost"`. They would fail if the launcher regressed: the old `ParameterManagerGui(pm)` call does not match `assert_called_once_with(mock_pm, sub_port=4568, sub_host="localhost")`, and (see below) removing `type=int` makes `args.port + 1` a `TypeError` that errors the test before the assertion.
  - `test_param_manager.py` — `test_add_parameter_without_initial_value_succeeds_and_broadcasts` is the named proxy test: via the `param_manager` fixture it calls `add_parameter("x")` with no `initial_value`/`unit`, then asserts exactly one `parameter-creation` broadcast on `server_port + 1` with `name="parameter_manager.x"`, `value is None`, `unit == ""`, and that `"x" in params.parameters`. I traced the broken-code path to confirm it is not vacuous: with the pre-fix `kwargs["initial_value"]` the KeyError is raised server-side after the call succeeds, wrapped in `ServerResponse(error=...)` by `executeServerInstruction`, and re-raised client-side by `BaseClient._handle_server_error` (default `raise_exceptions=True`) — so `params.add_parameter("x")` raises and the test fails; even if the exception were swallowed, no broadcast is emitted (the KeyError aborts before `_broadcastParameterChange`) and `wait_for_broadcasts` times out. The test pins the fix in both directions (call succeeds, and the exact broadcast payload).
- Right layers: launcher kwargs are checked in mocked unit tests (the established Phase-3 pattern in test_apps.py, no Qt event loop, no server); the KeyError fix is checked at the proxy layer through a live server and a real `SubClient`, matching the plan's "proxy tests use the `param_manager` fixture" convention. Names are accurate and in the plan's vocabulary.
- Coder's judgment call (`type=int` on `--port` in apps.py): consistent with the plan's scope rule. D24 requires `sub_port = args.port + 1`, which is uncomputable for a string port; before the commit only the int default `5555` worked and any `--port <value>` would have crashed the launcher at `args.port + 1`. The change is minimal, is pinned by the two launcher tests (they pass the string `"4567"` on argv and assert the int `sub_port=4568`), and does not touch any other launcher. `Client(port=...)` already receives ints elsewhere (conftest passes the int `server_port` fixture), so nothing downstream breaks.
- No existing tests were weakened, deleted or skipped; both launcher tests kept their original assertions and gained the kwargs check.
- Edge cases: `add_parameter` with `initial_value` present but `unit` missing (or vice versa) shares the same `kwargs.get` path and was equally broken pre-fix; the plan names only the both-missing proxy test, and the present-with-both case is already covered by the pre-existing `test_proxy_add_remove_parameter`. No gap.
