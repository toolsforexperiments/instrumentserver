---
status: accepted
date: 2026-09-16
---

# Parameter Manager Types are structural (duck-typed), never a stored membership

A Type in the Parameter Manager is a named shape: a set of relative parameter paths with units, plus Nested Types at named submodules. A submodule is an Instance of a Type purely because it carries every path of that shape with the declared unit; nothing records "q01 is a qubit". Membership is recomputed on demand and never persisted.

## Considered options

- **Explicit registry**: tag submodules with a Type and enforce structure on tagged ones. Rejected: it adds membership state to persist and migrate, and it makes "parameter removed from the Type but still on the Instance" a special case instead of the natural outcome (the row is simply untyped now).
- **Structural, computed** (chosen): matches how the lab thinks about it ("everything shaped like a qubit is a qubit"), needs no membership state, and lets one submodule match several Types (innermost, then largest, claims the tint).

## Consequences

- Deleting a required parameter silently makes a submodule stop matching; that is accepted. Deleting a parameter that is a Lock Target is the case that gets a GUI confirmation, not this one.
- An empty Type matches nothing, so a freshly created Type does not claim the tree.
- Matching walks the tree on every query. Trees are hundreds of parameters; no caching in the first version.
- The `_globals` submodule is excluded from matching at any depth.
