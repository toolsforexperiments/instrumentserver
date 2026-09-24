# 0.5 — plan-checker-qwen — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: src/instrumentserver/testing/dummy_instruments/generic.py:454, src/instrumentserver/log.py:157-158
- What: two `parameter-` literals remain under src/, both left untouched on purpose by the coder.
- Why: task text says "use them in `server/core.py`, `gui/instruments.py`, `client/application.py`,
  `monitoring/listener.py` wherever the literals appear" and these files are not on that list;
  Way-of-working rule 1 is "Do not widen scope". The coder's call is consistent with the task text.
  generic.py:454 is a default argument that sets an action string, so `PARAMETER_UPDATE` there
  would be a one-line consistency win; the log.py regex parses log text, not the wire string.
- Suggested fix: none for 0.5; optionally adopt the constants in a later task that touches those files.

## Notes
- Single commit b3e6586 in the range; message starts with "0.5:" per session protocol step 6.
- All six constants defined in blueprints.py; values match pre-commit literals exactly:
  "parameter-update", "parameter-call", "parameter-creation", "parameter-deletion",
  plus "pm-lock-update" / "pm-type-update" per D26 ("actions `pm-lock-update`, `pm-type-update`")
  and D10 ("Action strings stay strings; module-level constants for all actions").
- No behaviour change: every substitution is byte-identical (diff read line by line);
  `ParameterBroadcastBluePrint` and the wire format are untouched; no name collisions in blueprints.py.
- monitoring/listener.py verified clean: no `parameter-` literal at all; its listeners filter on
  `message.name` only, never on action, so the coder's report is correct.
- No `parameter-` occurrence left in any of the four named files (rg across all four: zero matches).
- PM_LOCK_UPDATE / PM_TYPE_UPDATE are defined but unused for now, as expected: their emitters
  arrive in tasks 1.3 and 2.5.
- Test files keep literals (test_base.py, test_broadcaster.py, test_param_manager.py); the task
  asks only for whole-suite green and those literal asserts pin the wire strings.
- Whole suite: `uv run pytest` -> `174 passed, 4 warnings in 68.60s`; warnings are pre-existing
  `PytestUnknownMarkWarning` in test_apps.py, unrelated to this commit.
- Working tree has uncommitted orchestrator files (PLAN_parameter_manager_redesign.md,
  orchestration/RUNS.md, orchestration/0.5/); the commit itself touches only the four source files.
