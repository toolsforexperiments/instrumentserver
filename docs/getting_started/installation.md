# Installation

:::{admonition} Not on PyPI yet
:class: note
instrumentserver is not published on PyPI yet (a release is planned). For now, every
install comes straight from the
[GitHub repository](https://github.com/toolsforexperiments/instrumentserver).
:::

## Requirements

You need **Python 3.11 or newer**. That's the same floor as QCoDeS, which instrumentserver is built on.

The recommended starting point is a local clone of the repository. In a terminal, `cd`
to the directory where you want the clone to live (the command below creates an
`instrumentserver` folder right where you run it), then:

```bash
git clone https://github.com/toolsforexperiments/instrumentserver.git
```

We recommend an editable installation of that clone: updating to the latest version is then
just a `git pull` away, and you can read (or tweak) the code you're actually running.
(If you'd rather skip the clone, the uv tab below has a clone-free alternative.)

## Installing

Pick the tab that matches how you manage your Python environments. We recommend uv.

::::{tab-set}

:::{tab-item} uv (recommended)
With [uv](https://docs.astral.sh/uv/), instrumentserver becomes a dependency of the
project you run your measurements from. From inside that project, add your local clone
as an editable dependency:

```bash
uv add --editable path/to/instrumentserver
```

This records the dependency in your project's `pyproject.toml` and installs it into the
project environment. After a `git pull` in the clone, your project picks up the new
version automatically.

If you'd rather not keep a local clone, you can add it as a git dependency instead:

```bash
uv add git+https://github.com/toolsforexperiments/instrumentserver.git
```

Updating then means running `uv lock --upgrade-package instrumentserver`.
:::

:::{tab-item} conda
We recommend one conda environment per measurement setup, with instrumentserver
installed alongside the rest of your measurement stack. Conda doesn't ship
instrumentserver as a package, so the installation goes through pip, inside the right
environment:

```bash
conda activate your-measurement-env
pip install -e path/to/instrumentserver
```

Double-check which environment is active before installing. A correct installation in the
wrong environment is the classic way to end up with "but I installed it!" confusion.
:::

:::{tab-item} pip + venv
The standard-library route: create a virtual environment, activate it, and install the
clone in editable mode.

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -e path/to/instrumentserver
```
:::

::::

## Optional: monitoring extra

If you plan to export instrument parameter changes to InfluxDB (see the
[monitoring guide](../user_guide/monitoring.md)), install the `monitoring` extra, which
adds the `influxdb-client` package:

```bash
pip install -e "path/to/instrumentserver[monitoring]"
```

Or with uv:

```bash
uv add --editable path/to/instrumentserver --extra monitoring
```

## Check that it worked

The installation puts five command line tools on your path. Ask the main one for help:

```bash
instrumentserver --help
```

If you see the usage message, you're done. Head to the [quickstart](quickstart.md) to
start a server and talk to your first instrument.
