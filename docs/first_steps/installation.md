# Installation

## Prerequisites

InstrumentServer requires Python 3.7+ and depends on several key packages:

- **QCoDeS**: For instrument abstraction and control
- **ZMQ (PyZMQ)**: For network communication
- **Qt/PyQt5**: For GUI components (optional for headless server)

## Install from Repository

The recommended way to install InstrumentServer is from the git repository:

```bash
pip install --no-deps -e /path/to/instrumentserver/
pip install zmq qcodes qtpy pyqt5 bokeh scipy
```

## Verify Installation

Test your installation by starting the Python interpreter and importing the module:

```python
from instrumentserver.client.proxy import Client
from instrumentserver.server.core import StationServer
print("InstrumentServer installed successfully!")
```

## Next Steps

Once installed, proceed to the [Basic Server Setup](basic_server_setup.md) guide to learn how to start your first InstrumentServer instance.

## Troubleshooting

### ZMQ Installation Issues

If you encounter ZMQ-related errors, ensure it's properly installed:

```bash
pip install -U pyzmq
```

### Qt/PyQT5 Issues

For GUI functionality, ensure Qt bindings are available:

```bash
pip install -U pyqt5 qtpy
```

If you're running on a headless server (no display), you can run the server without GUI and use remote clients only.
