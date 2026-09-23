---
status: accepted
date: 2026-09-16
---

# Parameter Locks pull on `get`; nothing is ever pushed into a Follower

A locked Follower answers `get` by asking its Target and returning that value; `set` on a locked Follower raises. The Target knows nothing about its Followers, no value is ever copied into a Follower, and "who follows X" is computed by scanning when asked. The behaviour lives in a `Parameter` subclass (`ManagedParameter`) so the server's call path, the instrument mutex and the existing broadcasts are untouched: the server resolves the dotted path and calls the parameter exactly as it does today.

## Considered options

- **Push on set**: a Target's `set` rewrites every Follower and each rewrite needs its own broadcast. Rejected: it fans one request into many writes, requires the instrument to report side effects to the server for every value change, and forces a dedup rule so Listeners do not log twice.
- **Pull on get** (chosen): minimal change, the broadcast path is unchanged for values, cycle checking is just a walk up the Target chain, and each hop of a chain is decided by that hop's own locked/unlocked state at read time.

## Consequences

- A Follower keeps its own underlying value while locked. Unlocking exposes that own value again (deliberate: "unlock and see its own value" is the point). Profiles store the own value plus the Lock.
- QCoDeS reads the cache, not `get`, for snapshots with `update=False`. `ManagedParameter` therefore reports the Target's value in its snapshot while locked, and the profile writer reads the own value explicitly. Otherwise measurement metadata would record stale values.
- GUIs repaint Followers when they receive a `parameter-update` for the Target; the Parameter Manager emits nothing for values.
- Deleting a Target removes the Locks pointing at it; their Followers become plain parameters.
- Targets are restricted to parameters inside the same Parameter Manager.
