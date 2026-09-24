# 0.3 — reviewer-qwen — round 1

Verdict: approve

## Previous findings

My round-0 report had no findings (verdict: approve; three informational Notes only), so
there is nothing to be fixed or dropped. The single fix-list item (test for the
config-load registration path) came from test-reviewer-qwen/deepseek and the coder's own
flag, not from my report. For the record, my two round-0 notes (the init-script
registration gap, out of scope per the task; the mixin's wire-callable public methods, a
0.2 consequence) are carried in `decisions.md` as "Notes for the user" and remain
informational.

## Fix commit review (5167241)

The commit adds one test, `test_config_loaded_broadcaster_instrument_gets_sink`, to
`test/pytest/test_broadcaster.py` (+46 lines; `git diff 04c4cbc..5167241 --stat` confirms
no other file changed, so my round-0 code-level conclusions stand).

- **It pins the right code.** The test writes a production-style server config
  (`instruments: cfg_bcaster: {type: ...DummyBroadcasterInstrument, initialize: True}`),
  splits it with `loadConfig` (unpacking the 7-tuple return in the correct order,
  verified against `src/instrumentserver/config.py:192-199`), and constructs
  `StationServer(port=server_port, serverConfig=..., stationConfig=...)` directly.
  In qcodes 0.58 the config-loaded instrument reaches the Station only through
  `load_instrument` inside `__init__` (qcodes `station.py:717` `add_component`), so the
  registration loop at `src/instrumentserver/server/core.py:151-152` is the *only* code
  that can put `server._broadcastParameterChange` into `component._broadcast_sinks`.
  The `in ...` plus `len(...) == 1` asserts therefore fail if the loop is removed — the
  test genuinely covers the previously untested path.
- **No interference with the running suite state.** The `StationServer` is constructed
  but never started: no port is bound (no collision with the module-scoped server on the
  same `server_port`), no thread is spawned. Its side effects are all cleaned up: the
  `loadConfig` temp-file handle and both wakeup socketpair ends are closed in `finally`,
  and `cfg_bcaster` is closed via `qc.Instrument.find_instrument(...).close()` guarded by
  `exist()`. The one residual — the new `Station` becomes `Station.default`
  (qcodes `station.py:164`, strong reference) and outlives the test — is harmless: the
  only qcodes consumer of `Station.default` is `Measurements.__init__`
  (`measurements.py:661`), which neither this codebase nor the test suite uses, and the
  live module server holds an explicit `self.station` reference. `update_monitor()` in
  `load_instrument` does not open a Qt Monitor (default `station.use_monitor` is
  falsy).
- **The skipped optional part is reasonable.** The fix list suggested optionally emitting
  through the component to a `SubClient`; the coder skipped it because a never-started
  `StationServer` has no bound PUB socket and `_broadcastParameterChange` asserts on
  `broadcastSocket`. The wire path is already covered by the created-instrument test.
  Noted in `decisions.md`; no objection.
- **Nothing weakened.** The two existing server tests are untouched; the new test adds no
  fixture dependencies beyond `tmp_path` / `server_port` / `qapp_session` and would pass
  standalone even without the module server.

## New findings

None.

## Notes

- Tests run: `uv run pytest test/pytest/test_broadcaster.py -v` → `12 passed in 7.45s`;
  `uv run pytest` (whole suite) → `173 passed, 4 warnings in 66.43s` (same pre-existing
  `pytest.mark.integration` warnings as round 0). `uv run ruff check
  test/pytest/test_broadcaster.py` → all checks passed.
- White-box style: the new test reaches into `StationServer` privates
  (`_wakeup_r`/`_wakeup_w`) and the mixin's `_broadcast_sinks`, matching the existing
  pattern in this file and in `conftest.py` (`server.SAFEWORD`); consistent, no finding.
- `loadConfig` writes a `NamedTemporaryFile(delete=False)` that persists on disk after
  the test (only the handle is closed); this is pre-existing production behaviour in
  `config.py`, identical to how `apps.py` uses it, and not changed by this commit.
