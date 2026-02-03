# Basic Server Setup

## Starting the Server

### With GUI

To start the InstrumentServer with a graphical interface:

```bash
instrumentserver --gui True
```

This launches the server with a real-time display of:
- Available instruments and their parameters
- Message log showing client requests
- Parameter values and status updates

### Without GUI (Headless)

For deployments without a display or for background operation:

```bash
instrumentserver --gui False
```

### Custom Port

By default, InstrumentServer runs on port 5555. To use a different port:

```bash
instrumentserver --port 5566 --gui False
```

## Configuration

InstrumentServer loads instruments from a YAML configuration file. See [Server Configuration](../user_guide/server/configuration.md) for detailed setup options.

A basic configuration file (`serverConfig.yml`) might look like:

```yaml
instruments:
  - module: qcodes_instruments.keysight.Keysight34410A
    name: dmm
    enabled: true

  - module: custom.instruments.MyCustomInstrument
    name: my_inst
    enabled: true
```

## Monitoring the Server

The server GUI provides real-time monitoring. For headless servers, use the listener utility:

```bash
instrumentserver-listener
```

This displays real-time parameter updates from the server.

## Stopping the Server

- **With GUI**: Close the window or press Ctrl+C
- **Background process**: Use `kill` or send SIGTERM

## Next Steps

Now that your server is running, learn how to [connect your first client](first_client.md).
