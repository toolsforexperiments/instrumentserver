# Advanced Client Patterns

## ClientStation - Multi-Experiment Isolation

For complex experiments with multiple independent measurement sequences, use `ClientStation` to create isolated instrument collections:

```python
from instrumentserver.client.proxy import ClientStation

# Create isolated stations for different experiments
exp1 = ClientStation(name='experiment_1')
exp2 = ClientStation(name='experiment_2')

# Each station has its own proxy objects
dmm1 = exp1.find_or_create_instrument('dmm', 'custom.DMM')
dmm2 = exp2.find_or_create_instrument('dmm', 'custom.DMM')

# Changes to one don't affect the other
dmm1.range.set(10)
dmm2.range.set(100)

# Automatic cleanup
del exp1  # Cleans up associated proxies
```

## QtClient - Qt Integration

For Qt applications, use `QtClient` for signal/slot integration:

```python
from PyQt5.QtCore import Qt
from instrumentserver.client.proxy import QtClient

class MeasurementWidget(QWidget):
    def __init__(self):
        super().__init__()

        # Qt-integrated client with signal support
        self.client = QtClient()
        self.dmm = self.client.get_instrument('dmm')

        # Connect parameter changes to slots
        self.dmm.voltage.on_change.connect(self.on_voltage_change)

    def on_voltage_change(self, value):
        # Called via Qt signal when voltage changes
        self.voltage_label.setText(f"Voltage: {value}")
```

## State Management

### Instrument State Capture

```python
class InstrumentState:
    def __init__(self, client, instrument_name):
        self.client = client
        self.instrument_name = instrument_name
        self.state = {}

    def capture(self):
        """Capture current state of all parameters"""
        instr = self.client.get_instrument(self.instrument_name)
        blueprint = self.client.get_blueprint(self.instrument_name)

        self.state = {
            param.name: getattr(instr, param.name).get()
            for param in blueprint.parameters
            if getattr(instr, param.name).is_readable()
        }
        return self.state

    def restore(self):
        """Restore captured state"""
        instr = self.client.get_instrument(self.instrument_name)

        for param_name, value in self.state.items():
            try:
                getattr(instr, param_name).set(value)
            except:
                pass  # Skip read-only parameters
```

### Usage

```python
state_manager = InstrumentState(client, 'dmm')

# Capture initial state
state_manager.capture()

# Do measurement...
# ... change parameters ...

# Restore original state
state_manager.restore()
```

## Error Recovery

### Automatic Reconnection

```python
from instrumentserver.client.proxy import Client
import time

class RobustClient:
    def __init__(self, host='localhost', port=5555):
        self.host = host
        self.port = port
        self.client = None
        self._connect()

    def _connect(self):
        """Connect with retry logic"""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.client = Client(
                    host=self.host,
                    port=self.port,
                    timeout=5
                )
                # Test connection
                self.client.list_instruments()
                print("Connected successfully")
                return
            except Exception as e:
                print(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise

    def get_instrument(self, name):
        """Get instrument with automatic reconnection"""
        try:
            return self.client.get_instrument(name)
        except:
            print("Connection lost, reconnecting...")
            self._connect()
            return self.client.get_instrument(name)

# Usage
robust_client = RobustClient(host='192.168.1.100')
dmm = robust_client.get_instrument('dmm')
```

## Batch Operations

### Efficient Parameter Queries

```python
def get_all_parameters(client, instrument_name):
    """Get all parameter values efficiently"""
    instr = client.get_instrument(instrument_name)
    blueprint = client.get_blueprint(instrument_name)

    values = {}
    for param in blueprint.parameters:
        if param.readable:
            try:
                values[param.name] = getattr(instr, param.name).get()
            except:
                values[param.name] = None

    return values

# Usage
all_params = get_all_parameters(client, 'dmm')
for name, value in all_params.items():
    print(f"{name}: {value}")
```

### Conditional Parameter Setting

```python
def set_parameters_if_valid(client, instrument_name, params):
    """Set parameters only if they pass validation"""
    instr = client.get_instrument(instrument_name)

    for param_name, value in params.items():
        try:
            param = getattr(instr, param_name)

            # Validate before setting
            if param.is_settable():
                # Check constraints
                if hasattr(param.vals, 'min_value'):
                    if value < param.vals.min_value:
                        print(f"Skipping {param_name}: below minimum")
                        continue

                param.set(value)
                print(f"Set {param_name} = {value}")
            else:
                print(f"Cannot set read-only parameter: {param_name}")
        except Exception as e:
            print(f"Error setting {param_name}: {e}")

# Usage
set_parameters_if_valid(client, 'source', {
    'voltage': 5.0,
    'current_limit': 0.1,
    'enabled': True
})
```

## Real-Time Data Acquisition

### Periodic Polling

```python
import threading
import time

class ParameterPoller:
    def __init__(self, client, instrument, parameter, interval=1.0):
        self.client = client
        self.instrument_name = instrument
        self.parameter_name = parameter
        self.interval = interval
        self.running = False
        self.thread = None
        self.on_data = None  # Callback for new data

    def start(self):
        """Start polling in background"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop polling"""
        self.running = False
        if self.thread:
            self.thread.join()

    def _poll_loop(self):
        """Polling loop"""
        instr = self.client.get_instrument(self.instrument_name)
        param = getattr(instr, self.parameter_name)

        while self.running:
            try:
                value = param.get()
                timestamp = time.time()

                if self.on_data:
                    self.on_data(timestamp, value)
            except Exception as e:
                print(f"Poll error: {e}")

            time.sleep(self.interval)

# Usage
def save_measurement(timestamp, value):
    print(f"{timestamp}: {value}")

poller = ParameterPoller(client, 'dmm', 'voltage', interval=0.5)
poller.on_data = save_measurement
poller.start()

# ... do other work ...

poller.stop()
```

## Distributed Measurement Control

### Coordinating Multiple Instruments

```python
class MeasurementSequence:
    def __init__(self, client):
        self.client = client
        self.source = client.get_instrument('source')
        self.dmm = client.get_instrument('dmm')
        self.lockin = client.get_instrument('lockin')

    def measure_iv_curve(self, voltages):
        """Measure I-V curve"""
        results = []

        for voltage in voltages:
            # Set source voltage
            self.source.voltage.set(voltage)
            time.sleep(0.1)  # Settle time

            # Read voltage and current
            measured_v = self.dmm.voltage.get()
            measured_i = self.dmm.current.get()

            results.append({
                'source_v': voltage,
                'measured_v': measured_v,
                'measured_i': measured_i
            })

        return results

# Usage
meas = MeasurementSequence(client)
data = meas.measure_iv_curve([0, 1, 2, 3, 4, 5])
```

## Next Steps

- Review [Basic Usage](basic_usage.md)
- Explore [Parameters and Methods](parameters_and_methods.md)
- Read the [Architecture Overview](../architecture/index.md)