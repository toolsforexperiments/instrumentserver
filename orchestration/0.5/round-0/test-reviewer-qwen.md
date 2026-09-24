# 0.5 — test-reviewer-qwen — round 0

Verdict: changes-needed

## Findings

### F1 — should-fix — no test pins the wire-string values of the new constants
- Where: src/instrumentserver/blueprints.py:84-89 (constants); suggested home for the missing test: test/pytest/test_broadcaster.py
- What: only 1 of the 6 new action constants is pinned by any test that compares a server emission against a hardcoded wire string.
- Why: the task's core claim is "No behaviour change" — the wire strings stay what they are.
  Since every in-repo emitter and consumer now shares the constant, a typo in a constant
  value passes the whole suite while breaking external subscribers (ADR-0003: "Existing
  subscribers parse them unchanged").
  Pinned today: PARAMETER_CREATION, via test/pytest/test_param_manager.py:117
  (server emits through the constant, test asserts the literal "parameter-creation").
  Not pinned: PARAMETER_UPDATE, PARAMETER_CALL, PARAMETER_DELETION (test_broadcaster.py:223
  asserts the literal "parameter-update" but that emission comes from the dummy helper's
  literal default at testing/dummy_instruments/generic.py:454, not from the constant; no
  test asserts "parameter-call" or "parameter-deletion" at all), and PM_LOCK_UPDATE /
  PM_TYPE_UPDATE (unused in src until Phases 1-3, no test references the strings; their
  names are fixed by D26).
- Suggested fix: add a small unit test (no server) that imports the six constants from
  instrumentserver.blueprints and asserts each equals exactly "parameter-update",
  "parameter-call", "parameter-creation", "parameter-deletion", "pm-lock-update",
  "pm-type-update". Expected result: any constant value drift fails the test.

## Notes
- Named tests for this task: "whole suite green" (task names no specific test file);
  ran the full suite. Summary line: `174 passed, 4 warnings in 68.55s (0:01:08)`.
  The 4 warnings are pre-existing PytestUnknownMarkWarning for pytest.mark.integration in
  test/pytest/test_apps.py; not introduced by this commit.
- The commit adds no new or changed tests and weakens, deletes or skips none.
- No-behaviour-change verified on the wire: each of the four in-use constants equals its
  previous literal exactly (parameter-update, parameter-call, parameter-creation,
  parameter-deletion); the diff is purely literal-to-constant swaps with no logic edits.
  PM_LOCK_UPDATE / PM_TYPE_UPDATE match D26 and are unused for now, as intended.
- monitoring/listener.py: confirmed zero `parameter-` literals and no `action` handling;
  the coder's claim holds, so nothing to use there.
- Deliberately untouched literals, judged against the task text: log.py:157-158 is a
  comment plus a regex that parses client-station log lines, and log.py is not one of the
  four named modules; testing/dummy_instruments/generic.py:454 is a test-helper default
  argument, also outside the named-file list. Plan scope rule "Do not widen scope" supports
  leaving both. From the test side, keeping generic.py:454 a literal is actually beneficial:
  it keeps test_broadcaster.py:223 an independent literal check of that wire string; using
  the constant there would make the assertion circular. No finding.
- test/pytest/test_base.py and test_broadcaster.py make_bp() use hardcoded
  "parameter-update" literals when building blueprints; that is correct and independent,
  not a weakness.
