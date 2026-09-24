# 0.3 — plan-checker-qwen — round 1

Verdict: approve

## Previous findings

My round-0 report (orchestration/0.3/round-0/plan-checker-qwen.md) had **no findings** (verdict: approve, 0 must-fix / 0 should-fix / 0 nit), so nothing from my report was fixed, not fixed, or dropped by the orchestrator. The single fix-list item (`orchestration/0.3/round-0/fix-list.md`, item 1: "Add a test for the config-load registration path") came from the test reviewers, not from me. For completeness, my two round-0 non-findings were both dropped by the orchestrator on purpose, per `orchestration/0.3/decisions.md` "Round 0 merge": the nit (`_registerBroadcaster` camelCase vs rule 8 "New methods are `snake_case`" — "Not sent: the task's explicit name wins") and the user-facing Notes (`_runInitScript` could add instruments after the `__init__` loop; plan lists only two entry points) — the latter remains a plan question, not a 0.3 requirement, so it stays out of scope.

Fix commit 5167241 implements exactly fix-list item 1 and only that: `git diff 04c4cbc 5167241 --stat` shows 46 insertions, 0 deletions, in `test/pytest/test_broadcaster.py` alone. No `src/` change.

## Did the fix break or weaken anything in my focus area?

No.

- **Implementation intact**: the `_registerBroadcaster` helper, both call sites, and the one-line "instrument mutex" comment are unchanged — verified by `git show 5167241:src/instrumentserver/server/core.py` (the `for component in self.station.components.values(): self._registerBroadcaster(component)` loop at core.py:151-152 is byte-identical to round 0).
- **Round-0 tests untouched**: the fix is purely additive; all 11 round-0 tests still pass unchanged.
- **New test stays in task 0.3 scope**: it exercises the task's second call site — plan task 0.3: "for every component after the Station is loaded from config in `__init__`" — and the plan's Testing table line: "server registers sinks for created **and config-loaded** instruments". It uses the real production path: `instrumentserver.config.loadConfig` splits a YAML (same shape as `test/docs_verification/getting_started/quickstartConfig.yml`, which the docstring names) into a station config plus `serverConfig`, and a directly constructed `StationServer` loads `cfg_bcaster` via the `load_instrument` loop in `__init__` (qcodes' `Station(config_file=…)` only reads the config; `load_instrument` is what instantiates and `add_component`s, qcodes/station.py:717). `loadConfig`'s 7-value return order was checked against `src/instrumentserver/config.py:192-200` — the unpack `stationConfigPath, serverConfig, _, _, tempFile, _, _` is correct.
- **Commit rule**: message starts with the task number ("0.3: fix from review round 1: …"); separate fix-round commit, per session protocol step 6 ("each round of review fixes is its own commit").
- **No fixed port**: uses the `server_port` fixture; `git grep -n "5555\|5599" -- test/pytest` finds nothing (task 0.0 acceptance holds).

## New findings

None.

- **Mutation-sensitive**: the test asserts `server._broadcastParameterChange in component._broadcast_sinks` **and** `len(component._broadcast_sinks) == 1`; removing the `__init__` loop leaves `_broadcast_sinks` empty, so the test fails — it closes exactly the gap the fix list named ("Today a removal of the `__init__` loop leaves every test green").
- **No interference with other tests**: the new test does not use the `start_server`/`cli` fixtures and creates no instruments on the running server. Constructing the throwaway `Station` reassigns `Station.default`, but in this qcodes version `Station.default` is referenced only by `dataset/measurements.py`, never during instrument creation; the running server holds its own `self.station` reference. Cleanup in `finally` (close `tempFile`, close both ends of the socketpair, close `cfg_bcaster` guarded by `qc.Instrument.exist`) matches what the test opened. The full suite passing confirms no cross-module disturbance.
- **Vocabulary**: "config-loaded broadcaster instrument", "get(s) a sink", "Broadcast sink", "reaches the Station from a config file", "component" (mirrors the plan's "for every component"), "ADR-0003" — all glossary/plan/ADR terms in their glossary meanings.
- **Skipped optional part**: the coder did not add the SubClient-emission part of the fix-list suggestion ("Optionally also emit through the component…"), with a sound reason recorded in `orchestration/0.3/decisions.md` (a never-started `StationServer` has no bound PUB socket; the wire path is already covered by `test_created_broadcaster_instrument_reaches_subclient`). The plan's task line for 0.3 names only the created-instrument and plain-dummy cases, so the mandated coverage (sink registered on a config-loaded instrument) is complete without it.

## Notes

- Tests run: `uv run pytest test/pytest/test_broadcaster.py` → `12 passed in 7.45s`; full `uv run pytest` → `173 passed, 4 warnings in 66.66s` (warnings pre-existing: `PytestUnknownMarkWarning` in `test_apps.py`).
- Observation (not a finding, out of scope per plan rule 6 "Do not widen scope"): `loadConfig` returns a `NamedTemporaryFile(delete=False)` and the test (like the rest of the codebase) only closes it, so a temp station-config file is left in the system temp dir per run. That is pre-existing `loadConfig` behaviour, not introduced by this commit.
- Carried-over user question from round 0 (unchanged): if a user init script adds instruments to the Station via `_runInitScript` (core.py:242, runs after `__init__`), those instruments get no sink; the plan names only two entry points, so this remains a plan-level question, not a 0.3 defect.
