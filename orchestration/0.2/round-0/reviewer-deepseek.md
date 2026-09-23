# 0.2 — reviewer-deepseek — round 0

Verdict: approve

## Findings

No findings at must-fix or should-fix severity.

### F1 — nit
- Where: src/instrumentserver/base.py:98-100
- What: `__init__`'s `_broadcast_sinks` annotation is an unquoted
  `Callable[[ParameterBroadcastBluePrint], None]`, while the class docstring
  (lines 90-93) instructs that blueprint-carrying annotations be quoted
  because the client proxy execs the call-signature string.
- Why: Not a bug — `__init__` is never a proxied method (only public
  `add_broadcast_sink` / `remove_broadcast_sink` / `broadcast` appear in the
  blueprint, and all three are correctly quoted), so no exec path can trip on
  it. It is only inconsistent with the stated convention.
- Suggested fix: Either quote it for consistency, or note in the docstring
  that the quoting rule applies to proxied (blueprint-listed) methods only.
  No behavioural change either way.

## Notes

- Commit: 8d04b42 `0.2: add Broadcaster mixin and mix it into ParameterManager`
  (the only commit in `a1bce5e..8d04b42`).
- Verified in my lane:
  - `broadcast` iterates `list(self._broadcast_sinks)` (a copy), so a sink
    registering/removing sinks mid-broadcast cannot raise
    `RuntimeError: list changed during iteration`; the plan's "exceptions in
    one sink are logged and do not stop the others" is satisfied and the
    remaining sinks still run.
  - `remove_broadcast_sink` uses `in` + `list.remove`, so removing an
    unregistered sink is a silent no-op and removing one of two equal sinks
    deletes only the first occurrence — consistent with the class docstring's
    documented no-dedup behaviour (the coder's flagged judgement calls). Not a
    defect against the plan, which only says "sinks stored in a list".
  - MRO check: `ParameterManager(Broadcaster, ParameterGroup)` — `__init__`
    at params.py:233 calls `super().__init__(name)` which lands in
    `Broadcaster.__init__(*args, **kwargs)`, initialising `_broadcast_sinks`
    then forwarding to `ParameterGroup.__init__`. A real `ParameterManager`
    constructs correctly (proven by the passing test). Submodules stay plain
    `ParameterGroup` (no Broadcaster), matching D15.
  - The quoted-annotation claim is sound: proxy.py:376-382 builds and `exec`s
    the method source with `globs` = `wrap/qcodes/collections` plus
    `from typing import *`; an unquoted class annotation would render a name
    (`ParameterBroadcastBluePrint`) that the exec'd source cannot resolve.
  - New import `from collections.abc import Callable` and
    `ParameterBroadcastBluePrint` in base.py do not shadow or clash with
    existing names; no caller breakage found (no existing API removed or
    changed).
- Tests run: `uv run pytest -q test/pytest/test_broadcaster.py` → 8 passed.
  Did not run the full suite (no need for this review; unit part green).