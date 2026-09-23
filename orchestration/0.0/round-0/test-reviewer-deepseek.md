# 0.0 — test-reviewer-deepseek — round 0

Verdict: approve

Single commit 71aa9af covers exactly the files the task names (conftest.py, the three
listed test modules, test_apps.py per the orchestrator decision, and AGENTS.md), with no
change to `src/`. The acceptance grep `5555|5599` over `test/pytest` (excluding
`__pycache__`) finds nothing, and I confirmed the whole suite passes (161 passed) on the
session-scoped `server_port` fixture.

## Findings

### F1 — nit
- Where: test/pytest/conftest.py:25-38 (`server_port` fixture, `_pair_is_free`)
- What: The fixture checks both ports are free, then closes its probe sockets and returns,
  so there is a check-to-bind (TOCTOU) window before `startServer` actually binds them.
- Why: Any "pick a free port" scheme has this race; the coder mitigated the dominant
  failure mode (concurrently starting sessions getting sequential adjacent ephemeral
  ports) by drawing randomly from a wide non-ephemeral range (20_000-40_000), which is the
  right call. Not plan-blocking — this is test infra, no `src/` change is allowed by the
  task.
- Suggested fix: none required. If ever flaky in CI, hold the probe sockets open and pass
  the bound file descriptors to `startServer`, but the current random-range approach is
  adequate and within the task's "test-only" scope.

### F2 — nit
- Where: test/pytest/conftest.py:12-38
- What: No dedicated test asserts the `server_port` fixture returns a distinct usable
  consecutive pair; it is only exercised end-to-end by the suite.
- Why: The task's own test criterion is "whole suite green" and names no fixture unit test;
  every `start_server`/`cli`/GUI test now drives the fixture, and the parallel-collision
  acceptance is a manual two-run check, so a dedicated test would be a bonus not a rule.
- Suggested fix: optional; a small test that a server started on `server_port` accepts
  requests on `port` and broadcasts on `port+1` would pin the fixture contract, but it is
  not required for this task.

## Notes

Tests run: `uv run pytest -q` in the worktree → `161 passed, 4 warnings in 59.53s`
(matches the orchestrator's two concurrent runs of 161 passed each).

Per-test check:
- `test_client_station.py` — all six `ClientStation(port=5555)` become
  `port=server_port`; the `"5555"` assert becomes `str(server_port)` — still a meaningful
  assertion that the GUI widget reflects the actually-used port. Not weakened.
- `test_server_gui.py` — five `startServerGuiApplication()` calls pass `port=server_port`
  and gained `_wait_until_client_points_at_server`, which waits for the embedded client's
  retarget to the dynamic port before the first request. This is a strengthening (removes a
  race that was invisible under the old fixed port), not a loosening.
- `test_gui_navigation.py` — `TEST_PORT = 5599` removed; `_start_window(qtbot, port)` and
  each test requests `server_port`; the `addr.endswith(f":{port}")` wait is preserved.
  Behaviour unchanged.
- `test_apps.py` — argparse-default asserts derive from `src` `DEFAULT_PORT` (== 5555)
  instead of the literal, and two param-manager tests use a non-default `--port 4567`
  sentinel; all are mocked unit tests so no live port is involved. Satisfies the
  orchestrator decision to make the literal disappear without touching `src/`.
- AGENTS.md carries the required sentence verbatim plus a `server_port` bullet.

The fixture's `port` / `port + 1` contract matches `src` (server binds `self.port`,
`broadcastPort = self.port + 1`). No test was deleted, skipped, or weakened.