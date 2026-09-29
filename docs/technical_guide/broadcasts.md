# Broadcasts

When a Client sets or reads a parameter, the Server announces it as a
**Broadcast**: a small message on a PUB socket that any number of subscribers
receive at once, from the Server's own GUI to a **Listener** on another
machine. Nobody polls. The
[getting started overview](../getting_started/how_it_works.md) shows what
Broadcasts are for; this page is the deeper twin. It covers what exactly
triggers a Broadcast, what the two frames on the wire look like, how a Client
subscribes with `SubClient`, how the Server forwards Broadcasts to other
machines, and how an instrument emits its own Broadcasts through the
**Broadcaster** contract, with the Parameter Manager's Lock, Type and
side-effect actions as the worked example.

The user-facing side of the Parameter Manager's Broadcasts is in the User
Guide's [Parameter Manager](../user_guide/parameter_manager.md) page, and
Blueprints in general are described in
[Blueprints and Proxies](blueprints_and_proxies.md).

## What triggers a Broadcast

The Server emits every Broadcast from the worker thread that executed the
client request, while that worker holds the instrument's instrument mutex.
Requests for one instrument are serialized by that mutex, so the Broadcasts
about one instrument go out in the order the requests ran.

Four things trigger a Broadcast. A parameter set emits `parameter-update`,
carrying the value that was set. A parameter read emits `parameter-call`,
carrying the value that was read. A client call to a method literally named
`add_parameter` emits `parameter-creation`, and one to `remove_parameter`
emits `parameter-deletion`; the message's `name` is the instrument name and
the call's arguments joined with dots, and a creation carries the
`initial_value` and `unit` keyword arguments the call received. Any other
method call emits nothing.

The examples below run against a Client and the two instruments they use:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client()
>>> dummy = cli.find_or_create_instrument(
...     "dummy",
...     "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule",
... )
>>> pm = cli.find_or_create_instrument(
...     "parameter_manager", "instrumentserver.params.ParameterManager"
... )
```

Captured through a `SubClient` (the next section shows the wiring), the
triggers look like this, in the order they were emitted:

```pycon
>>> dummy.param0.set(0.5)
>>> received[0].action, received[0].name, received[0].value
('parameter-update', 'dummy.param0', 0.5)
>>> dummy.param0()
>>> received[1].action, received[1].value
('parameter-call', 0.5)
>>> pm.add_parameter("extra.gain", initial_value=3, unit="V")
>>> received[2].action, received[2].name, received[2].value, received[2].unit
('parameter-creation', 'parameter_manager.extra.gain', 3, 'V')
>>> pm.remove_parameter("extra.gain")
>>> received[3].action, received[3].name, received[3].value
('parameter-deletion', 'parameter_manager.extra.gain', None)
```

That is the whole list for a plain instrument. An instrument that implements
the Broadcaster contract emits its own Broadcasts on top, which is how the
Parameter Manager announces Locks, Types and the parameters it creates as
side effects.

Every Broadcast carries one of six action strings. They are module constants
in `blueprints.py`, and their values are the wire contract that external
subscribers parse:

| Constant | Action string | Emitted by | `value` carries |
| --- | --- | --- | --- |
| `PARAMETER_UPDATE` | `parameter-update` | the Server, on a parameter set | the new value |
| `PARAMETER_CALL` | `parameter-call` | the Server, on a parameter read | the value that was read |
| `PARAMETER_CREATION` | `parameter-creation` | the Server, on a client call to `add_parameter`; the Parameter Manager, for parameters it creates as side effects | the initial value (`None` when none was given) |
| `PARAMETER_DELETION` | `parameter-deletion` | the Server, on a client call to `remove_parameter` | nothing (`None`) |
| `PM_LOCK_UPDATE` | `pm-lock-update` | the Parameter Manager, one per affected Follower | the Follower's `PMLockBluePrint`, or `None` when its Lock was removed |
| `PM_TYPE_UPDATE` | `pm-type-update` | the Parameter Manager, one per edited Type | the Type's fresh `PMTypeBluePrint`, or `None` when the Type was removed |

## The wire format

The Server publishes Broadcasts on a PUB socket bound to `tcp://*` on the
request port plus one. A Server on the default port 5555 publishes on 5556.

A Broadcast is a two-frame ZMQ message. Frame 1 is the topic: the instrument
name, which is the first dotted component of the message's `name`. Frame 2 is
the JSON of the message's `ParameterBroadcastBluePrint` dict. Here is one
real message as a subscriber received it, both frames:

```
frame 1: 'dummy'
frame 2: {"name": "dummy.param0", "action": "parameter-update", "value": "0.5", "unit": "", "_class_type": "ParameterBroadcastBluePrint"}
```

The topic is what lets subscribers filter per instrument: a SUB socket that
subscribes to `parameter_manager` receives the Parameter Manager's Broadcasts
and nothing else. The subscription is a plain prefix match, so subscribing to
`dummy` also receives the messages of an instrument named `dummy2`. One
Broadcast reaches every subscriber: two subscribers on the same socket
received the identical two frames.

