# Quickstart

:::{admonition} 🚧 Page in progress
:class: warning
The sections below are being written and verified one by one. Still to come:
first client connection, getting and setting a parameter, starting with a
config file, and where to go next.
:::

In the next few minutes you'll start a server, give it an instrument, and talk to that
instrument from a separate Python session. All you need is a working
[installation](installation.md). No hardware required: we'll use a dummy instrument
that ships with the package.

## Start the server

In a terminal (with your instrumentserver environment active), run:

```bash
instrumentserver
```

A window opens: this is the Server, the process that will own all your instruments.
It's empty for now, and it's listening for clients.

:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
The server GUI right after a bare `instrumentserver` launch: empty instrument
list, default window title. Capture the whole window.
:::

Leave it running. Everything else in this guide happens from a second terminal, a
notebook, or wherever you like to run Python.
