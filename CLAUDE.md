# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**instrumentserver** is a client-server framework for managing QCoDeS instruments in a networked environment. It enables remote control of lab instruments through proxy objects, allowing multiple clients to interact with instruments running on a central server. The server manages a QCoDeS Station and exposes instruments/parameters via ZMQ messaging.

## Installation

```bash
# Developer install (no dependencies)
pip install --no-deps -e /path/to/instrumentserver/

# With dependencies
pip install -e /path/to/instrumentserver/
```

## Console Scripts

The package installs four console scripts:

```bash
# Start server with GUI (default)
instrumentserver -p 5555

# Start server without GUI
instrumentserver -p 5555 --gui False

# Start with config file
instrumentserver -c /path/to/config.yaml

# Start detached server
instrumentserver-detached

# Start parameter manager GUI
instrumentserver-param-manager --name parameter_manager --port 5555

# Start monitoring listener
instrumentserver-listener
```

### Server Arguments
- `-p/--port` - Port number (default: 5555)
- `--gui` - Enable/disable GUI (default: True)
- `--allow_user_shutdown` - Allow users to shutdown server
- `-a/--listen_at` - Network addresses to listen on
- `-i/--init_script` - Initialization script path
- `-c/--config` - YAML config file path

## Testing

```bash
# Run all tests
pytest

# Run specific test
pytest test/pytest/test_basic_functionality.py
pytest test/pytest/test_serialize.py

# Run with verbose output
pytest -v
```

Tests are in `test/pytest/` with fixtures defined in `test/pytest/conftest.py`.

## Core Architecture

### Client-Server Communication

The architecture uses **ZMQ (ZeroMQ)** with a REQ-REP pattern for client-server communication plus PUB-SUB for broadcasting parameter updates.

**Server Side:**
- **StationServer** ([instrumentserver/server/core.py](instrumentserver/server/core.py)) - Main server managing a QCoDeS Station
  - Listens on port N (e.g., 5555) for requests via ZMQ ROUTER socket
  - Broadcasts on port N+1 (e.g., 5556) via ZMQ PUB socket for parameter updates
  - Runs in a QThread with Qt signals for GUI integration
  - Handles concurrent requests via ThreadPoolExecutor

**Client Side:**
- **BaseClient** ([instrumentserver/client/core.py](instrumentserver/client/core.py)) - Low-level ZMQ client
  - Uses DEALER socket for async request/reply
  - Handles timeouts and reconnection
  - Configurable exception raising
- **Client** ([instrumentserver/client/proxy.py](instrumentserver/client/proxy.py)) - High-level client that creates proxy objects

### Blueprint System

The **blueprints** module ([instrumentserver/blueprints.py](instrumentserver/blueprints.py)) defines all objects exchanged between client and server. This is the communication contract.

**Key Blueprint Types:**
- `ParameterBluePrint` - Describes a parameter (name, path, gettable/settable, unit)
- `InstrumentModuleBluePrint` - Describes an instrument/channel (parameters, methods, submodules)
- `MethodBluePrint` - Describes a callable method
- `ParameterBroadcastBluePrint` - Parameter update broadcasts

**Message Types:**
- `ServerInstruction` - Client requests (operations: get_blueprint, call, get, set, create_instrument, etc.)
- `ServerResponse` - Server responses (message, error)
- `CallSpec` - Function call specification (target, args, kwargs)
- `InstrumentCreationSpec` - Instrument instantiation spec

**Serialization:**
All blueprints implement `toJson()` for serialization. The module handles nested objects, numpy arrays, and custom classes via introspection. Use `deserialize_obj()` to reconstruct objects from JSON.

### Proxy Objects

Clients interact with instruments through **proxy objects** that mirror the server-side structure:

- **ProxyInstrument** - Mirrors QCoDeS Instrument
- **ProxyParameter** - Mirrors QCoDeS Parameter
  - `get()` sends ServerInstruction with Operation.get
  - `set(value)` sends ServerInstruction with Operation.set
- **ProxyMethod** - Mirrors instrument methods

All inherit from **ProxyMixin** which provides:
- `askServer()` - Send requests via client or direct sendRequest
- Blueprint-based initialization
- Remote path tracking

Pattern:
```python
cli = Client(host='localhost', port=5555)
instrument = cli.find_or_create_instrument('my_instrument')
param = instrument.some_parameter
value = param()  # Sends get request to server
param(new_value)  # Sends set request to server
```

### Parameter Manager

**ParameterManager** ([instrumentserver/params.py](instrumentserver/params.py)) is a virtual QCoDeS instrument for managing arbitrary parameters without physical instruments:

- Stores parameters in JSON "profiles" (e.g., `parameter_manager-qubit1.json`)
- Allows dynamic parameter addition/removal
- Supports nested parameter groups
- Used for experiment configuration and calibration values

### Serialization System

**serialize.py** ([instrumentserver/serialize.py](instrumentserver/serialize.py)) provides JSON serialization for instrument states:

**Key Functions:**
- `toParamDict(station/instrument)` - Extract parameter values to dict
- `fromParamDict(paramDict, station/instrument)` - Load parameter values from dict

**Format:**
```python
{
    "instrument.parameter": {
        "value": 123,
        "unit": "mV"
    }
}
# or simplified:
{
    "instrument.parameter": 123
}
```

Parameter addressing matches QCoDeS station paths: `station.instrument.submodule.parameter`.

## Module Organization

- **instrumentserver/server/** - Server implementation
  - `core.py` - StationServer, request handling
  - `application.py` - GUI application wrapper
  - `pollingWorker.py` - Background parameter polling
- **instrumentserver/client/** - Client implementation
  - `core.py` - BaseClient, low-level communication
  - `proxy.py` - Client class, proxy objects
- **instrumentserver/gui/** - Qt GUI components
  - `instruments.py` - Instrument control widgets
  - `parameters.py` - Parameter editing widgets
- **instrumentserver/** - Core utilities
  - `blueprints.py` - Communication protocol definitions
  - `params.py` - ParameterManager
  - `serialize.py` - Instrument state serialization
  - `helpers.py` - Utility functions (nestedAttributeFromString, etc.)
  - `base.py` - ZMQ send/recv helpers
  - `config.py` - YAML config loading
  - `apps.py` - Console script entry points
- **instrumentserver/monitoring/** - Monitoring tools
  - `listener.py` - Broadcast listener for monitoring
- **instrumentserver/testing/** - Test utilities and dummy instruments
- **instrumentserver/deployment/** - Grafana dashboard for instrument monitoring (Docker setup)

## Key Patterns

### Nested Attribute Access
Use `nestedAttributeFromString(obj, "sub.module.param")` to access nested attributes from dot-notation strings.

### Operations Enum
All server operations are defined in `Operation` enum (blueprints.py): `get_blueprint`, `call`, `get`, `set`, `create_instrument`, `list_instruments`, etc.

### Thread Safety
Server uses Qt threading model - StationServer runs in separate QThread, parameter access happens via thread pool to avoid blocking the message loop.

### Broadcasting
Parameter sets trigger broadcasts on port+1, clients can subscribe to monitor parameter changes in real-time without polling.
