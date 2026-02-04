# Architecture Overview

InstrumentServer uses a distributed client-server architecture with ZMQ for network communication and Python threading for concurrent access.

## System Design

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

## Core Concepts

### Server-Side Components

**StationServer**
The main server object running in a separate QThread. It manages:
- QCoDeS Station with laboratory instruments
- ZMQ ROUTER socket for multi-client requests
- ThreadPoolExecutor for concurrent request processing
- Per-instrument locks for thread-safe access
- ZMQ PUB socket for parameter change broadcasts

**Per-Instrument Locking**
Each instrument has its own `threading.Lock` to ensure:
- Multiple threads can safely access different instruments concurrently
- Same instrument is always accessed single-threaded
- No race conditions when multiple clients operate on same instrument

### Client-Side Components

**BaseClient**
Low-level ZMQ DEALER socket communication providing:
- Request-reply pattern with timeout handling
- Automatic connection recovery and retry logic
- Serialization/deserialization of messages

**Proxy Objects**
High-level abstractions for remote access:
- `ProxyParameter` - Remote QCoDeS parameters with get/set interface
- `ProxyInstrumentModule` - Remote instruments, channels, and submodules
- `Client` - Main API for instrument discovery and control
- `ClientStation` - Container for experiment-specific instrument proxies

## Communication Protocol

1. **Client Request** → ServerInstruction serialized to JSON
2. **ZMQ DEALER** sends request to server's ROUTER socket
3. **ROUTER** routes request to available ThreadPoolExecutor worker
4. **StationServer._callObject()** acquires per-instrument lock
5. **Operation executes** (get/set/call method)
6. **Lock released**, response returned
7. **Parameter broadcasts** sent via ZMQ PUB socket for real-time updates

## Operation Types

- **GET_EXISTING_INSTRUMENTS** - List available instruments
- **CREATE_INSTRUMENT** - Create new instrument from specification
- **CALL** - Call methods, get/set parameters
- **GET_BLUEPRINT** - Retrieve metadata about instruments/parameters

## Key Design Patterns

### ZMQ ROUTER/DEALER Pattern
Enables true async concurrency by:
- Routing requests to available workers
- Properly identifying clients for async replies
- Supporting multiple simultaneous client connections

### Async Request Handling
ThreadPoolExecutor distributes work across multiple threads:
- Each request runs in a separate thread
- Per-instrument locks prevent concurrent access to same instrument
- Different instruments accessed concurrently for performance

### Broadcast Architecture
Real-time parameter updates via separate ZMQ PUB socket:
- Server broadcasts on PUB socket
- Multiple clients SUB asynchronously
- No polling needed - updates pushed to clients immediately
- Clients listen in background thread

### Blueprint System
Metadata system providing:
- Parameter definitions (units, limits, validators)
- Instrument structure and submodules
- Method signatures
- Full client-side introspection without separate queries

## Data Serialization

All messages are serialized to JSON for network transmission:
- ServerInstruction (client request)
- ServerResponse (server reply with result or error)
- ParameterBluePrint (parameter metadata)
- InstrumentModuleBluePrint (instrument metadata)

