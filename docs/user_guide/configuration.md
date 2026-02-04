# Configuration Files

[//]: # (TODO: Make sure all of the comments are correct and up to date.)

This page covers the configuration files used by InstrumentServer: the **server configuration** file and the **listener configuration** file.

## Server Configuration

The server configuration file (typically `serverConfig.yml`) configures instruments, GUI defaults, and networking settings for the InstrumentServer.

### Example File

You can view the example file on GitHub: [serverConfig.yml](https://github.com/toolsforexperiments/instrumentserver/blob/master/docs/user_guide/serverConfig.yml)

```{literalinclude} serverConfig.yml
:language: yaml
```

### Instruments Section

The `instruments` section defines the instruments that the server will manage. Each instrument is identified by a name (e.g., `rr`, `dummy`) and has the following fields:

| Field | Description |
|-------|-------------|
| `type` | The fully qualified Python class path for the instrument (QCoDeS driver) |
| `initialize` | If `true`, the server creates an instance of this instrument at startup |
| `address` | (Optional) The network address of the instrument |
| `init` | (Optional) Additional initialization parameters passed to the instrument constructor |
| `gui` | (Optional) GUI-specific configuration for the instrument |

#### GUI Configuration

The `gui` field within an instrument allows customization of how the instrument appears in the GUI:

| Field | Description |
|-------|-------------|
| `type` | Widget class to use. Can be `generic` or a fully qualified Python class path |
| `kwargs` | Arguments passed to the widget constructor |

Within `kwargs`, you can configure which parameters and methods are hidden, starred, or trashed:

- **`parameters-hide`**: Parameters that will never be loaded or shown
- **`parameters-star`**: Parameters that start as starred (favorites)
- **`parameters-trash`**: Parameters that start in the trash
- **`methods-hide`**: Methods that will never be loaded or shown
- **`methods-star`**: Methods that start as starred
- **`methods-trash`**: Methods that start in the trash

### GUI Defaults Section

The `gui_defaults` section defines class-based defaults that apply to all instances of a given instrument class. This allows you to set common configurations once rather than repeating them for each instrument instance.

**Merge Order**: `__default__` → `ClassName` → `instance-specific`

- **`__default__`**: Settings that apply to ALL instruments unless overridden
- **Class-specific** (e.g., `DummyInstrumentWithSubmodule`): Settings that apply to all instances of that specific class
- **Instance-specific**: Settings defined in the instrument's `gui.kwargs` section

### Glob Pattern Matching

All hide/star/trash lists support glob pattern matching:

| Pattern | Description | Example |
|---------|-------------|---------|
| `*` | Matches any number of characters | `power_*` matches `power_level`, `power_offset` |
| `?` | Matches exactly one character | `ch?_gain` matches `ch1_gain`, `ch2_gain` |
| `[seq]` | Matches any character in the sequence | `trace_[0-3]` matches `trace_0` through `trace_3` |
| `[!seq]` | Matches any character NOT in the sequence | `param_[!xy]` matches `param_a` but not `param_x` |

### Networking Section

The `networking` section configures network addresses for the server:

| Field | Description |
|-------|-------------|
| `listeningAddress` | Additional address to listen for incoming messages |
| `externalBroadcast` | Address to broadcast parameter changes to (for listeners/dashboards) |

---

## Listener Configuration

The listener configuration file (typically `listenerConfig.yml`) configures the listener service that subscribes to broadcasts from instrument servers and writes data to storage (InfluxDB or CSV).

### Example File

You can view the example file on GitHub: [listenerConfig.yml](https://github.com/toolsforexperiments/instrumentserver/blob/master/docs/user_guide/listenerConfig.yml)

```{literalinclude} listenerConfig.yml
:language: yaml
```

### Common Fields

| Field | Description |
|-------|-------------|
| `addresses` | List of addresses to subscribe to broadcasts from (from instrument servers) |
| `params` | List of parameters to listen for. If empty, listens for all broadcasts |
| `type` | Type of listener: `"Influx"` or `"CSV"` |

### InfluxDB-Specific Fields

| Field | Description |
|-------|-------------|
| `token` | InfluxDB authentication token |
| `org` | InfluxDB organization name |
| `bucketDict` | Dictionary mapping instrument names to InfluxDB buckets |
| `url` | URL where InfluxDB is hosted (e.g., `"http://localhost:8086"`) |
| `measurementNameDict` | Dictionary mapping instrument names to measurement names |
| `timezone_name` | Timezone for timestamps (e.g., `"CDT"`, `"UTC"`) |

### CSV-Specific Fields

| Field | Description |
|-------|-------------|
| `csv_path` | Path to the CSV file for data output. File will be created if it doesn't exist |

---

## Starting Services

### Starting the Server

```bash
instrumentserver -c serverConfig.yml
```

To run without the GUI:

```bash
instrumentserver -c serverConfig.yml --gui False
```

### Starting the Listener

```bash
instrumentserver-listener -c listenerConfig.yml
```

To run in the background with output redirected:

```bash
nohup instrumentserver-listener -c listenerConfig.yml &
```