# Server Monitoring

## Real-Time Server GUI

The server GUI provides real-time monitoring of all activity:

```bash
instrumentserver --gui True
```

### GUI Panels

**Station List**
- Displays all instruments currently loaded
- Shows all parameters for each instrument
- Live parameter values updated in real-time
- Parameter details (units, limits, validators)

**Server Status**
- Message log showing all client requests
- Response times and operation results
- Error messages and warnings

**Station Object Info**
- Detailed metadata about selected instruments
- Parameter specifications and constraints
- Method signatures and documentation

## Command-Line Listener

For headless servers without a display, use the real-time listener:

```bash
instrumentserver-listener
```

This connects to a running server and displays:
- Real-time parameter updates
- Instrument changes
- Connection status

## Monitoring Configuration

Configure the listener with a YAML file (`listenerConfig.yml`):

```yaml
server:
  host: localhost
  port: 5555

monitoring:
  update_interval: 1.0  # seconds
  log_level: INFO
```

## Parameter Logging

InstrumentServer integrates with monitoring systems:

### CSV Logging

Parameters can be logged to CSV files for analysis:

```python
from instrumentserver.monitoring.monitor import ParameterLogger

logger = ParameterLogger(
    filename='measurements.csv',
    instruments=['dmm', 'source']
)

# Logs parameter updates to CSV
logger.start()
```

### Grafana Dashboard

See the deployment documentation for Grafana integration and dashboards.

## Client-Side Monitoring

Clients can subscribe to real-time updates:

```python
from instrumentserver.monitoring.monitor import ParameterListener

def on_update(value):
    print(f"Value: {value}")

listener = ParameterListener(
    instrument='dmm',
    parameter='voltage'
)
listener.on_change = on_update
listener.start()
```

## Logs and Debugging

### Log Files

- **instrumentserver.log** - Server activity and errors
- **instrumentclient.log** - Client activity and errors

### Increase Verbosity

```bash
instrumentserver --debug True
```

## Health Checks

Monitor server health programmatically:

```python
client = Client()

# List all instruments (simple health check)
instruments = client.list_instruments()
print(f"Server healthy: {len(instruments) >= 0}")
```

## Next Steps

- Learn about [GUI Components](gui_components.md)
- Read the [Client Guide](../client/index.md)
- Explore [Architecture](../architecture/index.md)