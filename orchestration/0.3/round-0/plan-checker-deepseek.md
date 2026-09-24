# 0.3 — plan-checker-deepseek — round 0

Verdict: approve

## Findings

No must-fix or should-fix findings.

### N1 — nit
- Where: src/instrumentserver/server/core.py:146-149 (`__init__`)
- What: The config-load registration loop iterates every `self.station.components.values()` rather than only components just loaded from `serverConfig`.
- Why: The plan says "Call it … for every component after the Station is loaded from config in `__init__`." Registering over all components is a superset of the config-loaded set and stays inside the plan's intent — ADR-0003: "When an instrument joins the Station (creation over the wire, or loading from config at startup) the Server checks `hasattr(instrument, "add_broadcast_sink")` and registers its own broadcast function as a sink." No double registration occurs because `_createInstrument` only registers for instruments newly added to `station.components`, which are not present at `__init__`.
- Suggested fix: none required; leaving as-is is consistent.

## Notes

- Scope: commit touches only `server/core.py`, `testing/dummy_instruments/generic.py` (new `DummyBroadcasterInstrument` for the tests), and `test_broadcaster.py`. Nothing outside task 0.3.
- Plan rules checked and met:
  - Helper `_registerBroadcaster(instrument)` with `hasattr(instrument, "add_broadcast_sink")` → `instrument.add_broadcast_sink(self._broadcastParameterChange)`. Matches the task line and ADR-0003.
  - Called after `self.station.add_component(new_instrument)` in `_createInstrument` (only inside the `if name not in components` branch, so a fresh instrument is registered exactly once), and for config-loaded components in `__init__`.
  - One-line comment above `_instrument_locks`: `# Prose calls these the "instrument mutex" (ADR-0003); the code keeps its current names.` Matches the task line and the glossary "Instrument mutex" entry (CONTEXT line 94). `_instrument_locks` is not renamed.
- Vocabulary: all new names and comments use glossary terms — "Broadcaster", "Broadcast", "Broadcast sink", "instrument mutex". No off-glossary words introduced. `SubClient`, `DummyBroadcasterInstrument`, `emit_broadcast`, `param0` are ordinary/consistent with existing code and plan wording.
- Acceptance (task line) met point by point: dummy `Broadcaster` instrument created via `cli.find_or_create_instrument`; method `emit_broadcast` emits a blueprint received by a `SubClient`; plain dummy instrument still works and gets no sink. The config-loaded registration path is implemented but not directly tested; the task's named test list covers only the created and plain-dummy paths, so no missing named test.
- Tests run:
  - `uv run pytest test/pytest/test_broadcaster.py -q` → 11 passed in 7.48s.
  - `uv run pytest -q` → 172 passed, 4 warnings in 66.86s (the `PytestUnknownMarkWarning` for `integration` is pre-existing and unrelated).