Frame 2 carries every field of the Blueprint as a string, including
`_class_type`, which names the class the dict stands for. `decode` turns the
payload back into the dataclass: `json.loads`, then `deserialize_obj`, which
sees the `_class_type` key and rebuilds a `ParameterBroadcastBluePrint` from
the fields. Decoding the frame 2 payload from above (a subscriber holds it as
`payload`), the numeric strings come back as numbers:

```pycon
>>> from instrumentserver.base import decode
>>> bp = decode(payload)
>>> type(bp).__name__
'ParameterBroadcastBluePrint'
>>> bp.name, bp.action, bp.value, bp.unit
('dummy.param0', 'parameter-update', 0.5, '')
```

One PUB/SUB quirk to know: a subscriber that connects after a Broadcast was
published misses it. The subscription only counts from the moment it reached
the Server's socket. So subscribe before you trigger, and give a fresh
subscriber a moment to connect before you expect messages from it. The
shared helpers sleep briefly after connecting for exactly this reason.

## SubClient

`SubClient` (in `instrumentserver.client.proxy`) is the Qt consumer of
Broadcasts. It opens a SUB socket on the Broadcast port, subscribes to the
instruments you name, or to everything when you pass none, and emits every
received Broadcast as a `ParameterBroadcastBluePrint` on its `update`
signal:

```python
sub = SubClient(instruments=["parameter_manager"])  # or instruments=None: all
thread = QtCore.QThread()
sub.moveToThread(thread)               # the receive loop runs on its own QThread
thread.started.connect(sub.connect)    # connect() runs the loop until stop()
sub.finished.connect(thread.quit)
sub.update.connect(on_broadcast)       # every Broadcast, as a ParameterBroadcastBluePrint
thread.start()
```

That is the exact wiring the Parameter Manager GUI and the shared helpers
use. `stop()` ends the receive loop; stop the thread with it, as the GUI's
`stopListener` does: `sub.stop()`, then `thread.quit()`, then
`thread.wait()`.

This is also how GUIs stay live without polling. The Parameter Manager GUI's
model receives every Broadcast through a `SubClient` and routes the two
Parameter Manager actions straight into its client-side state: a
`pm-lock-update` payload replaces one Follower's Lock, and a `pm-type-update`
payload replaces that one Type, which carries the whole fresh definition, so
the GUI never fetches that Type or Lock again. The next section shows
the payloads; [the Parameter Manager](../user_guide/parameter_manager.md)
page shows the widgets this feeds.

You do not need Qt to subscribe. A plain SUB loop is the whole recipe, and
the Listener is exactly that:

```python
import zmq
from instrumentserver.base import recvMultipart

context = zmq.Context.instance()
socket = context.socket(zmq.SUB)
socket.connect("tcp://localhost:5556")
socket.setsockopt_string(zmq.SUBSCRIBE, "")
while True:
    topic, blueprint = recvMultipart(socket)
    # blueprint is a ParameterBroadcastBluePrint, decoded for you
    ...
```

The [Monitoring](../user_guide/monitoring.md) page covers the Listener and
where it can send what it receives.

## External forwarding

By default the Server publishes Broadcasts at `tcp://*` on the request port
plus one, so every machine that can reach the Server can subscribe there.
The station config can additionally name a second address to publish the
same Broadcasts to, in its `networking` section:

```yaml
networking:
  # Adds an address to broadcast parameter changes to, Example: "tcp://192.168.1.1:6000"
  externalBroadcast: "tcp://192.168.1.1:6000"
```

With that in place the Server binds a second PUB socket on the given address
and sends every Broadcast to both sockets. The copy is the same two-frame
message as the original: a subscriber on the external address received
frames identical to the ones on the local port, and a `SubClient` pointed at
the external address received the Blueprint unchanged. Existing subscribers
need no change; the address is just a second door into the same stream.
That is what puts live UIs and Listeners on other machines: a dedicated
monitoring network or a fixed address of your choosing, with the same
stream on both.

In code, the same setting is the `ipAddresses` dict: `startServer` accepts
`ipAddresses={"externalBroadcast": "tcp://127.0.0.1:6000"}` and binds the
second PUB socket on it. [The Server](../user_guide/server.md) page covers
the config file and where each entry lands.

## The Broadcaster contract

Everything above is the Server broadcasting what it can see: parameter sets
and reads, and calls to methods literally named `add_parameter` and
`remove_parameter`. Structural changes inside an instrument stayed
invisible to everyone else. The Broadcaster contract (ADR-0003) is the
opt-in way for an instrument to announce them itself.

An instrument implements the contract by mixing in `Broadcaster` (in
`instrumentserver.base`), which brings three methods:

- `add_broadcast_sink(fn)` registers `fn` to receive every Broadcast the
  instrument emits. Sinks are stored in a plain list, so registering the same
  sink twice means receiving everything twice.
- `remove_broadcast_sink(fn)` removes it again.
- `broadcast(bp)` sends one `ParameterBroadcastBluePrint` to every
  registered sink. With no sinks registered it is a no-op, so an instrument
  used standalone (no Server, no sinks) emits nothing and nothing raises. An
  exception raised inside one sink is logged and the remaining sinks still
  receive the Broadcast.

