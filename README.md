# instrumentserver

A tool for managing qcodes in a server environment

## Installation

For installing, use a developer pip install:
```bash
pip install --no-deps -e /folder/to/instrumentserver/
```

## Usage

### Starting the Server

Start the instrument server with:
```bash
instrumentserver
```

This will launch the server GUI with the following features:
- Device initialization and management
- Parameter management
- Instrument monitoring
- Logging capabilities

### Device Initialization

The server supports device initialization through configuration files:

1. Default Configuration:
   - Place your device configuration in `instrumentserver/instrumentserver/config/devices.json`
   - The server will automatically use this file when initializing devices

2. Configuration File Format:
   ```json
   {
       "device_name": {
           "instrument_class": "path.to.instrument.class",
           "parameter1": "value1",
           "parameter2": "value2"
       }
   }
   ```

3. Using the GUI:
   - Click "Devices" → "Initialize Devices" to load devices
   - Click "Devices" → "Show Device Status" to view initialized devices
   - The server will automatically use the default configuration if available
