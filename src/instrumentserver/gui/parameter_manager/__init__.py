"""The Parameter Manager GUI.

- :mod:`.logic` holds what builds no widgets: the Type claims and tint
  palette, the Lock rows and texts, the Types tab rows, and :class:`PMState`.
- :mod:`.panels` holds the gutter delegate, the Lock arm strip, the Locks
  panel and the Types tab.
- :mod:`.widget` holds :class:`ParameterManagerGui` and the model, tree view
  and create form it is built from.

Station configs name the widget as
``instrumentserver.gui.parameter_manager.ParameterManagerGui``; the older
``instrumentserver.gui.instruments.ParameterManagerGui`` still works.
"""

from .logic import PMState  # noqa: F401
from .widget import ModelParameterManager, ParameterManagerGui  # noqa: F401
