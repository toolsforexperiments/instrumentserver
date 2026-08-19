# Python Client

The Client is the Python interface you use to work with instruments owned by a Server.
It gives you Proxy Instruments with the same parameters and methods as their real QCoDeS
drivers. If you haven't used instrumentserver before, start with the
[Quickstart](../getting_started/quickstart.md). For the concepts behind the connection,
see [How it works](../getting_started/how_it_works.md).

Each section below is a standalone example. Keep the Server running while you try them.

## Connect and get an instrument

Start the Server in a terminal:

```{prompt} bash
instrumentserver -p 5555 -a 127.0.0.1
```

The Server GUI opens so you can watch instruments appear as you create them. Leave it
running, then open Python in a second terminal or notebook.

:::{note}
Port `5555` and address `127.0.0.1` are the defaults, so plain `instrumentserver` starts
the same local Server. The `-p` option selects the request port. The `-a` option adds a
listening address, and the Server always includes the loopback address. See
[The Server](server.md) for addresses, ports, and remote connections.
:::

Create a long-lived Client for your measurement session and check which instruments the
Server already owns:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client(host="localhost", port=5555)
>>> cli.list_instruments()
[]
```

Now create the dummy RF generator used throughout this page:

```pycon
>>> generator = cli.find_or_create_instrument(
...     "generator",
...     "instrumentserver.testing.dummy_instruments.rf.Generator",
... )
>>> cli.list_instruments()
['generator']
```

`find_or_create_instrument` returns a Proxy Instrument ready to use. When the Server
doesn't have the requested name, it imports the class and creates the real instrument.
When the name already exists, it returns a Proxy for that instrument instead. The method
mirrors QCoDeS'
[`find_or_create_instrument`](https://microsoft.github.io/Qcodes/api/instrument/index.html#qcodes.instrument.find_or_create_instrument),
but instrumentserver's lookup is name-based: an existing name is returned without
checking the class path supplied for creation.

The generator appears in the Server GUI as soon as it is created:

```{image} ../_static/getting_started/quickstart/server_generator_light.png
:class: only-light
:alt: The Server GUI showing the newly created generator
```

```{image} ../_static/getting_started/quickstart/server_generator_dark.png
:class: only-dark
:alt: The Server GUI showing the newly created generator
```

:::{note}
If you know an instrument already exists and don't want to provide a creation class, use
`cli.get_instrument("generator")`. It returns a Proxy for the existing instrument and
does not create one.
:::

Keep one Client connected for the lifetime of your measurement. Disconnect it when the
measurement is finished:

```pycon
>>> cli.disconnect()
```

For a small script, a context manager can handle that cleanup for you:

```pycon
>>> with Client(host="localhost", port=5555) as cli:
...     generator = cli.get_instrument("generator")
...     print(generator.frequency())
10000000000.0
```

:::{note}
Constructing `Client` opens its ZMQ connection but does not perform a handshake with the
Server. The first request, such as `list_instruments()`, is what confirms that the Server
can reply. See [Handle errors and timeouts](#handle-errors-and-timeouts) for what happens
when it cannot.
:::

## Use a Proxy Instrument

Connect and retrieve the generator created above:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client()
>>> generator = cli.find_or_create_instrument(
...     "generator",
...     "instrumentserver.testing.dummy_instruments.rf.Generator",
... )
```

A Proxy parameter is a real QCoDeS
[`Parameter`](https://microsoft.github.io/Qcodes/api/parameters/#qcodes.parameters.Parameter)
whose get and set commands call the Server. Use the normal QCoDeS callable form to read
and write it:

```pycon
>>> generator.frequency()
10000000000.0
>>> generator.frequency(5e9)
>>> generator.frequency()
5000000000.0
```

The explicit QCoDeS methods are equivalent:

```pycon
>>> generator.frequency.set(6e9)
>>> generator.frequency.get()
6000000000.0
```

Driver methods are proxied too. This dummy resonator has a method that changes its
simulated resonance frequency:

```pycon
>>> resonator = cli.find_or_create_instrument(
...     "resonator",
...     "instrumentserver.testing.dummy_instruments.rf.ResonatorResponse",
... )
>>> resonator.modulate_frequency(delta=1e6)
```

The method runs on the real `resonator` inside the Server, just like a method on a
physical instrument driver would. When you're done with this session:

```pycon
>>> cli.disconnect()
```

## Save and restore parameter values

The Client can collect parameter values, apply a group of values, and save or restore
experiment state. These methods work with any existing Server-owned instrument.

Start from known generator values so the output is reproducible:

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

Save the generator's current values to a JSON file:

```pycon
>>> cli.paramsToFile(
...     "generator-parameters.json",
...     instruments=["generator"],
...     get=True,
... )
```

The file uses a nested shape that is easier to read and edit:

```json
{
  "generator": {
    "frequency": 6000000000.0,
    "power": -30,
    "rf_on": true
  }
}
```

Change the values, then restore the saved state:

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
working directory, not the Server's. Omit `instruments` to save every Server instrument,
or to restore every matching entry in the file.

:::{warning}
Boolean values are not currently restored by `setParameters` or `paramsFromFile`.
During deserialization, `True` and `False` become `1.0` and `0.0`, which fail QCoDeS
Boolean validation. Numeric values in the same operation still restore correctly. This
is tracked in [issue #152](https://github.com/toolsforexperiments/instrumentserver/issues/152).
:::

:::{note}
Do not load the nested JSON yourself and pass it directly to `setParameters`. That method
expects flat dotted keys and currently ignores the nested shape after logging a
Server-side error. Use `paramsFromFile`, which flattens the saved JSON before sending it.
:::

:::{note}
The Parameter Manager has a separate profile workflow. Its `toFile` and `fromFile`
methods run on the Server, preserve units, and can create or remove hierarchical
parameters. See [Parameter Manager](parameter_manager.md) when you need managed profiles
rather than a snapshot of existing instruments.
:::

```pycon
>>> cli.disconnect()
```

## Handle errors and timeouts

The Client raises Server-side errors by default. For example, the dummy generator only
accepts frequencies up to 20 GHz:

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
message. Keep the default `raise_exceptions=True` so failed operations cannot silently
look successful.

Timeouts are different from Server-side errors. This example uses a Dummy Instrument
whose method deliberately takes longer than the Client's deadline:

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

A timed-out request is not retried. The Client replaces its ZMQ socket so later requests
can work, but this is not automatic reconnection of the failed operation.

:::{warning}
A timeout means that no reply arrived before the deadline. It does not mean the Server
cancelled the operation. The Server worker continues and may still change the hardware.
Before retrying a non-idempotent operation, read the instrument state and decide whether
the original call completed.
:::

Calling `disconnect()` permanently closes that Client instance. Create a new Client if
you need another session:

```pycon
>>> cli.disconnect()
```

:::{note}
`Client(raise_exceptions=False)` logs failures and usually returns `None`. That can be
useful in long-running UI infrastructure with its own error reporting, but `None` is
ambiguous for measurement code because it can also be a valid method result. Normal
measurement code should keep the default and handle exceptions explicitly.
:::
