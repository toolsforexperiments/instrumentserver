# 0.5 — plan-checker-deepseek — round 1

Verdict: approve

## Previous findings

- F1 (nit) log.py:158 regex keeps the literal: dropped by orchestrator
  (decisions.md "Not sent: nit").
- F2 (nit) dummy_instruments/generic.py:454 default keeps the literal:
  dropped by orchestrator (decisions.md "Not sent: nit").

## Findings

No new must-fix or should-fix findings.

## Notes

- Fix commit eec0c25 adds test_broadcast_action_constants_pin_the_wire_strings
  to test/pytest/test_broadcaster.py, asserting each of the six constants
  against its exact wire string. No src/ change.
- It is a no-server unit test, consistent with "Tests per layer" (plan
  way-of-working rule 5).
- The pinned values match what the constants held in round 0 and the D26
  action names, so wire strings are still unchanged: no behaviour change.
- Test-only change; nothing in my focus area (scope, vocabulary, wire
  strings, plan rules) is broken or weakened.
- Full suite: 175 passed (run by the orchestrator); fix adds one passing
  test, so 175 includes it.