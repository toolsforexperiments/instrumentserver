---
status: accepted
date: 2026-09-16
---

# Instruments emit their own Broadcasts through an opt-in `Broadcaster` contract

The Server only broadcasts what it can see: parameter sets it executed, and calls whose method name is literally `add_parameter` or `remove_parameter`. Structural changes inside an instrument (a Type edited, a Lock declared, parameters created as a side effect of `add_instance`) were invisible to other clients. We add a small mixin, `Broadcaster`, with `add_broadcast_sink`, `remove_broadcast_sink` and `broadcast(blueprint)`. When an instrument joins the Station (creation over the wire, or loading from config at startup) the Server checks `hasattr(instrument, "add_broadcast_sink")` and registers its own broadcast function as a sink. Instruments without the mixin are registered exactly as before.

## Considered options

- **Hard-code more method names in the Server**, as `add_parameter` is today. Rejected: the Server accumulates one instrument's API.
- **Instrument declares a method-name to action mapping** that the Server consults after each call. Rejected: passive and coarse; cannot express "one message per created parameter" and still couples the Server to method names.
- **Server diffs state after each call.** Rejected: heavy, cannot express Type changes.
- **GUI polling.** Rejected: latency and traffic for nothing.
- **Opt-in emitter contract** (chosen): generic, three lines in the Server, no base-class change, usable by any future Virtual Instrument, and standalone use of the instrument (no sinks) is a no-op.

## Consequences

- Messages use the existing `ParameterBroadcastBluePrint`, same socket, same topic (instrument name), same wire format. Existing subscribers parse them unchanged.
- The Parameter Manager emits `pm-lock-update` (`PMLockBluePrint` payload), `pm-type-update` (`PMTypeBluePrint` payload), and re-emits `parameter-creation` / `parameter-deletion` for parameters it creates or removes as side effects. Direct `add_parameter` / `remove_parameter` calls keep being announced by the Server, so nothing is announced twice.
- `broadcast` runs on the thread that called the instrument method, which for a client request is the worker thread holding the instrument mutex: the same place the Server's own broadcasts already run.
- The `_instrument_locks` code in the Server is not renamed or altered; a comment notes that prose calls it the "instrument mutex".
