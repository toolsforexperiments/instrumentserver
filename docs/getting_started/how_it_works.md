# How It Works

Instrumentserver gives many programs access to the same laboratory hardware without
giving each program its own hardware connection. One server process owns the
instruments; clients send it requests and receive the results.

That division is the central idea behind the project. Everything else—Proxy
Instruments, Blueprints, and Broadcasts—exists to make the shared instrument feel
natural to use.

Before any of the detail, here is the whole thing in motion. Scroll on: the map
stays with you while one request makes the round trip, and then one Broadcast goes
out.

```{raw} html
:file: ../_static/animations/request_flow.html
```

## One owner for every instrument

Opening the same instrument from several processes is risky. Some devices permit only
one connection, while others accept several but do nothing to prevent commands from
different programs from being interleaved. Either way, coordinating access becomes the
responsibility of every measurement script, notebook, GUI, and monitor.

Instrumentserver puts that coordination in one place:

% TODO: Make this a proper and pretty diagram
```text
measurement script ──┐
notebook ────────────┼── requests ──> Server ──> QCoDeS Station ──> instruments
instrument GUI ──────┤                    │
monitor ─────────────┘                    └── updates ──> subscribers
```

The **Server** holds the
[QCoDeS Station](https://microsoft.github.io/Qcodes/api/station.html) and creates the
real instrument objects. It is the only process that opens connections to the hardware. A **Client** can run
in the same process, elsewhere on the same computer, or on another computer; it uses
the same network protocol in every case.

```python
from instrumentserver.client import Client

local = Client()
remote = Client(host="192.168.1.42", port=5555)
```

The server can run with its own GUI or without one. Instrument controls opened from the
server window still use an embedded client to make calls. The detached GUI is a separate
client that connects by host and port. Instrument access therefore does not depend on a
particular window being open.

## A local stand-in for a remote instrument

When a client asks for an instrument, it receives a **Proxy Instrument**, not the real
driver object:

```python
generator = local.find_or_create_instrument(
    "generator",
    "instrumentserver.testing.dummy_instruments.rf.Generator",
)

generator.frequency(5e9)  # set on the server
frequency = generator.frequency()  # get from the server
```

The proxy looks like a QCoDeS instrument. It has parameters, methods, and submodules,
but it does not communicate with the hardware itself. Calling a proxy parameter or
method sends a request to the Server, where the corresponding operation runs on the
real instrument. The result is then returned to the caller.

Parameter calls do not use a previously fetched value as their answer. Each
`generator.frequency()` call makes a new request, so two clients see the same
server-side state when they read the parameter:

```python
# client A
generator_a.frequency(7e9)

# client B
generator_b.frequency()
# 7000000000.0
```

Like ordinary QCoDeS parameters, a Proxy Parameter may retain its last value in its
local QCoDeS cache. That cache is useful as a record of the last call, but it is not the
shared source of truth. Call the parameter to read the current value from the Server.

## How the proxy learns the interface

The client usually does not import the instrument driver, so it needs another way to
discover that `generator` has a `frequency` parameter. The Server supplies a
**Blueprint**: serializable metadata describing an instrument's parameters, public
methods, submodules, documentation, and method signatures.

The client builds the proxy from that description. It caches Blueprints to avoid
repeating the same introspection request, while parameter gets and method calls continue
to go to the Server. If an instrument changes its interface at runtime—for example, by
adding a parameter—the proxy can refresh its Blueprint.

This separation means the hardware driver normally needs to be installed only on the
server computer. There is one important boundary: values returned over the network must
be serializable. Built-in values and supported containers work directly. Reconstructing
certain rich values, such as an enum or a supported custom object, may require the
defining package on the client as well. NumPy arrays require NumPy, which is already an
instrumentserver dependency.

## What happens during a call

Consider `generator.frequency(5e9)`. The complete trip is:

1. The Proxy Parameter creates a request naming `generator.frequency` and carrying the
   value `5e9`.
2. The Client serializes the request and sends it to the Server.
3. The Server dispatches the request to a worker thread and locates the real parameter
   in its Station.
4. The worker acquires the lock for `generator`, calls the parameter, and releases the
   lock when the operation finishes.
5. The Server sends the result back to the Client. It also publishes a parameter-update
   notification for anything subscribed to generator updates.

Requests for the same instrument are serialized by the instrument's lock. Requests for
different instruments can run concurrently. A long operation on one instrument
therefore does not have to block unrelated work on another instrument, while two clients
cannot issue overlapping calls to the same driver.

## Broadcasts keep views up to date

Request and response traffic is one-to-one: a result goes back to the client that made
the call. Live displays need a separate one-to-many path. The Server therefore publishes
a **Broadcast** whenever a parameter is read or set through instrumentserver, and when a
dynamic parameter is created or removed.

GUIs and monitoring processes subscribe to these messages. A set produces a
`parameter-update` Broadcast, so every open instrument view can display the new value
without polling the parameter itself. A get produces a `parameter-call` Broadcast,
which can also feed a monitor. Broadcasts travel on the port immediately above the
request port: a server on port `5555` publishes on `5556`.

Broadcasts are notifications, not a second store of instrument state. They may be
missed if a subscriber is disconnected, and they do not detect a value changed directly
at the hardware or by software outside instrumentserver. To observe values that change
on their own, configure parameter polling; each poll performs a server-side get, which
then produces a Broadcast.

## The pieces in one sentence

The Server owns the real QCoDeS instruments, Blueprints describe their interfaces,
Proxy Instruments turn client-side calls into server requests, and Broadcasts fan
parameter activity out to GUIs and monitors.

The [User Guide](../user_guide/index.md) explains how to use each of those features. For
the socket, threading, serialization, and locking details, continue to the
[Technical Guide](../technical_guide/index.md).
