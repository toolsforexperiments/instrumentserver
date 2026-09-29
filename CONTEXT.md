# Instrumentserver

Distributed control of QCoDeS instruments over ZMQ: one server owns the hardware, many clients talk to it through proxies. Part of the Tools For Experiments suite (sibling of labcore).

## Language

**Server**:
The single process that owns the QCoDeS Station and its instruments, serving requests over ZMQ.
_Avoid_: instrument server (two words), backend

**Client**:
A Python object (or process using one) that sends requests to the Server and receives proxies back.

**Proxy Instrument**:
A client-side object mirroring a server-side instrument, built dynamically from its Blueprint.
_Avoid_: remote instrument, instrument handle

**Blueprint**:
A serializable description of an instrument, parameter, or method that lets clients reconstruct its interface without importing the driver.
_Avoid_: schema, spec

**Broadcast**:
A parameter-change event published by the Server on its PUB socket for any subscriber. Most Broadcasts are produced by the Server when it executes a client request; an instrument that implements the **Broadcaster** contract can also emit its own.
_Avoid_: notification, event stream

**Broadcaster**:
The opt-in contract by which an instrument emits its own Broadcasts: it exposes `add_broadcast_sink` / `remove_broadcast_sink` / `broadcast`, and the Server registers itself as a sink when the instrument joins the Station. Instruments without it are untouched. The Parameter Manager is the first Broadcaster. It emits `pm-lock-update` (payload: a `PMLockBluePrint`, or `None` when its Lock was removed) and `pm-type-update` (payload: a `PMTypeBluePrint`, or `None` when the Type was removed), and re-emits the Server's own `parameter-creation` for the parameters it creates as side effects of Type edits, `add_instance` and Type Lock declarations; it emits no `parameter-deletion`.
_Avoid_: hook, callback, event emitter

