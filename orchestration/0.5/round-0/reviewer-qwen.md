# 0.5 — reviewer-qwen — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: src/instrumentserver/log.py:158
- What: The log-parsing regex still hardcodes the wire string ("parameter-update") instead of interpolating PARAMETER_UPDATE.
- Why: It is coupled to the client's log format; if the action string ever changes this regex would silently stop matching. The coder left it on purpose: log.py is not one of the task's four named files, and it parses log text rather than emitting or comparing the action, so this is a preference, not a task violation.
- Suggested fix: None required. Optionally `re.compile(rf"{PARAMETER_UPDATE}:\s*...")`.

## Notes
- Verified no behaviour change: the four constants equal the former literals exactly;
  `pm-lock-update` / `pm-type-update` had no literal anywhere in the parent commit
  (`git grep` on 884558a finds none), so the two new constants are purely additive
  and match D26.
- `git grep -n "parameter-" b3e6586` over the four named files returns nothing:
  server/core.py, gui/instruments.py, client/application.py are fully converted.
  monitoring/listener.py genuinely contains no action literal (its listeners filter
  on `message.name`, not `message.action`); the coder's report is accurate.
- Two remaining literals judged correctly left: log.py:157-158 (comment + regex,
  see F1) and testing/dummy_instruments/generic.py:454 (default argument of the
  DummyBroadcasterInstrument test helper;   not a named file, equivalent either way).
- Imports are alphabetical and consistent with existing import blocks; no new
  circular dependency (blueprints only imports helpers).
- Remaining `.action` uses in src/ are log f-strings (base.py:137, server/core.py:612)
  and serialization (blueprints.py:378,392); none compare literals, none need change.
- Tests: `uv run pytest` → `174 passed, 4 warnings in 68.92s` (warnings are
  pre-existing unknown-mark warnings in test_apps.py, unrelated).
