# 0.5 — plan-checker-qwen — round 1

Verdict: approve

## Previous findings

- F1 (nit, log.py:157-158 + generic.py:454 literals left untouched): dropped by orchestrator
  (decisions.md "Round 0 merge": both parts "Not sent: nit"). Not sent to the coder, so still
  present in the tree, as expected. No action needed.

## Fix commit check

- eec0c25 adds test_broadcast_action_constants_pin_the_wire_strings to
  test/pytest/test_broadcaster.py; no src/ change.
- The test was requested by the fix list item 1 (test-reviewer-qwen F1, kept by orchestrator);
  it asserts all six constants equal exactly "parameter-update", "parameter-call",
  "parameter-creation", "parameter-deletion", "pm-lock-update", "pm-type-update" — the wire
  values from D26 and ADR-0003 ("Existing subscribers parse them unchanged").
- It can fail: literal-equality asserts, not a tautology.
- No behaviour change: test-only commit; wire strings and API untouched.
- Plan rules: commit message starts with "0.5:", separate fix-round commit, glossary terms
  used ("Broadcast", "subscribers") in docstring and section comment.
- Placement: test_broadcaster.py, which the fix list named as an acceptable file.

## New findings

- None.

## Notes
- `uv run pytest test/pytest/test_broadcaster.py` -> 13 passed in 7.47s (12 before the fix).
- Orchestrator ran the full suite after the fix: 175 passed (decisions.md).
