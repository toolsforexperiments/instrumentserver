# API Reference

Complete API documentation for InstrumentServer, automatically generated from source code docstrings.

## Main Modules

```{eval-rst}
.. autosummary::
   :toctree: generated
   :recursive:

   instrumentserver.server
   instrumentserver.client
   instrumentserver.blueprints
   instrumentserver.monitoring
```

## Quick Navigation

### Server API
- `instrumentserver.server.core.StationServer` - Main server class
- `instrumentserver.server.application` - Server GUI components

### Client API
- `instrumentserver.client.proxy.Client` - High-level client API
- `instrumentserver.client.proxy.ProxyParameter` - Remote parameter interface
- `instrumentserver.client.proxy.ProxyInstrumentModule` - Remote instrument interface
- `instrumentserver.client.core.BaseClient` - Low-level ZMQ client

### Messaging
- `instrumentserver.blueprints.ServerInstruction` - Client requests
- `instrumentserver.blueprints.ServerResponse` - Server responses
- `instrumentserver.blueprints.ParameterBluePrint` - Parameter metadata
- `instrumentserver.blueprints.InstrumentModuleBluePrint` - Instrument metadata

### Monitoring
- `instrumentserver.monitoring.monitor.ParameterListener` - Real-time parameter updates
- `instrumentserver.monitoring.monitor.ParameterLogger` - Parameter logging