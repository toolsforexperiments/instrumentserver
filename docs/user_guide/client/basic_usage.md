# Basic Client Usage

## Connecting to the Server

### Default Connection

Connect to a server running on the local machine at the default port:

```python
from instrumentserver.client.proxy import Client

client = Client()  # Connects to localhost:5555
```

### Custom Host and Port

```python
# Connect to a remote server
client = Client(host='192.168.1.100', port=5566)

# With timeout
client = Client(host='192.168.1.100', timeout=10)
```

### Connection Settings

```python
client = Client(
    host='192.168.1.100',
    port=5555,
    timeout=5.0,  # seconds
    max_retries=3,
    retry_delay=1.0  # seconds
)
```

## Listing Instruments

### Get All Instruments

```python
instruments = client.list_instruments()
print(instruments)
# Output: ['dmm', 'source', 'lock_in']
```

### Get Instrument Metadata

```python
# Get full blueprint/metadata
blueprint = client.get_blueprint('dmm')
print(blueprint.parameters)  # List of available parameters
print(blueprint.methods)     # Available methods
```

## Accessing Instruments

### Get Existing Instrument

```python
dmm = client.get_instrument('dmm')
```

### Find or Create Instrument

If the instrument doesn't exist on the server yet:

```python
source = client.find_or_create_instrument(
    name='source',
    module_name='qcodes_instruments.keysight.N5242A',
    settings={
        'address': 'GPIB0::16::INSTR'
    }
)
```

## Working with Parameters

### Reading Parameter Values

```python
dmm = client.get_instrument('dmm')

# Get parameter value
voltage = dmm.voltage.get()
print(f"Voltage: {voltage}")

# All parameters are ProxyParameter objects
param = dmm.voltage
print(f"Units: {param.unit}")
print(f"Min: {param.vals.min_value}")
print(f"Max: {param.vals.max_value}")
```

### Setting Parameter Values

```python
dmm = client.get_instrument('dmm')

# Set parameter value
dmm.range.set(10)

# Set with validation
try:
    dmm.voltage.set(150)
except ValueError as e:
    print(f"Invalid value: {e}")
```

### Parameter Information

```python
param = dmm.voltage

# Metadata available locally (from blueprint)
print(f"Label: {param.label}")
print(f"Unit: {param.unit}")
print(f"Datatype: {param.datatype}")
print(f"Readable: {param.is_readable()}")
print(f"Settable: {param.is_settable()}")
```

## Calling Methods

### Simple Method Call

```python
dmm = client.get_instrument('dmm')

# Call method with no arguments
result = dmm.reset()

# Call method with arguments
dmm.configure(measurement_type='voltage', range=10)
```

### Method Information

```python
blueprint = client.get_blueprint('dmm')

# Get method signatures
for method in blueprint.methods:
    print(f"{method.name}({method.args})")
```

## Error Handling

### Timeout Errors

```python
from instrumentserver.client.core import TimeoutError as ClientTimeoutError

try:
    value = client.get_instrument('dmm').voltage.get()
except ClientTimeoutError:
    print("Server not responding - timeout")
except Exception as e:
    print(f"Error: {e}")
```

### Connection Errors

```python
try:
    client = Client(host='192.168.1.100', timeout=5)
    instruments = client.list_instruments()
except ConnectionError:
    print("Cannot connect to server")
```

### Instrument Errors

```python
try:
    dmm = client.get_instrument('nonexistent')
except KeyError:
    print("Instrument not found on server")
```

## Batch Operations

### Get Multiple Parameters

```python
dmm = client.get_instrument('dmm')

# Get multiple parameters efficiently
params = {
    'voltage': dmm.voltage.get(),
    'current': dmm.current.get(),
    'range': dmm.range.get()
}
```

### Set Multiple Parameters

```python
source = client.get_instrument('source')

# Set parameters in sequence
source.voltage.set(5.0)
source.current_limit.set(0.1)
source.enabled.set(True)
```

## Instrument Structure

### Accessing Submodules

```python
# If an instrument has submodules/channels
lockin = client.get_instrument('lockin')

# Access submodule
channel = lockin.channel_1

# Access parameters in submodule
value = lockin.channel_1.frequency.get()
```

### Exploring Structure

```python
blueprint = client.get_blueprint('lockin')

# Explore submodules
for submodule in blueprint.submodules:
    print(f"Submodule: {submodule.name}")
    for param in submodule.parameters:
        print(f"  - {param.name}: {param.unit}")
```

## Next Steps

- Learn about [Parameters and Methods](parameters_and_methods.md)
- Explore [Advanced Patterns](advanced_patterns.md)
- Read the [Architecture Overview](../architecture/index.md)