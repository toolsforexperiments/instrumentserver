# Your First Client

## Connecting to the Server

Once your InstrumentServer is running, you can connect a client in just a few lines of Python:

```python
from instrumentserver.client.proxy import Client

# Connect to the server
client = Client()  # Default: localhost:5555

# List available instruments
instruments = client.list_instruments()
print("Available instruments:", instruments)
```

## Getting Instrument Data

Access instruments and read parameters:

```python
# Get an instrument proxy
dmm = client.get_instrument('dmm')

# Read a parameter value
voltage = dmm.voltage.get()
print(f"Measured voltage: {voltage}")
```

## Setting Parameters

Control instruments by setting parameters:

```python
dmm = client.get_instrument('dmm')

# Set a parameter
dmm.range.set(10)  # Set to 10V range

# Some parameters are read-only
# (will raise an error if you try to set them)
```

## Calling Methods

Execute instrument methods:

```python
# Call a method on the instrument
result = dmm.reset()

# Methods with arguments
dmm.configure_measurement('voltage')
```

## Real-Time Parameter Updates

InstrumentServer broadcasts parameter changes in real-time. Subscribe to updates:

```python
from instrumentserver.client.proxy import Client
from instrumentserver.monitoring.monitor import ParameterListener

# Create a callback
def on_voltage_change(value):
    print(f"Voltage updated to: {value}")

# Listen for changes
listener = ParameterListener(instrument='dmm', parameter='voltage')
listener.on_change = on_voltage_change
listener.start()

# ... updates will trigger the callback
```

## Multiple Instruments

Working with multiple instruments is straightforward:

```python
client = Client()

dmm = client.get_instrument('dmm')
source = client.get_instrument('source')

# Control both instruments
voltage_reading = dmm.voltage.get()
source.voltage.set(voltage_reading + 1)
```

## Error Handling

Handle network and instrument errors gracefully:

```python
from instrumentserver.client.core import TimeoutError as ClientTimeoutError

try:
    client = Client(host='localhost', port=5555, timeout=5)
    value = client.get_instrument('dmm').voltage.get()
except ClientTimeoutError:
    print("Server not responding")
except Exception as e:
    print(f"Error: {e}")
```

## Client Station (Multi-Experiment Isolation)

For complex experiments with multiple independent measurement sequences, use `ClientStation`:

```python
from instrumentserver.client.proxy import ClientStation

# Create isolated instrument collections
experiment1 = ClientStation(name='exp1')
experiment2 = ClientStation(name='exp2')

# Each has independent proxy objects
dmm1 = experiment1.find_or_create_instrument('dmm', 'custom.instruments.DMM')
dmm2 = experiment2.find_or_create_instrument('dmm', 'custom.instruments.DMM')

# Changes to one don't affect the other
dmm1.range.set(10)
dmm2.range.set(100)
```

## Next Steps

- Learn more about [Client API](../user_guide/client/index.md)
- Explore [Server Configuration](../user_guide/server/index.md)
- Review the [Architecture](../user_guide/architecture/index.md)