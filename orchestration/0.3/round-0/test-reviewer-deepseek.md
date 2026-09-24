# 0.3 — test-reviewer-deepseek — round 0

Verdict: changes-needed

## Findings

### F1 — should-fix
- Where: `test/pytest/test_broadcaster.py` (server part) — no test for the config-load path in `src/instrumentserver/server/core.py:151-152`
- What: The `__init__` config-load registration branch (`for component in self.station.components.values(): self._registerBroadcaster(component)`, core.py:151-152) has no test; the server part covers only the `_createInstrument` branch (line 469).
- Why: The task text and the plan's Testing table both state registration applies to "created and config-loaded instruments", and the commit implements both paths (core.py:151-152 and 469). Currently a `git rm` of the `__init__` loop would leave every test green. This visits a code path the plan says the file must cover.
- Suggested fix: Add a test that starts the server with a `serverConfig` whose `initialize: True` names a Broadcaster instrument (mirroring the config fixtures in `test_apps.py`/`test_config.py`), then assert the sink was registered — e.g. `server.station.components[<name>]._broadcast_sinks` contains `server._broadcastParameterChange` — and ideally repeat the `SubClient`-receives-emission check, mirroring `test_created_broadcaster_instrument_reaches_subclient`. Setup: server constructed with the config; action: `_registerBroadcaster` runs over config-loaded components in `__init__`; expected: the config-tracked instrument has the server as a sink.

## Notes
- Severity: 0 must-fix, 1 should-fix, 0 nit.
- The three named tests are present and meaningful: (1) `test_created_broadcaster_instrument_reaches_subclient` — created-through-`cli` Broadcaster instrument is a registered sink and a method call that emits a blueprint arrives at a `SubClient` with the right name/action/value/unit and exactly one message; (2) `test_plain_dummy_instrument_still_works_and_gets_no_sink` — a plain dummy works over the wire and has no sink; (3) the unit part covers the mixin unchanged. The "exactly one message" assertion pins that the server registered itself once and that `_callObject` does not double-broadcast a plain method. The instrument-mutex comment (core.py:194) is present verbatim. Vocabulary matches the glossary (Broadcaster, broadcast, sink, instrument mutex).
- Tests run: `uv run pytest test/pytest/test_broadcaster.py` — 11 passed in 7.47s (9 unit + 2 server).
- This review covers only commit 04c4cbc; the 0.2 unit part (Broadcaster mixin) was out of scope.