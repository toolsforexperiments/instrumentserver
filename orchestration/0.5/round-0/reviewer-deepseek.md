# 0.5 — reviewer-deepseek — round 0

Verdict: approve

## Findings

No must-fix or should-fix findings.

### F1 — nit
- Where: src/instrumentserver/blueprints.py:80-89
- What: The comment block says "Action strings carried in
  ParameterBroadcastBluePrint.action" but PM_LOCK_UPDATE / PM_TYPE_UPDATE
  are not yet emitted by any code (used from Phase 1.3 / 2.5 onward).
- Why: PM_LOCK_UPDATE and PM_TYPE_UPDATE are defined but currently unused, so
  flake/type checks may flag them; also the comment's claim they are "emitted
  by instruments implementing the Broadcaster contract" is a forward
  statement, not true on this branch yet.
- Suggested fix: Accept as-is; they are required by the task and the plan
  (D10, D26) and will be consumed in later phases.

## Notes

Wire-string verification: every constant equals the exact literal it replaces
(parameter-update / parameter-call / parameter-creation / parameter-deletion,
plus pm-lock-update and pm-type-update from D10/D26). All replacements in
server/core.py, gui/instruments.py and client/application.py are 1:1
literal-to-constant swaps inside existing branches; no logic or ordering
changed. No behaviour change.

grep '"parameter-' across src/ finds literals only in blueprints.py (the new
definitions) plus two sites the coder intentionally left untouched:
log.py:157-158 (a comment and a log-parsing regex `parameter-update:`) and
testing/dummy_instruments/generic.py:454 (a test-helper default argument
`action="parameter-update"`). The task names exactly four modules (server/core,
gui/instruments, client/application, monitoring/listener); log.py and
testing/ are not among them, and the plan's way-of-working rule 6 ("Do not
widen scope") supports leaving them alone. The judgement is correct.
monitoring/listener.py has no literal at all, so nothing to change there.

Tests: `uv run pytest -q` -> 174 passed, 4 warnings in 68.44s. The 4 warnings
are pre-existing PytestUnknownMarkWarning for @pytest.mark.integration in
test_apps.py, unrelated to this commit.