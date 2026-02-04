# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add instrumentserver package to path for autodoc
sys.path.insert(0, os.path.abspath('..'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'InstrumentServer'
copyright = '2020-2026, Wolfgang Pfaff'
author = 'Wolfgang Pfaff'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'myst_parser',            # Markdown support
    'sphinx.ext.autodoc',     # API documentation from docstrings
    'sphinx.ext.autosummary', # Generate summary tables for modules
    'sphinx.ext.napoleon',    # Support for NumPy and Google style docstrings
    'sphinx.ext.viewcode',    # Add links to source code
    'nbsphinx',               # Jupyter notebook support
    'sphinx.ext.intersphinx', # Link to other project docs
]

# MyST Parser configuration
myst_enable_extensions = [
    "colon_fence",      # ::: for admonitions
    "deflist",          # Definition lists
    "dollarmath",       # Inline and display math using $
    "fieldlist",        # Field lists
    "html_admonition",  # HTML-style admonitions
    "html_image",       # HTML images
    "linkify",          # Auto-detect URLs
    "replacements",     # Text replacements
    "smartquotes",      # Smart quotes
    "substitution",     # Variable substitutions
    "tasklist",         # Task lists
]

# Allow MyST to parse Sphinx roles and directives
myst_enable_roles = True

# Autosummary configuration (auto-generate API docs)
autosummary_generate = True
autosummary_generate_overwrite = True

# Autodoc configuration (required for proper cross-references)
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
}

# MyST configuration for proper cross-references in Markdown
myst_linkify_fuzzy_links = True

# nbsphinx configuration (for Jupyter notebooks)
nbsphinx_execute = 'never'  # Don't execute notebooks during build (safer)
nbsphinx_allow_errors = True  # Continue building if notebook has errors
nbsphinx_kernel_name = 'python3'

# Intersphinx configuration (link to other docs)
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'qcodes': ('https://qcodes.github.io/Qcodes/', None),
    'zmq': ('https://pyzmq.readthedocs.io/', None),
}

templates_path = ['_templates']
exclude_patterns = ['build', 'Thumbs.db', '.DS_Store', '**.ipynb_checkpoints']

# -- Internationalization ----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#internationalization

language = "en"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pydata_sphinx_theme"
html_static_path = ['_static']
html_logo = '_static/logo.png'
html_baseurl = 'https://toolsforexperiments.github.io/instrumentserver/'

html_theme_options = {
    "show_nav_level": 2,
    "logo": {
        "text": "InstrumentServer",
    },
    "external_links": [
        {
            "url": "https://toolsforexperiments.github.io/",
            "name": "Tools for Experiments",
        },
        {
            "url": "https://toolsforexperiments.github.io/labcore/",
            "name": "Labcore",
        },
        {
            "url": "https://toolsforexperiments.github.io/plottr/",
            "name": "Plottr",
        },
    ],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/toolsforexperiments/instrumentserver",
            "icon": "fa-brands fa-github",
        }
    ],
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["navbar-icon-links", "theme-switcher"],
    "footer_start": ["copyright"],
    "footer_center": ["sphinx-version"],
}

# HTML context for custom variables
html_context = {
    "default_mode": "auto"  # Light/dark theme
}