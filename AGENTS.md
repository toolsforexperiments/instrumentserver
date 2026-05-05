# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Quick Start Commands

### Development Installation
```bash
pip install --no-deps -e /path/to/instrumentserver/
pip install zmq qcodes qtpy pyqt5 bokeh scipy
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest test/pytest/test_basic_functionality.py

# Run specific test function
pytest test/pytest/test_basic_functionality.py::test_function_name

# Run with verbose output
pytest -v
```

### Running the Server
```bash
# Server with GUI
instrumentserver --gui True

# Server without GUI (background)
instrumentserver --gui False

# Server on specific port
instrumentserver --port 5566

# Detached server GUI (connects to running server)
instrumentserver-detached

# Parameter manager utility
instrumentserver-param-manager

# Real-time monitoring listener
instrumentserver-listener
```

### Running the Client
```bash
# See test files for client usage examples
python test/test_async_requests/test_client.py
python test/test_async_requests/client_station_gui.py  # Client GUI
```

## Architecture Overview

### High-Level System Design

InstrumentServer is a distributed instrument control system enabling remote access to QCoDeS instruments via ZMQ. The architecture uses a server-client pattern with concurrent request handling and real-time parameter broadcasting.

```
CLIENT (ZMQ DEALER)        SERVER (ZMQ ROUTER + ThreadPoolExecutor)
    ↓                            ↓
ProxyInstrument            StationServer
ProxyParameter             (QCoDeS Station)
ClientStation              Per-instrument Locks
    ↓                            ↓
Client API                 Instruments
    ↓                            ↓
BaseClient → ZMQ Network → ThreadPool + Broadcast
```

### Core Components

#### Server (`instrumentserver/server/`)

**`core.py` - `StationServer` class**
- Main server object running in a separate QThread
- Manages QCoDeS Station with all laboratory instruments
- Uses ZMQ ROUTER socket to receive requests from multiple concurrent clients
- ThreadPoolExecutor handles requests asynchronously
- Per-instrument locks (`threading.Lock`) prevent race conditions when multiple threads access the same instrument
- ZMQ PUB socket broadcasts parameter changes to all listening clients
- Four primary operations:
  - `get_existing_instruments()` - List available instruments
  - `create_instrument()` - Create new instruments from specification
  - `call()` - Call methods, get/set parameters on instruments
  - `get_blueprint()` - Get metadata about instruments/parameters

