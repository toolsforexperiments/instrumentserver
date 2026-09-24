# 0.3 — reviewer-deepseek — round 0

Verdict: approve

## Findings

No must-fix or should-fix findings.

### N1 — nit
- Where: src/instrumentserver/server/core.py:148-152
- What: The config-load registration loop and its comment sit inside `__init__`, before `broadcastSocket` exists.
- Why: Harmless — `_registerBroadcaster` only appends `self._broadcastParameterChange` to the instrument's sink list; it never invokes the sink, so the `assert self.broadcastSocket is not None` in `_broadcastParameterChange` can only run once a request executes, after `startServer` has bound the socket.
- Suggested fix: None needed; recorded for completeness.

### N2 — nit
- Where: test/pytest/test_broadcaster.py:159 and src/instrumentserver/testing/dummy_instruments/generic.py:462
- What: The server test peeks at the private `_broadcast_sinks` list, and `DummyBroadcasterInstrument` exposes a small method solely for the test.
- Why: Checking the private sink list is a direct, honest assertion that the required registration happened (and that a plain dummy gets none), which is exactly what the plan's test spec asks to prove; the per-test dummy method is the minimal way to make an instrument emit through a proxy. Neither warrants a change.
- Suggested fix: None.

## Notes

- Reviewed the full diff for `04c4cbc` (`_registerBroadcaster` helper, its two call sites, the `_instrument_locks` comment, `DummyBroadcasterInstrument`, and the server part of `test_broadcaster.py`), plus the surrounding server code, the `Broadcaster` mixin in `base.py`, the three ADRs, `CONTEXT.md`, and `conftest.py`.
- Conformance to the task:
  - `_registerBroadcaster(instrument)` does `hasattr(instrument, "add_broadcast_sink")` → `instrument.add_broadcast_sink(self._broadcastParameterChange)` (core.py:586-587).
  - Called after `self.station.add_component(new_instrument)` in `_createInstrument` (core.py:469).
  - Called for every component after the Station is loaded from config in `__init__` (core.py:151-152; the loop runs after the `self.station.load_instrument(...)` loop and only config-loaded components are in `self.station.components` at that point).
  - One-line comment directly above `_instrument_locks` noting prose calls it the "instrument mutex" (ADR-0003) with the code names kept and nothing renamed (core.py:194).
  - Tests cover all three plan-specified server cases: created `Broadcaster` instrument reaches a `SubClient` (asserting exactly one message, i.e. no double registration), and a plain dummy instrument still works and stays sink-free.
- A created `Broadcaster` instrument registers exactly once: `_createInstrument` calls `_registerBroadcaster` only when the name is not already in `self.station.components`, and the config path only touches config-loaded instruments, so the two paths cannot double-register the same instrument.
- `broadcast` runs on the worker thread holding the instrument mutex, the same thread the Server's own broadcasts already use, matching ADR-0003.
- Tests run:
  - `uv run pytest test/pytest/test_broadcaster.py` → 11 passed in 7.46s.
  - `uv run pytest test/pytest/` → 172 passed in 66.35s (whole suite green).