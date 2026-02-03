# Parameters and Methods

## ProxyParameter Objects

All remote parameters are accessed through `ProxyParameter` objects, which provide the same interface as QCoDeS parameters.

### Getting Parameters

```python
dmm = client.get_instrument('dmm')

# Access a parameter
voltage_param = dmm.voltage

# All parameter access goes through the proxy
print(type(voltage_param))
# <class 'instrumentserver.client.proxy.ProxyParameter'>
```

### Parameter Information

Parameter metadata is cached locally after first access:

```python
voltage_param = dmm.voltage

# Get metadata (cached locally)
print(f"Name: {voltage_param.name}")
print(f"Label: {voltage_param.label}")
print(f"Unit: {voltage_param.unit}")
print(f"Datatype: {voltage_param.datatype}")

# Get value constraints
print(f"Min: {voltage_param.vals.min_value}")
print(f"Max: {voltage_param.vals.max_value}")
print(f"Allowed values: {voltage_param.vals.allowed_values}")
```

### Reading and Writing

```python
# Read parameter value (network call)
voltage = voltage_param.get()

# Write parameter value (network call)
voltage_param.set(5.0)

# Check if readable/writable
if voltage_param.is_readable():
    value = voltage_param.get()

if voltage_param.is_settable():
    voltage_param.set(10)
```

## Parameter Types

### Numeric Parameters

```python
# Float parameter
voltage = dmm.voltage.get()

# Integer parameter
count = source.pulse_count.get()

# Parameters with units
power = source.power.get()  # watts
frequency = source.frequency.get()  # Hz
```

### Enumeration Parameters

```python
# Select from allowed values
mode = source.mode
available = mode.vals.allowed_values  # ['AC', 'DC', 'Pulsed']

mode.set('AC')
current_mode = mode.get()  # 'AC'
```

### Boolean Parameters

```python
# Enable/disable
source.enabled.set(True)
is_enabled = source.enabled.get()  # True or False
```

### String Parameters

```python
# Free-form text parameters
serial = dmm.serial_number.get()  # read-only
name = source.label.set('my_source')  # if writable
```

## Method Calls

### Simple Methods

```python
dmm = client.get_instrument('dmm')

# Method with no arguments
result = dmm.reset()

# Method with return value
status = dmm.get_status()
print(f"Status: {status}")
```

### Methods with Arguments

```python
# Positional arguments
dmm.configure('voltage', 10)

# Keyword arguments
dmm.configure(mode='voltage', range=10)

# Mixed arguments
dmm.measure(measurement_type='voltage',
            range=100,
            resolution=0.001)
```

### Method Return Values

```python
# Method with return value
data = source.get_output_data()
print(f"Returned: {data}")

# Multiple return values (as tuple or dict)
freq, phase = lockin.get_reference()
```

## Validators and Constraints

### Understanding Validators

```python
voltage = dmm.voltage

# Check constraints
validator = voltage.vals

# Numeric validator
print(f"Min: {validator.min_value}")
print(f"Max: {validator.max_value}")

# Enumeration validator
enum_val = source.mode.vals
print(f"Allowed: {enum_val.allowed_values}")
```

### Validation on Set

```python
# Validation happens server-side
try:
    dmm.voltage.set(500)  # Exceeds max_value
except ValueError as e:
    print(f"Validation failed: {e}")
```

## Real-Time Updates

### Parameter Monitoring

```python
from instrumentserver.monitoring.monitor import ParameterListener

def on_voltage_change(value):
    print(f"Voltage changed to: {value}")

# Create listener for a specific parameter
listener = ParameterListener(
    host='localhost',
    port=5555,
    instrument='dmm',
    parameter='voltage'
)

listener.on_change = on_voltage_change
listener.start()

# Updates received asynchronously
```

### Batch Parameter Updates

```python
from instrumentserver.monitoring.monitor import InstrumentListener

def on_update(instrument_name, updates):
    for param_name, value in updates.items():
        print(f"{instrument_name}.{param_name} = {value}")

listener = InstrumentListener(
    host='localhost',
    port=5555,
    instrument='dmm'
)

listener.on_update = on_update
listener.start()
```

## Parameter Snapshot

### Snapshot and Restore

```python
dmm = client.get_instrument('dmm')

# Take a snapshot of current parameters
snapshot = {
    'voltage': dmm.voltage.get(),
    'range': dmm.range.get(),
    'resolution': dmm.resolution.get()
}

# Do something...

# Restore parameters
for name, value in snapshot.items():
    getattr(dmm, name).set(value)
```

## Asynchronous Operations

### Non-Blocking Calls

Due to the network nature, all calls are inherently non-blocking:

```python
# Call returns immediately (waits for response internally)
value = dmm.voltage.get()  # Blocks until response received

# For truly async, use threading
import threading

def read_voltage():
    voltage = dmm.voltage.get()
    print(f"Voltage: {voltage}")

thread = threading.Thread(target=read_voltage)
thread.start()
```

## Next Steps

- Learn about [Advanced Patterns](advanced_patterns.md)
- Explore [Basic Usage](basic_usage.md)
- Read the [API Reference](../../api/index.md)