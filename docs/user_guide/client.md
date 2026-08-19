# Python client

The Python Client is the interface to instruments owned by a Server. It represents a
remote instrument in the server as a local Proxy Instrument with the same parameters and methods as its real
QCoDeS driver. The [Quickstart](../getting_started/quickstart.md) gives a shorter first
look at instrumentserver. For a conceptual overview, see
[How it works](../getting_started/how_it_works.md).

Each section is self-contained and assumes the same Server remains running.

## Connections and instrument discovery

The examples use a local Server started with:

```{prompt} bash
instrumentserver -p 5555 -a 127.0.0.1
```

This opens the Server GUI, where instruments appear as the examples create them. The
Client examples work in a terminal, a Jupyter notebook, or anywhere you can run python.

:::{note}
Port `5555` and address `127.0.0.1` are the defaults, so plain `instrumentserver` starts
the same local Server. The `-p` option selects the request port, and `-a` adds a
listening address. The Server always includes the loopback address.
[The Server](server.md) covers addresses, ports, and remote connections.
:::

Clients can stay open for an entire measurement or be created only when needed, though
we usually keep one for the duration of a measurement. In either case, closing the
Client releases the network resources used by its connection to the Server.

The Client is created with the Server's host and request port (if using defaults, you can just use `Client()`):

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client(host="localhost", port=5555)
```

Once the Client exists, `list_instruments()` reports the instruments that the Server
already owns:

```pycon
>>> cli.list_instruments()
[]
```

`find_or_create_instrument` adds the dummy RF generator used throughout this page:

```pycon
>>> generator = cli.find_or_create_instrument(
...     "generator",
...     "instrumentserver.testing.dummy_instruments.rf.Generator",
... )
>>> cli.list_instruments()
['generator']
```

`find_or_create_instrument` returns a Proxy Instrument. If the Server doesn't have the
requested name, it imports the class and creates the real instrument. If the name
already exists, the Server returns a Proxy for that instrument. The method mirrors
QCoDeS' [`find_or_create_instrument`](https://microsoft.github.io/Qcodes/api/instrument/index.html#qcodes.instrument.find_or_create_instrument).
Instrumentserver, however, matches only by name. For an existing name, it does not check
the class path supplied for creation.

The Server GUI shows the generator as soon as the Server creates it:

```{image} ../_static/getting_started/quickstart/server_generator_light.png
:class: only-light
:alt: The Server GUI showing the newly created generator
```

```{image} ../_static/getting_started/quickstart/server_generator_dark.png
:class: only-dark
:alt: The Server GUI showing the newly created generator
```

:::{note}
`cli.get_instrument("generator")` covers the case where an instrument already exists and
no creation class is needed. It returns a Proxy without creating an instrument.
:::

A Client remains connected until `disconnect()` closes its ZMQ connection:

```pycon
>>> cli.disconnect()
```

A context manager gives small scripts the same lifecycle. It disconnects the Client when
the block exits:

```pycon
>>> with Client(host="localhost", port=5555) as cli:
...     generator = cli.get_instrument("generator")
...     print(generator.frequency())
10000000000.0
```

:::{note}
Constructing `Client` opens its ZMQ connection but does not perform a handshake with the
Server. The first request, such as `list_instruments()`, is what confirms that the Server
can reply. [Errors and timeouts](#errors-and-timeouts) describes what happens when it
cannot.
:::

## Proxy instruments

The same call creates or retrieves the generator for this self-contained example:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client()
>>> generator = cli.find_or_create_instrument(
...     "generator",
...     "instrumentserver.testing.dummy_instruments.rf.Generator",
... )
```

