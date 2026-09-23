# 0.0 — reviewer-qwen — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/conftest.py:18-22 (docstring) and :35 (`random.randrange(20_000, 40_000)`)
- What: The fixture docstring says the random range is "deliberately outside the OS ephemeral port range", but 32768–39999 falls inside Linux's default ephemeral range (`ip_local_port_range` 32768–60999); the claim only holds on macOS/BSD (49152–65535).
- Why: The bind-verify loop catches ports that are in use at check time, so the practical risk is small, but on Linux the top quarter of the range still carries the kernel-allocation race the docstring says the range avoids, and the stated rationale is inaccurate there. No observed failure on this machine.
- Suggested fix: Either narrow the upper bound (e.g. `random.randrange(20_000, 32_000)`), or soften the docstring to "outside the macOS ephemeral port range; the bind check covers the rest".

## Notes

- Scope check: commit 71aa9af touches only `AGENTS.md` and five `test/pytest/*.py` files; no `src/` change, matching the task's "No change to `src/`".
- Plan conformance (spot-checked here, plan checker owns the full call): session-scoped `server_port` fixture picking two free consecutive ports by binding both (`conftest.py:12-38`); `start_server` (`startServer(port=server_port)`), the shutdown `BaseClient(port=server_port)`, and `cli` (`Client(port=server_port)`) all use it. `test_client_station.py`: six `ClientStation(port=server_port)` and the `"5555"` assert now `str(server_port)`; `test_server_gui.py`: five `startServerGuiApplication(port=server_port)`; `test_gui_navigation.py`: `TEST_PORT = 5599` gone, port threaded through `_start_window`. AGENTS.md carries the plan's sentence verbatim under "Testing" plus a fixture-list entry.
- The new `_wait_until_client_points_at_server` (test_server_gui.py:25-29) and its twin in `test_gui_navigation.py:_start_window` (:42) are justified, not just cosmetic: `EmbeddedClient` is constructed at `DEFAULT_PORT` (server/application.py:639) and only re-targets on the `serverStarted` signal. I verified the wait is safe: the server binds the ROUTER socket *before* emitting `serverStarted` (server/core.py:213-217), so by the time the wait passes the first request is answered; ZMQ DEALER queues outgoing messages until the TCP handshake completes, and the PUB socket on `port + 1` binding a moment later (core.py:220-223) is irrelevant to these tests, whose only dependency is the request socket.
- `endswith(f":{port}")` is exact enough: the leading `:` in the suffix rules out false matches against a shorter default-port address (e.g. port 35555 vs. the initial `:5555`).
- test_apps.py: per the logged orchestrator decision, argparse-default assertions now compare against `DEFAULT_PORT` from `instrumentserver` (src `__init__.py:25`). This is a stronger invariant than the literal (it catches drift between the hardcoded `default=5555` in apps.py:128/155/167 and the package constant), and no src/ change was needed. The `"4567"` argv values in the two mocked `parameterManagerScript` tests match the file's existing style (`"9999"` in `test_server_script_passthrough_args`) and are never bound.
- No test in `test/pytest/` constructs a `Client`/`BaseClient`/`SubClient` outside the fixtures (grep-verified), so nothing silently points at 5555 anymore. `test_base.py` already used `bind_to_random_port`; `test_shortcuts.py` (`{"port": 8000}`) and `test_config.py` (`:5556`) are YAML data values, not live ports, and are outside the acceptance grep.
- `test/test_async_requests/test_client.py:9` and `demo_concurrency.py:33` still use literal 5555; the task text and its acceptance grep are scoped to `test/pytest`, so this is outside 0.0's scope (flagging for the plan checker's awareness only).
- Tests run: `uv run pytest -q` → `161 passed, 4 warnings in 58.68s` (warnings are pre-existing, e.g. unregistered `integration` mark). The two-concurrent-runs acceptance was already executed by the orchestrator and logged in orchestration/0.0/decisions.md (both 161 passed).
- Acceptance grep: `grep -rn "5555\|5599" test/pytest` → no matches (exit 1).
