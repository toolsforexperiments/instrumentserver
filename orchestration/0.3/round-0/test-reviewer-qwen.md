# 0.3 — test-reviewer-qwen — round 0

Verdict: changes-needed

## Findings

### F1 — must-fix
- Where: `test/pytest/test_broadcaster.py` (server part) + `src/instrumentserver/server/core.py:148-152`
- What: The config-load registration path has no test. The commit adds a loop in `StationServer.__init__` that calls `_registerBroadcaster` for every component loaded from the station config, but no test exercises that path; `test_broadcaster.py` only covers the created-over-the-wire path.
- Why: The plan's Testing table is explicit that this file covers "server registers sinks for created **and config-loaded** instruments", and D23 points at that table as the test plan. The `__init__` loop is brand-new code from this commit and is the only place the config-load requirement ("for every component after the Station is loaded from config in `__init__`") is implemented. No other task names this coverage. If that loop regressed, a `Broadcaster` instrument loaded from config at startup would silently never emit, and no test would fail.
- Suggested fix: Add a test that loads a `DummyBroadcasterInstrument` from config and asserts the server registered itself as its sink. Setup: write a station-config YAML defining `bcaster_cfg` → `instrumentserver.testing.dummy_instruments.generic.DummyBroadcasterInstrument` with `initialize: True` (mirror `test/docs_verification/getting_started/quickstartConfig.yml`), derive `serverConfig`/`stationConfig` via `instrumentserver.config.loadConfig` (the pattern `test_apps.py` already uses). Action: construct a `StationServer(port=server_port, serverConfig=..., stationConfig=...)` — registration happens in `__init__`, so no thread or port bind is needed; use the `server_port` fixture and `qapp_session`. Expected: `server.station.components["bcaster_cfg"]` exists and `server._broadcastParameterChange in server.station.components["bcaster_cfg"]._broadcast_sinks` (mirroring the white-box assert in `test_created_broadcaster_instrument_reaches_subclient`); tear down with `qc.Instrument.close_all()`. Optionally also emit via the component and confirm a `SubClient` receives it, to cover the full path.

### F2 — nit
- Where: `test/pytest/test_broadcaster.py::test_plain_dummy_instrument_still_works_and_gets_no_sink`
- What: The "gets no sink" assertion checks `not hasattr(server_dummy, "add_broadcast_sink")`, which is a property of the dummy's class hierarchy rather than of the Server's behaviour.
- Why: Because registration is gated on `hasattr(instrument, "add_broadcast_sink")`, this is a logically valid proxy and the "still works" set/get part is a genuine behaviour check, so it is acceptable as-is — but a direct `not hasattr(server_dummy, "_broadcast_sinks")` (or asserting `_registerBroadcaster` added nothing) would state the intent more precisely. Preference only.

### F3 — nit
- Where: `test/pytest/test_broadcaster.py::test_created_broadcaster_instrument_reaches_subclient`
- What: `inst.emit_broadcast(value=2.5, unit="V")` is called but its return value (the `ParameterBroadcastBluePrint` the method returns) is never asserted.
- Why: The plan requires client-facing method return values to be JSON-serialisable blueprints that round-trip through the proxy; asserting the returned blueprint equals what was sent would pin that. The broadcast-on-the-wire is already asserted, so this is a missed opportunity, not a broken test. Preference only.

## Notes

- All three tests named in task 0.3's "Tests:" line are present and meaningful:
  - `test_created_broadcaster_instrument_reaches_subclient` — creates a `DummyBroadcasterInstrument` via `cli.find_or_create_instrument`, white-box asserts the server is in its `_broadcast_sinks`, then a proxy method call that emits a blueprint is received by a `SubClient` (asserts topic, action, value, unit, and `len(received) == 1` to catch double-registration). Right layer (server/proxy). Fails if the sink is not registered.
  - `test_plain_dummy_instrument_still_works_and_gets_no_sink` — plain dummy still set/gets over the wire and has no sink.
- The two new tests are at the correct layer and use the plan's vocabulary (Broadcaster, SubClient, Broadcast). The `capture_broadcasts`/`wait_for_broadcasts` helpers faithfully mirror the established `test/docs_verification/helpers.py` pattern (SubClient on its own QThread, `DirectConnection`, PUB/SUB slow-joiner sleep, GIL-safe list append), so the threading is sound and not flaky-prone by design.
- `DummyBroadcasterInstrument` is added to `src/instrumentserver/testing/dummy_instruments/generic.py`; that module is only imported on demand (both `__init__.py`s are empty), so there is no import-time or circular-import risk, and the existing API is untouched. `Broadcaster.__init__` correctly chains into `Instrument.__init__` and `param0` is added after `super().__init__()`.
- The `_registerBroadcaster` helper and the `_createInstrument` call site match the task exactly; the one-line "instrument mutex" comment is present above `_instrument_locks` and nothing was renamed.
- No existing test was weakened, deleted, or skipped; the nine unit tests from task 0.2 are unchanged.
- Tests run:
  - `uv run pytest test/pytest/test_broadcaster.py -v` → `11 passed in 7.45s`
  - `uv run pytest` (whole suite) → `172 passed, 4 warnings in 66.92s` (the 4 warnings are pre-existing `pytest.mark.integration` unknown-mark warnings in `test_apps.py`, unrelated to this commit).
