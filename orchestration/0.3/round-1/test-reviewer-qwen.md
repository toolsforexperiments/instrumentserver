# 0.3 — test-reviewer-qwen — round 1

Verdict: approve

## Previous findings

- **F1 (must-fix — config-load registration path untested): FIXED.** The fix commit adds `test_config_loaded_broadcaster_instrument_gets_sink` (`test/pytest/test_broadcaster.py:240`), which does exactly what the fix list asked: it writes a station-config YAML defining `cfg_bcaster` → `DummyBroadcasterInstrument` with `initialize: True`, splits it with `loadConfig`, constructs a `StationServer(port=server_port, serverConfig=..., stationConfig=...)` directly, and asserts the component exists, `isinstance(component, Broadcaster)`, `server._broadcastParameterChange in component._broadcast_sinks`, and `len(component._broadcast_sinks) == 1`. I verified the `__init__` loop it covers is intact (`core.py:148-152`, unchanged from 04c4cbc), and the test is meaningful: for a config-loaded instrument the only sink-registration path is that loop (`_createInstrument` is not on this path), so removing the loop would leave `_broadcast_sinks` empty and both the membership and length asserts would fail. The coder skipped the optional SubClient emission step with a sound reason (an un-started `StationServer` has no bound PUB socket, so emission would trip the `assert self.broadcastSocket is not None` in `_broadcastParameterChange`); the plan's table requires "server registers sinks for … config-loaded instruments" — registration is what is asserted — and the wire path is covered by `test_created_broadcaster_instrument_reaches_subclient`. The teardown is actually safer than my suggestion: it closes the temp config file, the `__init__` wakeup socketpair, and only the `cfg_bcaster` instrument itself (not `close_all()`), so the module-scoped server's instruments are undisturbed.
- **F2 (nit — "gets no sink" asserted via the class rather than server state): DROPPED by orchestrator** (Round 0 merge: "Not sent: nit"). Still present, unchanged (`test_plain_dummy_instrument_still_works_and_gets_no_sink` line 237). Intentional; no action expected.
- **F3 (nit — `emit_broadcast` return value not asserted): DROPPED by orchestrator** (Round 0 merge: "Not sent: nit"). Still present; the created-path test is unchanged by the fix commit. Intentional; no action expected.

## Did the fix commit break or weaken anything?

No. Commit 5167241 touches only `test/pytest/test_broadcaster.py` (new imports `qcodes`, `loadConfig`, `StationServer`, plus the one new test); no `src/` change. I re-verified the `__init__` registration loop is intact at `core.py:148-152` (consistent with the orchestrator's mutation-check record). No existing test was modified, weakened, or skipped — all 11 pre-existing tests in the file still pass. The new test is deterministic (no sockets, no timing, runs last in the file, does not use the module server fixtures), so it adds no flakiness risk and cannot interfere with the module-scoped `start_server`.

## New findings

None. The new test is at the right layer (server, unit-style construction of `StationServer`), its name is accurate and in the plan's vocabulary (config, Broadcaster, sink), and it fails if the config-load registration regresses.

## Notes

- Tests run:
  - `uv run pytest test/pytest/test_broadcaster.py -v` → `12 passed in 7.47s`
  - `uv run pytest` (whole suite) → `173 passed, 4 warnings in 66.51s` (the 4 warnings are the same pre-existing `pytest.mark.integration` unknown-mark warnings in `test_apps.py`, unrelated to this commit).
- Both registration points named in task 0.3 now have a dedicated test: created-over-the-wire (`test_created_broadcaster_instrument_reaches_subclient`) and config-loaded (`test_config_loaded_broadcaster_instrument_gets_sink`), matching the plan's Testing table for `test_broadcaster.py`.