**`application.py` - Server GUI components**
- `StationList` - Displays all instruments and their parameters
- `StationObjectInfo` - Shows detailed metadata
- `ServerStatus` - Real-time message and status display
- `DetachedServerGui` - Connects to running server (doesn't host it)

#### Client (`instrumentserver/client/`)

**`core.py` - `BaseClient` class**
- Low-level ZMQ DEALER socket communication
- Request-reply pattern with timeout handling
- Automatic connection recovery with retry logic

**`proxy.py` - High-level client abstractions**
- `ProxyParameter` - Wraps remote QCoDeS parameters with get/set interface
- `ProxyInstrumentModule` - Wraps remote instruments/channels/submodules
- `Client` - Main high-level API
  - `list_instruments()` - Get list of available instruments
  - `find_or_create_instrument()` - Create or get proxy for instrument
  - `call()` - Call remote methods
  - `get_instrument()` - Get existing proxy
- `ClientStation` - Lightweight container for managing proxy instruments per experiment
- `QtClient` - Qt-integrated version with signal/slot support
- Blueprint caching for performance

**`application.py` - Client GUI**
- `ClientStationGui` - Tab-based interface for controlling instruments
- Real-time parameter listener using broadcast socket
- Detachable/dockable tabs for instrument control
- Automatic reconnection on network failure

#### Messaging & Serialization (`instrumentserver/`)

**`blueprints.py` - Protocol definitions**
- `ParameterBluePrint` - Describes remote parameters (value, units, limits, etc.)
- `InstrumentModuleBluePrint` - Describes remote instruments/channels/submodules
- `MethodBluePrint` - Describes remote methods
- `ServerInstruction` - Client requests (JSON-serializable)
  - Operation enum: `GET_EXISTING_INSTRUMENTS`, `CREATE_INSTRUMENT`, `CALL`, `GET_BLUEPRINT`
- `ServerResponse` - Server responses with result or error
- Serialization/deserialization to/from JSON for network transmission

**`base.py` - Low-level ZMQ utilities**
- `send/recv` - Basic ZMQ message encoding/decoding
- `send_router/recv_router` - ROUTER socket handling (multi-client)
- `sendBroadcast/recvMultipart` - Broadcast communication patterns

**`serialize.py` - Parameter persistence**
- Convert instruments to parameter dictionaries
- Load parameters from dictionaries (round-trip save/load)

#### GUI Components (`instrumentserver/gui/`)
- `base_instrument.py` - Generic instrument UI building blocks
- `instruments.py` - Specialized GUIs for specific instrument types
- `parameters.py` - Parameter input/display widgets
- `misc.py` - Dialogs, tabs, and UI utilities

#### Supporting Modules
- `params.py` - `ParameterManager` - Dynamic parameter instrument for runtime parameter management
- `config.py` - Configuration file handling (YAML)
- `log.py` - Logging setup
- `helpers.py` - Utilities (nested attribute access, class path resolution)
- `monitoring/` - Real-time data broadcasting listener
- `deployment/` - Docker and deployment configurations
- `dashboard/` - Grafana monitoring dashboard

### Communication Protocol

1. **Client Request** → `ServerInstruction` serialized to JSON
2. **ZMQ DEALER** sends request to server's ROUTER socket
3. **ROUTER** routes to ThreadPoolExecutor worker
4. **StationServer._callObject()** acquires per-instrument lock and executes
5. **Parameter changes** broadcast via ZMQ PUB socket
6. **ServerResponse** returned with result or error

### Key Design Patterns

**Per-Instrument Locking (ce4190d)**
- Each instrument has a `threading.Lock`
- Lock acquired in `_callObject()` before any operation
- Prevents race conditions in multi-threaded access
- Single-threaded access per instrument enforced

**Async Request Handling (f9753ea)**
- ZMQ ROUTER/DEALER pattern enables true concurrency
- ThreadPoolExecutor distributes work across multiple workers
- Each request runs in separate thread with acquired instrument lock
- Different instruments can be accessed concurrently

**Proxy Pattern**
- Client-side proxies (ProxyParameter, ProxyInstrument) mimic QCoDeS API
- Transparent network communication hidden from user code
- Supports normal Python attribute access: `proxy_instrument.parameter.get()`

**ClientStation Isolation (9171d8c)**
- Experiment-specific proxy collection
- Enables multiple concurrent experiments on same server
- Lightweight container (doesn't host server)

**Broadcast Architecture**
- Server broadcasts on separate PUB socket
- Multiple clients SUB to same socket
- Real-time parameter updates without polling
- Clients listen asynchronously with background thread

## Testing

### Test Setup (test/pytest/conftest.py)
- `start_server` fixture - Module-scoped server for all tests
- `cli` fixture - New Client per test
- `dummy_instrument` fixture - Test dummy instrument with submodules
- `param_manager` fixture - ParameterManager for testing dynamic parameters

### Test Structure
```
test/pytest/              # Pytest test suite
  conftest.py           # Fixtures and setup
  test_basic_functionality.py
  test_serialize.py
  test_param_manager.py
  test_json_serializable.py
  test_server_gui.py

test/test_async_requests/  # Integration/stress tests
  test_client.py        # Client concurrency tests
  demo_concurrency.py   # Demo of concurrent access

test/prototyping/       # Exploratory tests and examples
```

### Running Specific Tests
```bash
# Run test file
pytest test/pytest/test_basic_functionality.py

# Run single test
pytest test/pytest/test_basic_functionality.py::Test_basic_functionality::test_create_and_get

# Run with output
pytest -s test/pytest/test_basic_functionality.py
```

## Important Files and Patterns

### Server Initialization
- `instrumentserver/apps.py` - Entry points and CLI argument parsing
- `instrumentserver/server/core.py:startServer()` - Creates and starts StationServer
- Server runs in QThread, GUI runs in main thread

### Client Usage Pattern

```python
from src.instrumentserver.client.proxy import Client

cli = Client()  # Connect to server
instr = cli.find_or_create_instrument('my_inst', 'my.module.MyInstrument')
value = instr.parameter.get()
instr.parameter.set(new_value)
```

### ClientStation Pattern (for multi-experiment isolation)

```python
from src.instrumentserver.client.proxy import ClientStation

station = ClientStation(name='experiment_1')
instr = station.find_or_create_instrument('inst', 'module.Instrument')
# Each ClientStation has isolated proxy instruments
```

### Adding Instruments at Runtime
- Use `ParameterManager` instrument or `find_or_create_instrument()`
- Instruments loaded from Python class path
- Must be QCoDeS Instrument subclass
- Submodules and channels supported

### Configuration
- Server config in YAML format
- See `doc/serverConfig.yml` for example
- Client config via Python code or YAML

## Recent Architecture Changes

**Per-Instrument Thread Safety (ce4190d)**
- Before: Global lock on entire server
- After: Per-instrument locks enable concurrent access to different instruments
- Same instrument still single-threaded (enforced by lock)

**Router/Dealer Pattern (f9753ea)**
- Replaced PULL/PUSH with ROUTER/DEALER
- Enables proper client identification and async reply routing
- ThreadPoolExecutor distributes work

**ClientStation Container (9171d8c)**
- Enables experiment isolation
- Multiple concurrent experiments on same server
- Proxy instruments owned by ClientStation

**Parameter Broadcasting (a71f423)**
- Separate ZMQ PUB socket for broadcasts
- Clients SUB asynchronously
- Real-time parameter updates to GUI

## Common Development Tasks

### Debugging
- Check `instrumentserver.log` and `instrumentclient.log` for errors
- Use `pytest -s` to see print statements
- Server GUI shows message log in real-time
- Look for per-instrument lock contention in logs

### Adding New Operation Types
1. Add Operation enum value in `blueprints.py`
2. Add ServerInstruction handling in `server/core.py:_handle()`
3. Add Client method in `client/proxy.py:Client`
4. Add corresponding ProxyInstrument method if needed

### Extending Client API
- Add methods to `Client` class in `client/proxy.py`
- Use `_baseClient.handleRemoteCall()` for low-level requests
- Follow pattern: call → instruction → send → receive → response

### Working with Parameters
- QCoDeS Parameter objects become ProxyParameter on client
- Get/set operations go through network
- Parameter metadata available via blueprint
- Validators and limits enforced on server side

## Deployment

### Docker Deployment
- See `instrumentserver/deployment/` for Docker configurations
- Grafana dashboard in `instrumentserver/dashboard/`
- CSV datasource for parameter logging

### Multi-Machine Setup
- Server runs on one machine (specified port)
- Clients connect via network (specify server host:port)
- ZMQ handles network communication
- Works across local networks and with proper routing

## Qt Integration

The codebase uses Qt for threading and GUI:
- `QtCore.QThread` - Server runs in separate thread
- `QtCore.Signal/Slot` - Inter-thread communication
- `QtWidgets` - GUI components
- `qtpy` - Qt abstraction layer (PyQt5/PySide2 compatibility)

Key pattern: Business logic (StationServer) in separate QThread, GUI in main thread, signals used for communication.

## Agent skills

### Issue tracker

GitHub issues on `toolsforexperiments/instrumentserver` (canonical upstream), accessed via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical defaults (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/` at repo root). See `docs/agents/domain.md`.