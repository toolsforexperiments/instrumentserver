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
A parameter-change event published by the Server on its PUB socket for any subscriber.
_Avoid_: notification, event stream

**Virtual Instrument**:
An instrument that lives entirely in the Server with no hardware behind it.
_Avoid_: soft instrument, fake instrument (that's a dummy instrument, for testing)

**Parameter Manager**:
The flagship Virtual Instrument: a hierarchical, persistent, profile-aware store of experiment parameters.
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

## Relationships

- The **Server** owns instruments; **Clients** reach them only through **Proxy Instruments** built from **Blueprints**
- Every parameter change on the **Server** produces a **Broadcast**; **Listeners** and GUIs consume Broadcasts
- A **Client Station** groups Proxy Instruments for one client; many Client Stations can share one Server
- A **Virtual Instrument** is served like any other instrument; the **Parameter Manager** is one
- **Chained Servers** compose: a downstream Server proxies an upstream Server's instruments

## Example dialogue

> **Dev:** "If I set a value on a **Proxy Instrument**, who finds out?"
> **Domain expert:** "The **Server** executes the set under that instrument's lock, then emits a **Broadcast** — every subscribed GUI and **Listener** sees it, no polling needed."
> **Dev:** "And a **Client Station** is a second server?"
> **Domain expert:** "No — it never owns instruments. It's a scoped view: one client's chosen set of **Proxy Instruments** over the same shared **Server**. If you actually need a second server re-exporting instruments, that's **Chained Servers**."

## Flagged ambiguities

- "apps" — the five console entry points are launchers, not five separate applications; they collapse into three features (Server, Client Station, Monitoring) plus two convenience launchers (Detached GUI, Parameter Manager GUI). Resolved: docs pages follow features, not entry points.
- "sub-server" — used colloquially for **Client Station**; resolved: explanation, not terminology.
- "virtual instrument" vs "dummy instrument" — distinct: virtual = production feature with no hardware; dummy = testing stand-in for hardware.
