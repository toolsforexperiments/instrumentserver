# 0.0 — plan-checker-deepseek — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/test_apps.py:354,379 (the two `parameterManagerScript` tests)
- What: the plan task text lists only `test_client_station.py`, `test_server_gui.py`, `test_gui_navigation.py` for the port change; `test_apps.py` is handled per the orchestrator note, so the coder swapping `--port 5555` → `--port 4567` in these two tests is within the logged decision, not in-scope.
- Why: Orca decisions.md records: "the task text does not list that file but its acceptance grep requires the literal gone from all of test/pytest, so the orchestrator told the coder to ... derive the expected default from src without changing src/." The `4567` makes the grep literal-free while src stays untouched (verified `git diff dcac611..71aa9af -- src/` is empty and `DEFAULT_PORT = 5555` exists unchanged in `src/instrumentserver/__init__.py`).
- Suggested fix: none required.

### F2 — nit
- Where: test/pytest/test_server_gui.py:25-30 (`_wait_until_client_points_at_server`)
- What: a small wait helper added beyond the literal task text (which only says the five `startServerGuiApplication()` calls use the port) so the embedded client re-targets the dynamic port before the first request.
- Why: the plan's conftest prose states the server binds `port` and uses `port + 1` for broadcasts; with fixed ports the embedded client's initial default-port connection happened to be harmless, but a dynamic port makes the first request race. The helper makes the named tests honest without touching `src/`, consistent with "No change to `src/`" ("No change to `src/`.").
- Suggested fix: none required; reads as necessary accommodation for dynamic ports.

## Notes
- Tests run: `uv run pytest -q` — `161 passed, 4 warnings in 59.12s` (warnings are pre-existing unknown pytest.mark.integration marks). Matches the orchestrator's two concurrent runs (161 passed each).
- Confirmed acceptance: `grep -rn "5555\|5599" test/pytest` (excluding __pycache__) returns nothing (exit 1).
- Remaining `5555`/`5599` literals elsewhere in `test/` (`test_config.py` `:5556` externalBroadcast yaml-content assertion, `test_async_requests/*`, `test/notebooks`, `docs_verification/helpers.py`) are outside the `test/pytest` acceptance scope and are not live server ports targeted by this task; correctly left alone.
- The `server_port` fixture ranges 20k–40k, out of the OS ephemeral range, and verifies both the request port and `port + 1` are free before returning — satisfies "picks two free consecutive ports once per pytest session".