---
myst:
  html_meta:
    "description lang=eng": "InstrumentServer - Remote instrument control via ZMQ"
html_theme.sidebar_secondary.remove: true
---

# InstrumentServer

Distributed control of QCoDeS instruments over ZMQ: one server owns the hardware, many
clients talk to it through proxies. Part of the
[Tools for Experiments](https://toolsforexperiments.github.io/) suite.

[GitHub Repository](https://github.com/toolsforexperiments/instrumentserver) | [About Us](https://toolsforexperiments.github.io/about_us/organization.html)

:::{note}
We are rewriting this site page by page. Pages marked 🚧 are planned but not yet
written, and show what they will cover.
:::

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} Getting Started
:link: getting_started/index
:link-type: doc

Installation, your first server and client connection, and a conceptual overview
of how it all works.
:::

:::{grid-item-card} User Guide
:link: user_guide/index
:link-type: doc

How to use each feature: the Python client, the Server, the Parameter Manager,
Client Stations, monitoring, and configuration.
:::

:::{grid-item-card} Technical Guide
:link: technical_guide/index
:link-type: doc

How instrumentserver works inside: architecture, Blueprints and proxies, Broadcasts,
and custom widgets.
:::

:::{grid-item-card} API Reference
:link: api/index
:link-type: doc

Reference documentation for all public modules, generated from the source code.
:::

::::

```{toctree}
:maxdepth: 2
:hidden:

getting_started/index
user_guide/index
technical_guide/index
api/index
```
