# 0.2 — plan-checker-qwen — round 0

Verdict: approve

## Findings

None.

## Notes

- Acceptance, point by point, against the task line "**0.2 `Broadcaster` mixin.** In `base.py`
  (next to `sendBroadcast`): class `Broadcaster` with `add_broadcast_sink(fn)`,
  `remove_broadcast_sink(fn)`, `broadcast(bp: ParameterBroadcastBluePrint)`; sinks stored in
  a list; exceptions in one sink are logged and do not stop the others; no sinks → no-op.
  `ParameterManager` inherits it (no emissions yet). Tests: `test_broadcaster.py` unit part.":
  - Placed in `src/instrumentserver/base.py:75`, directly after `sendBroadcast` (lines 62–72) ✓
  - All three methods present with the plan's names ✓
  - Sinks stored in a list (`_broadcast_sinks`, base.py:98–100) ✓
  - Per-sink try/except with `logger.exception`; iteration over a snapshot
    (`list(self._broadcast_sinks)`) so a sink removing itself mid-broadcast cannot break the
    others (base.py:131–139) ✓
  - No sinks → loop over empty list → no-op ✓
  - `class ParameterManager(Broadcaster, ParameterGroup)` (params.py:209); no
    `self.broadcast(...)` call anywhere in `params.py`, matching "(no emissions yet)" ✓
  - `test/pytest/test_broadcaster.py` contains only the unit part (no server fixture); the
    file's docstring defers the server part, which task 0.3 owns. Eight tests cover: no-op
    without sinks, sink receipt, registration order, exception-logged-and-others-run
    (asserts exactly one ERROR record, the sink's name in the message, and `exc_info`),
    removal, removing an unregistered sink, and the mixin on a real `ParameterManager` ✓
- Quoted annotations. The plan's literal signature is `broadcast(bp:
  ParameterBroadcastBluePrint)`; the commit quotes all public-method annotations. I verified
  empirically that this was necessary: `str(inspect.signature(...))` of an unquoted class
  annotation renders `instrumentserver.blueprints.ParameterBroadcastBluePrint`, and
  `client/proxy.py:_makeProxyMethod` (lines 355–382) execs that string with a restricted
  globals dict — unquoted fails with `NameError: name 'instrumentserver' is not defined`,
  quoted execs clean. This matches the plan's own fact that "any new public method on
  `ParameterManager` is callable from clients with no client changes" and would otherwise
  have broken rule 7 ("Do not break the existing API"). The deviation is documented in the
  class docstring (base.py:90–93) and in `orchestration/0.2/decisions.md`. Not a defect.
- Judgement calls flagged by the coder, both acceptable and documented:
  - Removing an unregistered sink is a silent no-op — stated in the `remove_broadcast_sink`
    docstring and covered by `test_removing_a_sink_that_was_never_added_is_a_noop`. The plan
    does not prescribe the opposite.
  - Duplicate `add_broadcast_sink` is not deduplicated — stated in the class docstring;
    consistent with "Sinks are stored in a plain list".
- Plan rules: glossary vocabulary throughout docstrings, log message and test docstring
  ("Broadcast", "sink", "Server", "Station", "client", "blueprint"; no avoided terms such as
  "notification"/"hook"/"callback"). Casing per rule 8 (`Broadcaster`, `snake_case`
  methods). Commit message starts with `0.2:`. No CONTEXT.md change needed: "Broadcaster" is
  already a glossary term (CONTEXT.md:26) and no new term was introduced.
- Scope: diff touches only `src/instrumentserver/base.py` (imports + mixin),
  `src/instrumentserver/params.py` (import, base class, docstring), and the new test file.
  No work from 0.3/0.4/0.5 leaked in.
- ADR-0003 consistent: opt-in contract, standalone use is a no-op, `ParameterBroadcastBluePrint`
  as the payload type, and server-side registration explicitly left to task 0.3
  (`hasattr(instrument, "add_broadcast_sink")`).
- Tests run: `uv run pytest -q test/pytest/test_broadcaster.py` → `8 passed in 0.01s`.
  `uv run pytest -q` (full suite) → `169 passed, 4 warnings in 58.54s` (same count and the
  same pre-existing warnings as the orchestrator's run; the unknown-mark warning comes from
  `test/pytest/test_apps.py`, not this commit).