The Server knows the contract by shape, not by base class: when an
instrument joins the Station, the Server checks for an
`add_broadcast_sink` attribute and registers its own
`StationServer._broadcastParameterChange` as a sink. This happens at the two
points where instruments enter the Station: created over the wire with
`find_or_create_instrument`, and loaded from the station config at startup.
Instruments without the mixin are registered exactly as before and stay
untouched.

`broadcast` runs on the thread that called the instrument method. For a
client request that is the worker thread holding the instrument mutex, the
same place the Server's own Broadcasts run from. And the emissions use the
same socket, the same topic (the instrument name) and the same two-frame
wire format as the Server's own Broadcasts, so an existing subscriber parses
them without knowing or caring who produced them.

The shipping example is the test instrument the verification of this page
uses, `instrumentserver.testing.dummy_instruments.generic.DummyBroadcasterInstrument`.
Its emitting method is the whole pattern:

```python
def emit_broadcast(self, value=1.0, unit="V", action="parameter-update"):
    bp = ParameterBroadcastBluePrint(
        name=f"{self.name}.param0", action=action, value=value, unit=unit
    )
    self.broadcast(bp)
    return bp
```

The Server registered itself as a sink when the instrument joined the
Station, so `broadcast` put the Blueprint on the Server's PUB socket, and a
`SubClient` received it like any other Broadcast:

```pycon
>>> bcaster = cli.find_or_create_instrument(
...     "bcaster",
...     "instrumentserver.testing.dummy_instruments.generic.DummyBroadcasterInstrument",
... )
>>> bcaster.emit_broadcast(value=3.0, unit="V")
>>> received[0].name, received[0].action, received[0].value, received[0].unit
('bcaster.param0', 'parameter-update', 3.0, 'V')
```

## The Parameter Manager's actions

The Parameter Manager is the first instrument built on the Broadcaster
contract. It emits `pm-lock-update` and `pm-type-update`, and re-emits
`parameter-creation` for parameters it creates as side effects. On the wire
its emissions are indistinguishable from the Server's own: same socket, same
topic, same two-frame format. What the actions mean to use is described in
the User Guide's [Parameter Manager](../user_guide/parameter_manager.md)
page, its Locks and Types sections in particular.

Every Lock method that changes a Lock emits one `pm-lock-update` per
affected Follower (D10). The message's `name` is the Follower's full dotted
path, and its `value` is the Follower's `PMLockBluePrint`, or `None` when
its Lock was removed. So `lock`, `unlock`, `relock`, `toggle_lock` and
`remove_lock` each announce their one change, and `remove_parameter` on a
Target announces every Lock that deleting it drops, one `None` payload per
dropped Follower. The no-op paths emit nothing: unlocking an already
unlocked Lock is not news. Here is the payload of a `pm-lock-update` as it
crossed the wire, stringified fields and all:

```
{"name": "parameter_manager.show.follower", "action": "pm-lock-update", "value": {"target": "parameter_manager.show.target", "locked": "True", "_class_type": "PMLockBluePrint"}, "unit": "", "_class_type": "ParameterBroadcastBluePrint"}
```

Every Type-editing method emits one `pm-type-update` per affected Type
(D22), including `lock_type_parameter` and `unlock_type_parameter`, which
are Lock methods and Type methods at once. The message's `name` is the
Type's full dotted name, `<instrument>.<type>`, and its `value` is the
Type's fresh `PMTypeBluePrint` with its entries (defaults, units and Type
Lock Targets), its Nested Types and its effective set, or `None` when the
Type was removed. The payload carries the whole new definition, which is why
a GUI can replace that one Type locally and recompute its tints with no
follow-up fetch:

```
{"name": "parameter_manager.display", "action": "pm-type-update", "value": {"name": "display", "parameters": {"gain": {"default": "12", "unit": "dB", "target": "None"}}, "nested": {}, "effective": {"gain": {"unit": "dB", "from_type": "display"}}, "_class_type": "PMTypeBluePrint"}, "unit": "", "_class_type": "ParameterBroadcastBluePrint"}
```

Parameters the Parameter Manager creates as side effects are announced as
`parameter-creation`, one per created parameter in creation order: an
`add_type_parameter` that writes an entry into every Instance lacking it, an
`add_instance`, and the Globals Target that a Type Lock with no explicit
Target creates on demand. Direct `add_parameter` and `remove_parameter`
calls keep being announced by the Server, so nothing is ever announced
twice.

The emissions of one method arrive in a fixed order:

- `lock_type_parameter` with the default Target: first the
  `parameter-creation` of the Globals parameter, then one `pm-lock-update`
  per applied Lock, then the Type's `pm-type-update`.
- `add_instance`: first one `parameter-creation` per created parameter, in
  creation order, then the `pm-lock-update`s of the Type Locks the new
  Instance gets at creation. It edits no Type, so no `pm-type-update`.
- `remove_parameter` on a Target: first one `pm-lock-update` with `None` per
  dropped Follower, then one `pm-type-update` per affected Type (the Type
  Locks whose stored Target it was), then the `parameter-deletion` that the
  Server emits once the call has returned.
