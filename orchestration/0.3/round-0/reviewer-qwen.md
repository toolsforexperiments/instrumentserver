# 0.3 — reviewer-qwen — round 0

Verdict: approve

## Findings

None.

I checked the commit (`04c4cbc`) line by line against the task and the surrounding code:

- `_registerBroadcaster` (`src/instrumentserver/server/core.py:578-587`) is exactly the
  plan's helper: `hasattr(instrument, "add_broadcast_sink")` →
  `instrument.add_broadcast_sink(self._broadcastParameterChange)`. It is called at the two
  plan-named sites: after `self.station.add_component(new_instrument)` in
  `_createInstrument` (`core.py:468-469`), and for every component after the Station is
  loaded from config in `__init__` (`core.py:148-152`). I verified in qcodes 0.58
  (`.venv/.../qcodes/station.py`) that `Station(config_file=...)` only parses the YAML and
  that instruments actually enter the Station via `load_instrument` (`core.py:146`), which
  runs before the loop — so the loop covers precisely the config-loaded instruments.
  `git grep` confirms those two are the only places in `src/` where components enter the
  Station (the init script is a third, out-of-scope path, see Notes).
- Registration happens in `__init__` before `broadcastSocket` exists, which is safe:
  the bound method only dereferences the socket when it is later invoked on a worker
  thread, the same place the Server's own broadcasts already run (ADR-0003 consequence).
  Double registration is impossible: a config-loaded instrument later reached by
  `find_or_create_instrument` is already in `station.components` and is skipped by the
  same `if` guard as `add_component`.
- The one-line comment above `_instrument_locks` (`core.py:194`) notes the "instrument
  mutex" prose name (ADR-0003); the name is untouched, as the task requires.
- `DummyBroadcasterInstrument(Broadcaster, Instrument)`
  (`src/instrumentserver/testing/dummy_instruments/generic.py:442-465`) has a correct MRO
  (`Broadcaster.__init__` → `Instrument.__init__`), and `emit_broadcast` is picked up by
  `bluePrintFromInstrumentModule` (public, not on the base class), so it is callable
  through the client proxy — which the new test does.
- The two new tests cover both plan scenarios: a Broadcaster created through
  `cli.find_or_create_instrument` emitting a blueprint that a `SubClient` receives
  (and exactly once, pinning the single-registration semantics), and a plain dummy
  instrument still working with no sink. The SubClient thread pattern is the established
  one from `test/docs_verification/helpers.py` and is free of the usual Qt
  cross-threading traps (`DirectConnection` append runs on the SubClient's thread, so
  blocking the main thread in `wait_for_broadcasts` cannot deadlock it).
- Naming and structure follow the file's conventions (camelCase private server methods,
  `:param:` docstrings, `ADR-0003` reference style used elsewhere in the ADRs).

## Notes

- Tests run: `uv run pytest test/pytest/test_broadcaster.py -v` → `11 passed in 7.46s`;
  `uv run pytest` (whole suite) → `172 passed, 4 warnings in 66.33s` (the 4 warnings are
  the pre-existing unregistered `pytest.mark.integration` in `test_apps.py`).
- `uv run ruff check` on the three changed files: all passed; `uv run mypy` on the two
  `src/` files: no issues.
- The mixin's public methods (`add_broadcast_sink`, `remove_broadcast_sink`, `broadcast`)
  show up in instrument blueprints as remotely callable methods (e.g. they would appear
  on the Parameter Manager's proxy once it emits). They are inert over the wire —
  callables do not survive JSON, and a malformed remote `broadcast(dict)` only reaches
  the mixin's logged-and-swallowed sink error path — but it is a design consequence of
  task 0.2's public contract, not of this commit. Flagging for the plan checker / a
  future task, not a finding here.
- The init script (`_runInitScript`, executed in `startServer`) can add components to
  the Station after the `__init__` registration loop; instruments added that way would
  not get a sink. The task explicitly scopes registration to the two named sites, and
  the plan's architecture section lists the same two entry points, so this is out of
  scope — worth keeping in mind for the Phase 6 broadcasts docs page.
- `capture_broadcasts` / `wait_for_broadcasts` in the test duplicate ~25 lines of
  `test/docs_verification/helpers.py`; that helper is only importable by the standalone
  script convention (`sys.path` insert), so the duplication is justified, and the test
  docstring says so.
