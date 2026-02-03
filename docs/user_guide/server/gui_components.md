# GUI Components

InstrumentServer provides Qt-based GUI components for both server and client applications.

## Server GUI

### Running the Server with GUI

```bash
instrumentserver --gui True
```

### Server GUI Components

The server GUI consists of three main panels:

**Station List Panel**
- Tree view of all instruments in the QCoDeS Station
- Shows instrument names, parameters, and current values
- Color-coded status indicators
- Expandable tree structure for submodules and channels

**Server Status Panel**
- Real-time message log of all server activity
- Client requests and responses
- Error messages and warnings
- Timestamps for each event

**Station Object Info Panel**
- Detailed information about selected instrument
- Parameter specifications (units, limits, validators)
- Method signatures
- Instrument documentation and metadata

## Client GUI

### Client Station GUI

Connect to a remote server and control instruments with a graphical interface:

```bash
client-station-gui
```

### Client GUI Features

**Tab-Based Interface**
- One tab per instrument
- Detachable/dockable tabs for flexible layouts
- Tabbed parameter controls within each instrument

**Parameter Controls**
- Auto-generated widgets for different parameter types
- Text input for numerical values
- Combo boxes for enumerated parameters
- Checkboxes for boolean parameters
- Real-time validation and error messages

**Real-Time Updates**
- Automatic parameter update from server
- Subscribe to parameter changes
- Automatic refresh of GUI when values change
- Batch updates for efficiency

**Detached Server GUI**

Connect to a running server without hosting it:

```bash
instrumentserver-detached
```

This allows monitoring a server running on another machine without local server startup overhead.

## Custom GUI Components

### Building Instrument-Specific GUIs

InstrumentServer provides base classes for building custom GUIs:

```python
from instrumentserver.gui.base_instrument import BaseInstrumentGUI
from instrumentserver.gui.parameters import ParameterInput

class MyInstrumentGUI(BaseInstrumentGUI):
    def __init__(self, proxy_instrument):
        super().__init__(proxy_instrument)

        # Create parameter widgets
        voltage_input = ParameterInput(
            parameter=proxy_instrument.voltage,
            label="Voltage (V)"
        )

        self.add_widget(voltage_input)
```

### Available Widgets

- **ParameterInput** - Generic parameter control
- **NumericInput** - Numerical parameter input with validation
- **EnumSelect** - Enumeration parameter selection
- **RangeSlider** - Parameter with range limits
- **ReadOnlyDisplay** - Display-only parameter value

## Integration with Qt Applications

Embed InstrumentServer controls in your own Qt applications:

```python
from PyQt5.QtWidgets import QMainWindow
from instrumentserver.client.proxy import QtClient
from instrumentserver.gui.base_instrument import BaseInstrumentGUI

class MyApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create Qt-integrated client
        self.client = QtClient()

        # Get instrument and create GUI
        instrument = self.client.get_instrument('dmm')
        gui = BaseInstrumentGUI(instrument)

        self.setCentralWidget(gui)
```

## PyQt5 vs PySide2

InstrumentServer uses `qtpy` for Qt abstraction, supporting both PyQt5 and PySide2:

```bash
# Using PyQt5
pip install pyqt5

# Or using PySide2
pip install pyside2
```

Both work transparently with InstrumentServer.

## Styling

Apply custom stylesheets:

```python
stylesheet = """
    QLineEdit {
        background-color: #f0f0f0;
        border: 1px solid #ccc;
    }
"""

gui_widget.setStyleSheet(stylesheet)
```

## Next Steps

- Explore [Server Configuration](configuration.md)
- Learn [Client Development](../client/index.md)
- Read the [API Reference](../../api/index.md)