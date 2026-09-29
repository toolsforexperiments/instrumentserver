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

from .logic import (  # noqa: F401
    GUTTER_COLUMN,
    GUTTER_ROLE,
    GUTTER_WIDTH,
    LOCK_COLOUR,
    LOCK_COLUMN,
    LOCK_COLUMN_WIDTH,
    TINT_COLOURS,
    TINT_PALETTE,
    Claim,
    EntryRow,
    LockRow,
    PMState,
    TypePalette,
    also_types,
    build_lock_rows,
    compute_claims,
    followers_reaching,
    instances_of_type,
    lock_button_tooltip,
    lock_column_text,
    lock_root,
    parse_default_text,
    rank_lock_targets,
    relative_path,
    type_entry_rows,
)
from .panels import (  # noqa: F401
    ENTRIES_DEFAULT_WIDTH,
    ENTRIES_LOCK_WIDTH,
    ENTRIES_UNIT_WIDTH,
    INSTANCES_ALSO_WIDTH,
    INSTANCES_BUTTON_WIDTH,
    INSTANCES_COUNT_WIDTH,
    LOCK_PANEL_BUTTONS_WIDTH,
    LOCK_PANEL_NOTE,
    LOCK_PANEL_VALUE_WIDTH,
    LOCK_ROW_ROLE,
    GutterDelegate,
    LockArmStrip,
    LocksPanel,
    TypesPane,
    make_lock_button,
)
from .widget import (  # noqa: F401
    AddParameterWidget,
    ModelParameterManager,
    ParameterDeleteDelegate,
    ParameterManagerGui,
    ParameterManagerTreeView,
    ProfilesManager,
)
