# InstrumentServer Documentation

This directory contains the source files for the InstrumentServer documentation website.

## Building the Documentation

### Prerequisites

Install the documentation build dependencies:

```bash
pip install -r docs_requirements.txt
```

### Build HTML

To build the HTML documentation:

```bash
cd docs
make html
```

The built documentation will be in `docs/build/html/`. Open `index.html` in your browser to view it.

### Clean Build

To remove build artifacts and start fresh:

```bash
make clean
make html
```

### Live Preview

For development with automatic rebuilds:

```bash
pip install sphinx-autobuild
sphinx-autobuild docs docs/build/html
```

Then open `http://localhost:8000` in your browser.

## Documentation Structure

```
docs/
├── index.md                    # Main landing page
├── about.md                    # About InstrumentServer
├── conf.py                     # Sphinx configuration
├── Makefile                    # Build commands
│
├── first_steps/               # Getting started guide
│   ├── index.md
│   ├── installation.md
│   ├── basic_server_setup.md
│   └── first_client.md
│
├── user_guide/                # Comprehensive user guide
│   ├── index.md
│   ├── architecture/           # System architecture
│   │   └── index.md
│   ├── server/                 # Server configuration and operation
│   │   ├── index.md
│   │   ├── configuration.md
│   │   ├── monitoring.md
│   │   └── gui_components.md
│   └── client/                 # Client development guide
│       ├── index.md
│       ├── basic_usage.md
│       ├── parameters_and_methods.md
│       └── advanced_patterns.md
│
├── examples/                   # Code examples
│   └── index.md
│
├── api/                        # Auto-generated API reference
│   ├── index.md
│   └── generated/              # Auto-generated files
│
├── _static/                    # Static files (images, logos)
├── _templates/                 # Custom Sphinx templates
└── build/                      # Output directory (generated)
```

## Theme

The documentation uses the **pydata-sphinx-theme**, which provides:
- Modern, responsive design
- Light/dark mode support
- Mobile-friendly navigation
- Integrated search

## Contributing to Documentation

### Adding New Pages

1. Create a new `.md` file in the appropriate section
2. Add it to the `toctree` directive in the parent `index.md`
3. Build and test locally with `make html`

### Writing Style

- Use Markdown for all new content
- Use clear, concise headings
- Include code examples where appropriate
- Add cross-references using MyST syntax

### Code Examples

Include executable examples:

```python
from instrumentserver.client.proxy import Client

client = Client()
instruments = client.list_instruments()
```

Use admonitions for notes and warnings:

```markdown
:::{note}
This is a note.
:::

:::{warning}
This is a warning.
:::
```

## Deployment

Documentation is built and deployed automatically on GitHub Pages:

```
https://toolsforexperiments.github.io/instrumentserver/
```

Commits to the main branch trigger automatic builds.

## References

- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [MyST Parser](https://myst-parser.readthedocs.io/)
- [PyData Theme](https://pydata-sphinx-theme.readthedocs.io/)