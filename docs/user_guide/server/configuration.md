# Server Configuration

## Configuration File

InstrumentServer uses a YAML configuration file to define instruments and server settings. The default location is `serverConfig.yml` in the working directory.

## Basic Structure

```yaml
# Server settings
port: 5555
gui: true

# Instruments to load
instruments:
  - name: dmm
    module: qcodes_instruments.keysight.Keysight34410A
    enabled: true
    settings: {}

  - name: source
    module: qcodes_instruments.keysight.N5242A
    enabled: true
    settings:
      address: "GPIB0::16::INSTR"
```

## Instrument Configuration

### Required Fields

- **name**: Unique identifier for the instrument in the server
- **module**: Python module path to the QCoDeS Instrument class

### Optional Fields

- **enabled**: Whether to load this instrument at startup (default: `true`)
- **settings**: Dictionary of arguments passed to instrument constructor

## Creating Instruments at Runtime

You don't need to define all instruments in the config file. Create them dynamically:

```python
client = Client()

# Create a new instrument on the fly
instrument = client.find_or_create_instrument(
    name='my_inst',
    module_name='my.module.MyInstrument',
    settings={'param1': 'value1'}
)
```

## Parameter Manager

InstrumentServer includes a dynamic parameter management instrument. Access it via:

```bash
instrumentserver-param-manager
```

This allows adding, removing, and modifying parameters at runtime without restarting the server.

## Loading Custom Instruments

For custom instruments, ensure the module is importable. Add to your Python path:

```bash
export PYTHONPATH=/path/to/custom/instruments:$PYTHONPATH
instrumentserver
```

Or configure in Python:

```python
import sys
sys.path.insert(0, '/path/to/custom/instruments')
from instrumentserver.server.core import startServer
startServer()
```

## Performance Tuning

### Thread Pool Size

Configure the number of concurrent request handlers:

```python
from instrumentserver.server.core import StationServer

server = StationServer()
server.threadPoolSize = 10  # Default is 5
```

### Request Timeout

Set timeout for client requests:

```python
from instrumentserver.client.proxy import Client

client = Client(timeout=10)  # 10 second timeout
```

## Next Steps

- Learn about [Server Monitoring](monitoring.md)
- Explore [GUI Components](gui_components.md)
- Read the [Client Guide](../client/index.md)