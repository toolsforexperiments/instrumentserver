# 0.2 — plan-checker-deepseek — round 0

Verdict: approve

The commit `8d04b42` implements exactly task 0.2, meets its acceptance criteria point by
point, and stays in scope (no trace of task 0.3's server-side sink registration). No
must-fix or should-fix findings.

## Findings

None.

## Notes

### Acceptance check against the plan task line

Plan task 0.2 (PLAN_parameter_manager_redesign.md:415-419):

> **0.2 `Broadcaster` mixin.** In `base.py` (next to `sendBroadcast`): class
> `Broadcaster` with `add_broadcast_sink(fn)`, `remove_broadcast_sink(fn)`,
> `broadcast(bp: ParameterBroadcastBluePrint)`; sinks stored in a list; exceptions in one
> sink are logged and do not stop the others; no sinks → no-op. `ParameterManager` inherits
> it (no emissions yet). Tests: `test_broadcaster.py` unit part.

- **next to `sendBroadcast`**: `Broadcaster` is defined at base.py:75, immediately after
  `sendBroadcast` (base.py:62-72). OK.
- **`add_broadcast_sink(fn)` / `remove_broadcast_sink(fn)` / `broadcast(bp)`**: all three
  present at base.py:102, base.py:112, base.py:123.
- **sinks stored in a list**: `self._broadcast_sinks: list[...] = []` at base.py:98.
- **exceptions in one sink are logged and do not stop the others**: `broadcast` wraps each
  sink call in `try/except Exception` with `logger.exception()`, iterating over a copy
  (`list(self._broadcast_sinks)`) so a sink removing itself during broadcast does not
  corrupt the loop.
- **no sinks → no-op**: the for-loop over the empty list does nothing.
- **`ParameterManager` inherits it (no emissions yet)**: `class ParameterManager(Broadcaster,
  ParameterGroup)` at params.py:209; no `broadcast` call sites were added.
- **Tests: `test_broadcaster.py` unit part**: new file test/pytest/test_broadcaster.py, 8
  unit tests; none needs a Server.

### Vocabulary (plan rule 2)

Names used — `Broadcaster`, `Broadcast`, `sink`, `Station`, `Parameter Manager` — match the
glossary entries in CONTEXT.md (Broadcaster, Broadcast). "Sink" is the established word in
ADR-0003 ("registers its own broadcast function as a sink") and in the plan task text. The
"instrument mutex" term from D2 / ADR-0003 is referenced correctly (the Server registers
itself as a sink) and nothing confuses it with a Lock. Casing follows plan rule 8: new
methods `add_broadcast_sink`, `remove_broadcast_sink`, `broadcast` are `snake_case`; the new
class `Broadcaster` is `CamelCase`.

### Judgement calls flagged by the coder

- **Removing an unregistered sink is a silent no-op**: `remove_broadcast_sink` returns
  without raising when `fn` is absent. The plan task text does not specify error behaviour,
  and the docstring documents the choice ("Removing a sink that is not registered does
  nothing"). Reasonable; not a defect.
- **Adding the same sink twice is not deduplicated**: matches the plan's "sinks stored in a
  list" and is documented in the class docstring ("adding the same sink twice makes it
  receive every Broadcast twice"). Not a defect.

### Quoted annotations (orchestrator context)

The public method annotations are quoted strings because the client builds proxy methods by
exec-ing the blueprint's call-signature string, which cannot resolve a rendered class
annotation. This is documented in the class docstring ("Keep new blueprint-carrying
annotations quoted like these."). It does not change the runtime signatures of the mixin,
so it does not violate the contract's method names. Acceptable.

### Scope

The commit touches only src/instrumentserver/base.py, src/instrumentserver/params.py, and
test/pytest/test_broadcaster.py. Nothing from task 0.3 (server registers sinks) is present.
Plan rule 6 (do not widen scope) is respected.

### Tests run

`uv run pytest -q test/pytest/test_broadcaster.py` -> 8 passed in 0.01s.