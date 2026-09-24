# 0.3 — plan-checker-deepseek — round 1

Verdict: approve

## Previous findings

### N1 — nit (previous round)
- Where: src/instrumentserver/server/core.py:146-149 (`__init__`)
- What: the `__init__` config-load registration loop iterates every `self.station.components.values()` rather than only components just loaded from `serverConfig`.
- Why: the plan says "Call it … for every component after the Station is loaded from config in `__init__`." Registering over all components is a superset of the config-loaded set but stays inside the plan's intent.
- Status: **dropped by orchestrator** — decisions.md "Round 0 merge": "plan-checker-deepseek N1 (nit): __init__ loop covers all station components, a superset of config-loaded ones. Not sent: nit; matches ADR-0003 intent." The `__init__` loop is unchanged (still at core.py:152) and remains consistent with the plan and ADR-0003, so dropping is fine.

## Findings (round 1)

No must-fix or should-fix findings, and no new findings in the plan-checker lane.

### N2 — nit
- Where: test/pytest/test_broadcaster.py (`test_config_loaded_broadcaster_instrument_gets_sink`)
- What: the new test peeks at the private `component._broadcast_sinks`.
- Why: not a plan rule; it mirrors the existing created-instrument test (`test_created_broadcaster_instrument_reaches_subclient`), which does the same private peek. A server-side public accessor is out of this task's scope.
- Suggested fix: none; consistent with the existing tests.

## Notes

- Fix commit 5167241 is test-only: it adds `test_config_loaded_broadcaster_instrument_gets_sink` to `test/pytest/test_broadcaster.py` and changes no `src/` code. The `__init__` register loop (core.py:152) and the `_createInstrument` registration (core.py:469) are intact, matching the plan's two entry points and ADR-0003.
- The new test genuinely guards the config-load path: it writes a config YAML with `instruments:` -> `cfg_bcaster` (`type: instrumentserver.testing.dummy_instruments.generic.DummyBroadcasterInstrument`, `initialize: True`), runs it through `loadConfig`, constructs `StationServer(port=server_port, serverConfig=..., stationConfig=...)` directly (registration happens in `__init__`; no thread or socket bind needed), and asserts the component exists, is a `Broadcaster`, and that `server._broadcastParameterChange` is in its `_broadcast_sinks`. Removing the `__init__` loop would fail the test, so it is not vacuous. It uses the `server_port` fixture (no fixed port, per D27). Teardown closes the temp file, the wake-up socket pair, and the config-loaded `cfg_bcaster` instrument, leaving the module-scoped `start_server` fixtures unharmed.
- The fix-test vocabulary uses glossary terms: "Broadcaster", "Broadcast sink", `serverConfig`/`stationConfig` — consistent. The optional SubClient emission part was reasonably skipped (a never-started StationServer has no bound PUB socket; the wire path is already covered by the created-instrument test).
- Tests run:
  - `uv run pytest test/pytest/test_broadcaster.py -q` -> 12 passed in 7.44s.
  - Orchestrator's full suite after fix 1: 173 passed, 4 warnings (per decisions.md).