A Proxy Parameter is a QCoDeS
[`Parameter`](https://microsoft.github.io/Qcodes/api/parameters/#qcodes.parameters.Parameter)
with get and set commands that call the Server. The normal QCoDeS callable form reads
and writes the parameter:

```pycon
>>> generator.frequency()
10000000000.0
>>> generator.frequency(5e9)
>>> generator.frequency()
5000000000.0
```

The explicit QCoDeS methods make the same calls:

```pycon
>>> generator.frequency.set(6e9)
>>> generator.frequency.get()
6000000000.0
```

The Client also proxies driver methods. This dummy resonator has a method that changes
its simulated resonance frequency:

```pycon
>>> resonator = cli.find_or_create_instrument(
...     "resonator",
...     "instrumentserver.testing.dummy_instruments.rf.ResonatorResponse",
... )
>>> resonator.modulate_frequency(delta=1e6)
```

The Server runs the method on the real `resonator`, not on the Proxy Instrument.
`disconnect()` then closes the example's Client:

```pycon
>>> cli.disconnect()
```

## Parameter snapshots

The Client can collect parameter values, apply a group of values, and save or restore
experiment state. These methods work with any existing Server-owned instrument.

This example starts from fixed generator values so the output is reproducible:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client()
>>> generator = cli.find_or_create_instrument(
...     "generator",
...     "instrumentserver.testing.dummy_instruments.rf.Generator",
... )
>>> generator.frequency(5e9)
>>> generator.power(-42)
>>> generator.rf_on(True)
```

`getParamDict` returns a flat dictionary. Each key is the dotted path to a parameter:

```pycon
>>> values = cli.getParamDict("generator", get=True)
>>> values
{'generator.frequency': 5000000000.0, 'generator.power': -42, 'generator.rf_on': True}
```

`setParameters` accepts that same flat shape:

```pycon
>>> cli.setParameters(
...     {
...         "generator.frequency": 6e9,
...         "generator.power": -30,
...     }
... )
```

`paramsToFile` writes the generator's current values to a JSON file:

```pycon
>>> cli.paramsToFile(
...     "generator-parameters.json",
...     instruments=["generator"],
...     get=True,
... )
```

The file groups parameter names under each instrument:

```json
{
  "generator": {
    "frequency": 6000000000.0,
    "power": -30,
    "rf_on": true
  }
}
```

After the values change, `paramsFromFile` restores the saved state:

```pycon
>>> generator.frequency(7e9)
>>> generator.power(-20)
>>> generator.rf_on(False)
>>> cli.paramsFromFile(
...     "generator-parameters.json",
...     instruments=["generator"],
... )
>>> generator.frequency()
6000000000.0
>>> generator.power()
-30
```

Both file methods run in the Client process, so relative paths refer to the Client's
working directory, not the Server's. Without `instruments`, `paramsToFile` saves every
Server instrument and `paramsFromFile` restores every matching entry in the file.

:::{warning}
`setParameters` and `paramsFromFile` cannot currently restore Boolean values.
Deserialization converts `True` and `False` to `1.0` and `0.0`, which fail QCoDeS Boolean
validation. Numeric values in the same operation still restore correctly. See
[issue #152](https://github.com/toolsforexperiments/instrumentserver/issues/152).
:::

:::{note}
`setParameters` does not accept the nested JSON shown above. It expects flat dotted keys
and currently ignores the nested shape after logging a Server-side error.
`paramsFromFile` flattens the saved JSON before sending it.
:::

:::{note}
The [Parameter Manager](parameter_manager.md) has a separate profile workflow. Its
`toFile` and `fromFile` methods run on the Server, preserve units, and can create or
remove hierarchical parameters. Managed profiles use this workflow rather than a
snapshot of existing instruments.
:::

`disconnect()` closes the Client used for the snapshot example:

```pycon
>>> cli.disconnect()
```

## Errors and timeouts

By default, the Client turns Server-side failures into local exceptions. The dummy
generator, for example, accepts frequencies only up to 20 GHz:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client(timeout=0.2)
>>> generator = cli.find_or_create_instrument(
...     "generator",
...     "instrumentserver.testing.dummy_instruments.rf.Generator",
... )
>>> try:
...     generator.frequency(100e9)
... except Exception as exc:
...     rejected = exc
>>> type(rejected) is Exception
True
>>> "generator_frequency" in str(rejected)
True
```

The Client currently raises a generic `Exception` containing the original Server-side
message. With the default `raise_exceptions=True`, a failed operation cannot look like a
successful call that returned `None`.

A timeout is different from a Server-side error. This Dummy Instrument has a method that
takes longer than the Client's deadline:

```pycon
>>> import time
>>> slow = cli.find_or_create_instrument(
...     "slow",
...     "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout",
... )
>>> expected_random = slow.get_random()
>>> try:
...     slow.get_random_timeout(wait_time=0.5)
... except RuntimeError as exc:
...     print(exc)
Server did not reply before timeout.
>>> time.sleep(0.4)
>>> slow.get_random() == expected_random
True
```

The Client does not retry a timed-out request. It replaces its ZMQ socket so later
requests can work, but it does not reconnect or rerun the failed operation.

:::{warning}
A timeout means that no reply arrived before the deadline. It does not mean the Server
cancelled the operation. The Server worker continues and may still change the hardware.
For a non-idempotent operation, the instrument state is the only reliable indication of
whether the original call completed.
:::

After `disconnect()`, the Client cannot be reused. Another session requires a new Client:

```pycon
>>> cli.disconnect()
```

:::{note}
`Client(raise_exceptions=False)` logs failures and usually returns `None`. This behavior
fits long-running UI infrastructure with its own error reporting. In measurement code,
`None` is ambiguous because it can also be a valid method result. The default
`raise_exceptions=True` keeps those cases distinct.
:::
