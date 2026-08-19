# How It Works

Laboratory hardware needs a single authoritative owner. If every script, GUI, and
Listener opened its own connection, they could disagree about the instrument's state or
send it conflicting commands. Instrumentserver keeps the real instrument in one
**Server** and gives each consumer a shared way to reach it.

## Following the diagram

The diagram follows one instrument, `generator`, from Server startup through a parameter
call and the resulting **Broadcast**.

```{raw} html
:file: ../_static/animations/request_flow.html
```

### The Server owns the instrument

A QCoDeS driver is a live software object that maintains a connection to an instrument
and translates parameter operations into commands the hardware understands.
Instrumentserver instantiates that driver once and keeps it alive in the Server, independently
of any individual script or GUI. In the diagram, `generator` is this real driver.

The Server can create instruments from its configuration when it starts, as shown here,
or a Client can ask it to create one later. The creation path only determines when the
instrument becomes available. Once created, every Client reaches the same driver and the
same hardware connection. Closing one Client does not close the instrument or transfer
ownership to another Client.

### The Client builds a Proxy Instrument

The **Client** provides the initial connection to the Server and discovers which
instruments are available. When it asks for `generator`, the Server returns a
**Blueprint** rather than the real driver. The Blueprint describes the driver's public
interface, including its parameters, methods, and submodules.

The Client uses this description to construct a **Proxy Instrument** inside your script.
The distinction between the Client and the Proxy is useful: the Client provides access
to the Server as a whole, while each Proxy represents one particular instrument. Your
code can work with the Proxy through the familiar QCoDeS interface without creating the
real driver or connecting to the hardware itself.

The Blueprint is only the information needed to construct that local interface. The
Proxy is not a copy of the instrument or its state. It forwards operations to the one
real driver owned by the Server, which keeps every consumer working with the same
instrument.

### A call reaches the hardware

Calling `generator.frequency(5e9)` looks like an ordinary parameter operation in your
script, but the Proxy does not set anything locally. It forwards the operation to the
Server, which runs it on the real `generator` driver. The driver then translates the
parameter operation into the command understood by the RF source.

From your script's perspective, the call remains a single operation. It completes when
the Server has finished interacting with the instrument and returned the result to the
Proxy. Parameter reads follow the same round trip, so they retrieve the Server's current
instrument state rather than relying on a separate local copy.

### A Broadcast reaches subscribers

The Proxy that made a call already receives its result directly, but other consumers may
also need to know that a parameter changed. The Server therefore publishes a
**Broadcast** that every listening subscriber can receive. One message can update many
consumers without each of them querying the instrument again.

Broadcasts are especially useful for consumers that maintain a view or record of
instrument activity. The Server's GUI uses them to keep its displayed values current,
while a **Listener** can save the same activity elsewhere. These subscribers observe what
happened, but they do not take part in the original call or become owners of the
instrument.

A Broadcast is an announcement, not another copy of the instrument's state. The Server
and its real driver remain authoritative, while subscribers use Broadcasts to keep their
own displays and records in sync.

This overview leaves out the machinery beneath these paths. Continue to the
[Technical Guide](../technical_guide/architecture.md) for the request lifecycle,
networking, concurrency, and other implementation details.
