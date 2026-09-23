# 0.0 — test-reviewer-qwen — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/conftest.py:18-23 (`server_port` docstring)
- What: The docstring claims the random range 20000–40000 is "deliberately outside the OS ephemeral port range", which is true on macOS (49152–65535) but not on Linux, where the default ephemeral range starts at 32768, so the top ~7k of the range overlap.
- Why: On Linux, ports in 32768–39999 could be handed out sequentially to a concurrently starting session; the bind-verification of both `port` and `port + 1` catches ports already in use and the random draw makes an adjacent-pair hand-out extremely unlikely, so this is a docstring accuracy issue, not a behaviour one.
- Suggested fix: Soften the docstring (e.g. "outside the macOS ephemeral range; both ports are verified free regardless of platform").

## Notes

- Review target: commit `71aa9af` ("0.0: per-run test ports via session-scoped server_port fixture"), the only commit in `dcac611..71aa9af`. Files: `AGENTS.md`, `test/pytest/{conftest,test_apps,test_client_station,test_gui_navigation,test_server_gui}.py`. `git diff dcac611..71aa9af -- src/` is empty, so the task's "No change to src/" rule holds.
- `server_port` (conftest.py:12-38): session-scoped, draws a random port from 20000–40000 and bind- verifies both `port` and `port + 1` (the server binds `127.0.0.1:port` for requests and `*:port+1` for the PUB broadcast socket — `server/core.py:135,152,214` — so checking `""` (0.0.0.0) for both is a correct superset check). Raises `RuntimeError` after 100 failed draws. It can fail (all draws occupied → every server module errors), and it cannot silently return a used pair.
- Named call sites, all converted: `start_server` (`startServer(port=server_port)`), the shutdown client in `start_server` (`BaseClient(port=server_port)`), `cli` (`Client(port=server_port)`), six `ClientStation(host=..., port=server_port)` in `test_client_station.py` (incl. the module-scoped `client_station` fixture) plus the `"5555"` assert (now `str(server_port)` — meaningful, since `ServerWidget` renders `client_station._port`), five `startServerGuiApplication(port=server_port)` in `test_server_gui.py`, and `TEST_PORT = 5599` removed from `test_gui_navigation.py` (now threaded through `_start_window(qtbot, port)`).
- New behaviour, well tested: `_wait_until_client_points_at_server` (test_server_gui.py:25-29), added after every `startServerGuiApplication(port=...)` call. This addresses a real new race — `EmbeddedClient` is constructed at the default port and only re-targets when the `serverStarted` signal is delivered, so without the wait the first request would go to port 5555 (a developer's live server). `test_gui_navigation.py` already had the equivalent wait pre-existing.
- `test_apps.py` (orchestrator-directed, see `orchestration/0.0/decisions.md`): the four argparse-default assertions now compare against `instrumentserver.DEFAULT_PORT` (= 5555, `src/instrumentserver/__init__.py:25`) instead of the literal — assertion strength preserved, no src change. The two `parameterManagerScript` tests use `"--port", "4567"`; those clients are `MagicMock`s, so no socket is opened — same style as the pre-existing `9999`/`9000` literals in that file and irrelevant to port collisions.
- No weakening: no `skip`/`xfail` introduced; the only removed lines are the port literals; every pre-existing assertion is intact. Other test files in `test/pytest` reach the server only through the `cli`/`param_manager` fixtures, so they inherit the dynamic port; no other fixed server-port literals remain (`test_shortcuts.py` `port: 8000` is YAML config content parsed locally, no server).
- No dedicated unit test exists for the `server_port` fixture itself (freeness, consecutiveness, session stability), but the plan names none ("Tests: whole suite green") and the fixture is self-verifying through use: a non-free pair makes the server's bind fail and every server-backed test in the session fail, and the two-concurrent-runs acceptance below exercises it.
- Tests run (mine):
  - `uv run pytest -q` → `161 passed, 4 warnings in 59.41s` (the 4 warnings are pre-existing `PytestUnknownMarkWarning` for `integration`, unrelated to this commit).
  - Two concurrent `uv run pytest -q` runs started at the same time: run A `161 passed, 4 warnings in 59.09s` (exit 0), run B `161 passed, 4 warnings in 58.89s` (exit 0) — the plan's second acceptance criterion, independently re-verified.
  - Acceptance grep `grep -rn "5555\|5599" test/pytest` → no matches (exit 1).
- AGENTS.md: the exact required line ("Tests never use a fixed port. Use the `server_port` fixture; agents run the suite in parallel.") is present under "Testing", plus a `server_port` bullet in the Test Setup list.
