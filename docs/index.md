---
myst:
  html_meta:
    "description lang=eng": "InstrumentServer - Remote instrument control via ZMQ"
html_theme.sidebar_secondary.remove: true
---

# InstrumentServer

**Distributed instrument control system for QCoDeS instruments via ZMQ**

[GitHub Repository](https://github.com/toolsforexperiments/instrumentserver) | [About](about.md)

## Overview

InstrumentServer is a distributed system for remote access to QCoDeS instruments. It enables multi-client instrument control through a ZMQ-based server-client architecture with real-time parameter broadcasting and concurrent request handling.

### Key Features

**Multi-Client Access**
- Multiple clients can simultaneously control the same server
- Thread-safe per-instrument locking prevents race conditions
- Concurrent access to different instruments

**Real-Time Monitoring**
- Broadcast parameter changes to all listening clients
- Asynchronous parameter updates via ZMQ PUB socket
- Real-time GUI updates across the network

**QCoDeS Integration**
- Native QCoDeS Station support
- Full instrument metadata and blueprint system
- Seamless proxy objects for remote instruments

**Robust Architecture**
- ZMQ ROUTER/DEALER pattern for reliable messaging
- ThreadPoolExecutor for concurrent request handling
- Automatic connection recovery with retry logic

## Documentation

```{toctree}
:maxdepth: 2
:caption: Contents

first_steps/index
user_guide/index
```

## Code Examples

```{toctree}
:maxdepth: 1
:caption: Examples

examples/index
```

## API Reference

The API documentation is automatically generated from the source code.

```{toctree}
:maxdepth: 1
:caption: API Reference

api/index
```