**Virtual Instrument**:
An instrument that lives entirely in the Server with no hardware behind it.
_Avoid_: soft instrument, fake instrument (that's a dummy instrument, for testing)

**Parameter Manager**:
The flagship Virtual Instrument: a hierarchical, persistent, profile-aware store of experiment parameters. Its root owns the Type registry and all Lock and Type methods; its submodules are **Parameter Groups**.
_Avoid_: param store, PM

**Client Station**:
A client-side grouping of Proxy Instruments giving one client a scoped view of a shared Server.
_Avoid_: sub-server (colloquial; useful as an explanation, not a name)

**Listener**:
A standalone subscriber to Broadcasts that exports parameter changes to a sink (CSV, InfluxDB).
_Avoid_: monitor, logger

**Detached GUI**:
The Server's GUI running in a separate process so UI failures cannot take down the Server.

**Dummy Instrument**:
A hardware-free test instrument shipped in `instrumentserver.testing` for development and verified documentation.

**Chained Servers**:
A Server acting as a Client of another Server, so instruments can be re-exported downstream.
_Avoid_: server-in-server, daisy-chaining (fine in prose, not as the term)

**Parameter Group**:
A submodule inside the Parameter Manager: a plain container of parameters and nested groups with no file, profile, Type or Lock logic of its own. Every submodule is a Parameter Group; only the root is the Parameter Manager, which extends the group with those responsibilities.
_Avoid_: nested manager, sub-manager

**Type**:
A named set of relative parameter paths (each with a default value and unit), plus **Nested Types** required at named submodules. Type entries carry no value kind and no description. A Type is structural: it describes a shape, not a list of members.
_Avoid_: template, schema, class. Not to be confused with a parameter's **value kind** (numeric, string, bool…), which is the `ParameterTypes` enum in code.

**Nested Type**:
A Type required at a named submodule of another Type, e.g. `qubit` requires a `readout` at its submodule `readout` (`add_nested_type("qubit", "readout", "readout")`). The outer Type's effective parameter set is its own entries plus every Nested Type's set under that submodule name. Nesting can go several levels deep but may not cycle.
_Avoid_: include, import, inherit, extend, subtype

**Instance**:
A Parameter Manager submodule (at any depth, never the root and never under Globals) that carries every parameter path of a Type, including those of its Nested Types, each with the unit the Type declares. Values are irrelevant to matching. Membership is duck-typed and recomputed on demand, never stored. An empty Type has no Instances. A submodule may be an Instance of several Types at once.
_Avoid_: member, tagged submodule

**Claiming Type**:
The Type whose tint a parameter row shows when several Types cover it: the innermost (most deeply nested) Type wins, then the largest.

**Lock**:
A rule attached to one parameter (the **Follower**) naming another parameter, its **Target**. While the Lock is **locked**, the Follower answers `get` with the Target's value and refuses `set`. While **unlocked**, the Follower behaves as a plain parameter but remembers its Target so it can be locked again. Removing the Lock forgets the Target. Locks chain (a Target may itself have a Lock) but never cycle. Values are pulled on `get`; nothing is ever pushed into a Follower.
_Avoid_: link, binding, mirror, source. Not the server's **instrument mutex**.

**Target**:
The parameter a Lock points at. A parameter that is the Target of at least one Lock is marked as such in the tree, its Followers counted locked and unlocked alike. Deleting a Target removes the Locks that pointed at it and clears the Type Lock rules whose stored Target it was; their Followers become plain parameters.
_Avoid_: source

**Follower**:
A parameter that has a Lock. Convenience noun for prose; the code says "the parameter's lock".

**Type Lock**:
A rule on a Type entry naming a Target. Declaring it puts an ordinary, locked Lock on that parameter in every current Instance, and every future Instance gets it at creation. Its default Target is `_globals.<type>.<path>`, created on demand with the entry's default and unit. Instance parameters that already have a Lock on another Target are skipped with a warning. Removing the Type Lock removes only the rule; the Locks it created stay until removed individually. Instances that stop matching keep their Locks.
_Avoid_: group lock, rule (alone)

**Globals**:
The reserved `_globals` submodule of the Parameter Manager that holds the default Targets of Type Locks. Its parameters are created on demand by the Type Lock, not through `add_parameter`, which refuses the name; otherwise a Globals parameter is ordinary: it can be read and set, and it is saved with the profile. Globals is never an Instance of anything.

**Instrument mutex**:
The server's per-instrument `threading.RLock` that serialises concurrent `call`s to one instrument. Prose uses "instrument mutex" so it never collides with **Lock**; the code keeps its current names (`_instrument_locks`) with a rename note only.
_Avoid_: instrument lock (in prose)

## Relationships

- The **Server** owns instruments; **Clients** reach them only through **Proxy Instruments** built from **Blueprints**
- Every parameter change on the **Server** produces a **Broadcast**; **Listeners** and GUIs consume Broadcasts
- A **Client Station** groups Proxy Instruments for one client; many Client Stations can share one Server
- A **Virtual Instrument** is served like any other instrument; the **Parameter Manager** is one
- **Chained Servers** compose: a downstream Server proxies an upstream Server's instruments
- A **Type** is a shape; an **Instance** is any submodule matching it. Adding a parameter to a Type writes it into every Instance; removing one from a Type leaves it on the Instances, which then show it as an untyped row
- A **Lock** makes a **Follower** read its **Target**'s value while locked; a **Type Lock** does this for every Instance of a Type, defaulting its Target to **Globals**

## Example dialogue

> **Dev:** "If I set a value on a **Proxy Instrument**, who finds out?"
> **Domain expert:** "The **Server** executes the set under that instrument's **instrument mutex**, then emits a **Broadcast** — every subscribed GUI and **Listener** sees it, no polling needed."
> **Dev:** "And a **Client Station** is a second server?"
> **Domain expert:** "No — it never owns instruments. It's a scoped view: one client's chosen set of **Proxy Instruments** over the same shared **Server**. If you actually need a second server re-exporting instruments, that's **Chained Servers**."

## Flagged ambiguities

- "apps" — the five console entry points are launchers, not five separate applications; they collapse into three features (Server, Client Station, Monitoring) plus two convenience launchers (Detached GUI, Parameter Manager GUI). Resolved: docs pages follow features, not entry points.
- "sub-server" — used colloquially for **Client Station**; resolved: explanation, not terminology.
- "virtual instrument" vs "dummy instrument" — distinct: virtual = production feature with no hardware; dummy = testing stand-in for hardware.
- "type" — overloaded: the `ParameterTypes` enum is a parameter's **value kind** (drives widget choice); the Parameter Manager's **Type** is a structural shape of a submodule. Resolved: **Type** is the structural concept; the enum is called "value kind" in prose.
- "lock" — overloaded: the server's per-instrument RLock vs the Parameter Manager's user-facing **Lock**. Resolved: the RLock is the **instrument mutex** in prose; code names unchanged.
