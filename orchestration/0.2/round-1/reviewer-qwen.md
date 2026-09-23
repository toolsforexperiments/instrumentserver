# 0.2 — reviewer-qwen — round 1

Verdict: approve

## Previous findings

- N1 (nit) — no `callable` check in `add_broadcast_sink` (src/instrumentserver/base.py:102-110): **dropped by orchestrator.** Decisions log "Round 0 merge": "Not sent: nit (misuse only)." Not in the fix list; base.py is unchanged in 693d4e7. Accepted.
- N2 (nit) — exception log line dereferences `bp.name`/`bp.action` and could raise on a non-blueprint argument (src/instrumentserver/base.py:134-138): **dropped by orchestrator.** "Not sent: nit (contract violation path)." Not in the fix list; unchanged. Accepted.

Both were nits; neither needed fixing for this task. No action expected.

## Fix commit review (693d4e7)

The commit adds exactly one test, `test_adding_the_same_sink_twice_delivers_twice`
(test/pytest/test_broadcaster.py:56-73), and nothing in src/ changes.

- It implements the round-0 fix-list item (raised by test-reviewer-qwen) exactly as
  suggested: one `Broadcaster`, the same sink added twice, one `broadcast` → sink
  called twice (`received == [bp, bp]`), one `remove_broadcast_sink` → a further
  `broadcast` delivered once (`received == [bp, bp, bp]`).
- It pins the semantics documented in the `Broadcaster` class docstring
  ("adding the same sink twice makes it receive every Broadcast twice") that task 0.3
  builds on, and is not vacuous: a deduplicating implementation fails the first
  assertion; a `remove` that drops all equal sinks fails the second.
- Correctness note: `received.append` is a bound method, and the two registered
  references compare equal, so `list.remove` (used in `remove_broadcast_sink`,
  base.py:119-121) removes exactly one registration — the test matches the
  implementation's `in`/`remove` semantics.
- Placement is next to the other sink-registration tests, as the fix list asked;
  name and docstring use glossary terms ("Broadcast", "sink").

## New findings

None. The commit touches only the test file and adds a passing, non-vacuous test;
no behaviour in my focus area changed or weakened.

## Notes

- `uv run pytest -q test/pytest/test_broadcaster.py` → `9 passed in 0.01s` (was 8;
  matches the orchestrator's post-fix run in decisions.md, full suite 170 passed).
- Counts: 0 must-fix, 0 should-fix, 0 new nits.
