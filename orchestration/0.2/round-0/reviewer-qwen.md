# 0.2 — reviewer-qwen — round 0

Verdict: approve

## Findings

### N1 — nit
- Where: src/instrumentserver/base.py:102-110
- What: `add_broadcast_sink` does not check that `fn` is callable; a non-callable
  "sink" stays registered and raises `TypeError` on every subsequent
  `broadcast`, which is then swallowed and logged as a sink exception.
- Why: The contract types the argument as a callable, so this only matters on
  misuse, but the failure mode is a permanently failing sink that hides a
  registration-time mistake behind per-Broadcast log noise.
- Suggested fix: One-line fail-fast at registration: `if not callable(fn): raise
  TypeError(...)`. Optional; behaviour otherwise matches the plan's contract.

### N2 — nit
- Where: src/instrumentserver/base.py:134-138
- What: The exception log line dereferences `bp.name` / `bp.action` while
  handling a sink exception.
- Why: If a caller passes a non-`ParameterBroadcastBluePrint` (contract
  violation) and a sink raises, the f-string itself raises `AttributeError`,
  which escapes `broadcast` instead of being logged. Extremely narrow edge of
  an already-invalid call, so preference only.
- Suggested fix: Log via `getattr(bp, "name", bp)` / `getattr(bp, "action",
  bp)` or just `bp!r`, so the logging path cannot raise.

## Notes

- Tests run: `uv run pytest -q test/pytest/test_broadcaster.py` → `8 passed in
  0.01s`; full suite `uv run pytest -q` → `169 passed, 4 warnings in 58.30s`
  (same result the orchestrator recorded in decisions.md).
- Plan conformance of the shape: all three method names and the
  `broadcast(bp: ParameterBroadcastBluePrint)` signature match the task; sinks
  are a list; no sinks → no-op; one sink's exception is logged (ERROR with
  traceback, which satisfies "logged") and does not stop the others
  (`test_exception_in_one_sink_is_logged_and_others_still_run` verifies
  order, level, and that later sinks still receive); `ParameterManager`
  inherits the mixin (MRO `ParameterManager → Broadcaster → ParameterGroup →
  InstrumentBase`, valid) and emits nothing yet (no `self.broadcast` calls in
  `params.py`). The class sits in `base.py` directly after `sendBroadcast`,
  as the plan says.
- The coder's reported judgement call about quoted annotations is correct and
  empirically verified, not a style choice: I reproduced the client pipeline.
  `bluePrintFromInstrumentModule` (`blueprints.py:334-344`) picks up all three
  inherited public methods via `dir(ins)`, and `str(inspect.signature(...))`
  of an *unquoted* annotation renders the dotted qualified name
  (`instrumentserver.blueprints.ParameterBroadcastBluePrint`), which the
  client's `exec` in `_makeProxyMethod` (`client/proxy.py:376-382`, globs
  limited to `wrap`/`qcodes`/`collections` + `typing`) cannot resolve →
  `NameError` during proxy construction, i.e. every client that builds a
  ParameterManager proxy would break. Quoted annotations render as string
  literals and exec cleanly (verified for all three methods). The class
  docstring paragraph documenting this for Phase 1 is a useful guardrail.
- The two flagged judgement calls (remove of an unregistered sink is a silent
  no-op; duplicate add is not deduplicated) are consistent with the plan,
  documented in the docstring and the `remove` docstring respectively, and
  covered by tests. I agree with both; one note on coherence: with duplicates,
  one `remove_broadcast_sink` removes one registration, which matches the
  "added twice → receives twice" semantics.
- Observation for task 0.3 (not a defect of this commit): once the Server
  registers itself as a sink, `pm.broadcast` is callable from any remote
  client (the plan, line 158, makes every new public method proxyable, and
  call args are JSON-decoded with `deserialize_obj`, so a dict carrying
  `_class_type` becomes a real `ParameterBroadcastBluePrint`). A client could
  then inject arbitrary blueprints into the PUB broadcast stream. `
  add_broadcast_sink` is effectively not operable over the wire (a callable
  is not JSON-serialisable), so the exposure is `broadcast` only. This is
  inherent to the plan's "public methods are proxyable" design; worth a
  sentence in the 0.3 review or the plan checker's lane.
- No import-cycle risk introduced: `params.py → base.py → blueprints.py` and
  `base.py → blueprints.py` already existed in the parent commit; full suite
  green confirms.
- Commit hygiene: exactly one commit `8d04b42` in the range, message prefixed
  `0.2:`, only the three expected files touched; no test is vacuous — each
  would fail if its behaviour regressed (no-op without sinks, delivery,
  registration order, exception isolation + logging, removal, unregistered
  removal, mixin inheritance on a real `ParameterManager`).
