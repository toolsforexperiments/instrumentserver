"""Parameter Manager GUI logic that builds no widgets: the Type claims and
tint palette, the Lock rows and texts, the Types tab rows, and the
:class:`PMState` cache of Types and Locks."""

import ast
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    cast,
)

from ... import QtCore, QtGui
from ...blueprints import (
    PMLockBluePrint,
    PMTypeBluePrint,
)

# ----------------- Tints --------------------------------------------------------------


#: Logical index of the gutter column of :class:`.ModelParameterManager`,
#: whose items carry a row's stack of Types for the
#: :class:`.GutterDelegate` to draw. The existing columns keep their
#: indexes: name (0), unit (1), delegate (2).
GUTTER_COLUMN = 3

#: Fixed pixel width of the gutter column in the view.
GUTTER_WIDTH = 12

#: Data role under which a row's stack of Type names is stored on its
#: gutter item; :class:`.GutterDelegate` reads it to draw the bands.
GUTTER_ROLE = cast(
    "QtCore.Qt.ItemDataRole", QtCore.Qt.ItemDataRole.UserRole + 1
)

#: The mock's TINTS for a light theme: ``tint`` and ``tintAlt`` are the
#: row background of a claimed row (``tintAlt`` for every other sibling
#: row), ``bar`` the colour of its gutter band. The slot of a Type is its
#: index in this list.
TINT_PALETTE: List[Dict[str, str]] = [
    {"tint": "#e8f1fb", "tintAlt": "#dfe9f6", "bar": "#4a7fc1"},
    {"tint": "#e9f4e9", "tintAlt": "#e0ede0", "bar": "#4f9e57"},
    {"tint": "#f6efe4", "tintAlt": "#efe7db", "bar": "#b98a3e"},
    {"tint": "#f9ecec", "tintAlt": "#f2e3e3", "bar": "#b5605f"},
    {"tint": "#e5f4f2", "tintAlt": "#dcece9", "bar": "#3f9490"},
]

#: The same five hues for a dark theme, slot for slot: dark, low-saturation
#: tints that keep the theme's light text readable, and brighter bars so
#: the gutter bands stand out on a dark background.
TINT_PALETTE_DARK: List[Dict[str, str]] = [
    {"tint": "#1e2a3a", "tintAlt": "#233245", "bar": "#5b8fd1"},
    {"tint": "#1e2e21", "tintAlt": "#243627", "bar": "#5fae67"},
    {"tint": "#33291b", "tintAlt": "#3b3020", "bar": "#c99a4e"},
    {"tint": "#352122", "tintAlt": "#3e2728", "bar": "#c5706f"},
    {"tint": "#1b302e", "tintAlt": "#213835", "bar": "#4fa4a0"},
]

#: The palettes as QColors, in the same slot order.
TINT_COLOURS: List[Dict[str, QtGui.QColor]] = [
    {name: QtGui.QColor(value) for name, value in entry.items()}
    for entry in TINT_PALETTE
]
TINT_COLOURS_DARK: List[Dict[str, QtGui.QColor]] = [
    {name: QtGui.QColor(value) for name, value in entry.items()}
    for entry in TINT_PALETTE_DARK
]


def is_dark_theme() -> bool:
    """Whether the application currently uses a dark theme: its palette's
    window colour is darker than its window text. Reading the palette
    (rather than the platform's colour scheme) also covers a dark palette
    or style sheet set on the application itself."""
    palette = QtGui.QGuiApplication.palette()
    window = palette.color(QtGui.QPalette.ColorRole.Window)
    text = palette.color(QtGui.QPalette.ColorRole.WindowText)
    return window.lightness() < text.lightness()


def tint_colours() -> List[Dict[str, QtGui.QColor]]:
    """The tint palette for the current theme (:func:`is_dark_theme`)."""
    return TINT_COLOURS_DARK if is_dark_theme() else TINT_COLOURS


@dataclass
class Claim:
    """What the tree shows for one row that Types carry (the mock's
    ``claims()``): the Claiming Type whose tint the row shows, the Instance
    submodule path that claims it, and every Type carrying the row,
    outermost first (the gutter draws one band per Type, up to three)."""

    type: str
    instance: str
    stack: List[str]


def _nested_claim_prefixes(
    blueprint: PMTypeBluePrint,
    types: Mapping[str, PMTypeBluePrint],
) -> Dict[str, str]:
    """Map every effective path of the Type ``blueprint`` that a Nested
    Type defines to the dotted submodule chain under which its defining
    Type sits (the mock's ``at``): a ``qubit`` nesting a ``readout`` at its
    submodule ``readout``, with the ``readout`` nesting a ``pulse_window``
    at ``pw``, maps the effective path ``readout.pw.win`` to
    ``readout.pw``.

    Mirrors how ``params.py`` expands the effective set
    (``_collect_effective``): the entries a Type defines itself are left
    out (they claim at the Instance itself) and each Nested Type's own
    entries are recorded under the chain that leads to it.
    """
    at_by_path: Dict[str, str] = {}

    def walk(blueprint: PMTypeBluePrint, prefix: str, seen: Tuple[str, ...]) -> None:
        for submodule, nested_name in blueprint.nested.items():
            if nested_name in seen:
                continue  # cycles are refused by the Parameter Manager
            nested = types.get(nested_name)
            if nested is None:
                continue
            at = prefix + submodule
            for path, spec in nested.effective.items():
                if spec.get("from_type") == nested_name:
                    at_by_path[f"{at}.{path}"] = at
            walk(nested, f"{at}.", seen + (nested_name,))

    walk(blueprint, "", (blueprint.name,))
    return at_by_path


def _carries_effective_set(
    instance: str,
    effective: Mapping[str, Mapping[str, str]],
    parameters: Mapping[str, str],
) -> bool:
    """Whether the candidate Instance ``instance`` carries every path of
    the effective set ``effective`` with the unit the Type declares (D12):
    matching requires existence and unit, compared as strings; values are
    irrelevant."""
    prefix = f"{instance}."
    for path, spec in effective.items():
        if parameters.get(prefix + path) != spec["unit"]:
            return False
    return True


def _instance_candidates(parameters: Mapping[str, str]) -> List[str]:
    """Every submodule path the parameter rows imply, sorted: every proper
    dotted prefix of a parameter path, never the root and never anything
    under the Globals submodule (D12). This is the candidate set both
    :func:`compute_claims` and :func:`instances_of_type` match against."""
    candidates = set()
    for path in parameters:
        segments = path.split(".")
        for depth in range(1, len(segments)):
            candidate = ".".join(segments[:depth])
            if "_globals" in candidate.split("."):
                continue  # Globals is excluded from matching at any depth
            candidates.add(candidate)
    return sorted(candidates)


def compute_claims(
    types: Mapping[str, PMTypeBluePrint],
    parameters: Mapping[str, str],
) -> Dict[str, Claim]:
    """The mock's ``claims()`` ported to the client-side state (plan task
    5.2): which Type claims each row of the Parameter Manager tree, and
    which stack of Types carries it.

    :param types: the Parameter Manager's Types (``PMState.types``), each
        as its :class:`PMTypeBluePrint`.
    :param parameters: every parameter row of the tree as ``{path relative
        to the Parameter Manager: unit}``.
    :return: for every claimed parameter path and submodule path, its
        :class:`Claim`.

    Matching mirrors ``ParameterManager.instances_of`` (D12) client-side:
    a candidate is every submodule path derived from the parameter paths
    (every proper dotted prefix; never the root, never anything under
    Globals) and it is an Instance when it carries every effective path
    with the declared unit. The Claiming Type is the innermost (the
    longest Instance path), then the largest effective set, then the Type
    name. A Nested Type claims at and below its submodule, so a row it
    defines is claimed by it, with the outer Types behind it in the stack.
    """
    # candidate Instances: every proper dotted prefix of a parameter path
    candidates = _instance_candidates(parameters)

    claims_by_path: Dict[str, List[Tuple[str, str, int]]] = {}
    winning: Dict[str, Tuple[str, str, int]] = {}

    def put(path: str, type_name: str, instance: str, size: int) -> None:
        # one (Type, Instance, effective set size) claim, as the mock's
        # all/map pair; the winner keeps the innermost Instance, then the
        # largest effective set, then the Type name
        claim = (type_name, instance, size)
        claims_by_path.setdefault(path, []).append(claim)
        old = winning.get(path)
        if old is None or (-len(instance), -size, type_name) < (
            -len(old[1]),
            -old[2],
            old[0],
        ):
            winning[path] = claim

    for type_name, blueprint in types.items():
        effective = blueprint.effective
        if not effective:
            continue  # an empty Type has no Instances
        size = len(effective)
        at_by_path = _nested_claim_prefixes(blueprint, types)
        for instance in candidates:
            if not _carries_effective_set(instance, effective, parameters):
                continue
            # the Instance row itself is claimed by its Type, as in the mock
            put(instance, type_name, instance, size)
            for path in effective:
                # every row at and above the parameter, down to the
                # parameter itself, is claimed at the Instance
                at = at_by_path.get(path, "")
                spec = effective[path]
                owner_instance = f"{instance}.{at}" if at else None
                at_depth = len(at.split(".")) if at else 0
                segments = path.split(".")
                for depth in range(1, len(segments) + 1):
                    row = f"{instance}.{'.'.join(segments[:depth])}"
                    put(row, type_name, instance, size)
                    if owner_instance is not None and depth >= at_depth:
                        # the Nested Type claims at and below its submodule
                        put(row, spec["from_type"], owner_instance, size)

    claims: Dict[str, Claim] = {}
    for path, path_claims in claims_by_path.items():
        # the stack is every Type carrying the row, outermost first
        # (shortest Instance path, then the larger effective set),
        # de-duplicated by Type
        stack: List[str] = []
        for name in [
            entry[0]
            for entry in sorted(
                path_claims, key=lambda entry: (len(entry[1]), -entry[2], entry[0])
            )
        ]:
            if name not in stack:
                stack.append(name)
        type_name, instance, _ = winning[path]
        claims[path] = Claim(type=type_name, instance=instance, stack=stack)
    return claims


class TypePalette:
    """Assigns the fixed tint palette's slots to the Types the GUI knows.

    A Type keeps its slot while it exists: the slot is assigned when the
    GUI first sees the Type (in ``PMState.types`` order after a refresh,
    then each new Type from a ``pm-type-update`` Broadcast), it never
    changes while the Type is in the state, and it is freed when the Type
    is removed. A new Type takes the lowest free slot, or slot 0 when all
    five are used (the mock's ``freeTint`` recycles when exhausted).
    """

    def __init__(self) -> None:
        self.slots: Dict[str, int] = {}

    def sync(self, type_names: Any) -> None:
        """Free the slots of Types that are gone and assign slots to new
        ones, in the given creation order.

        :param type_names: the names of the Types the GUI knows
            (``PMState.types``).
        """
        names = list(type_names)
        for name in [known for known in self.slots if known not in names]:
            del self.slots[name]
        used = set(self.slots.values())
        for name in names:
            if name in self.slots:
                continue
            slot = next(
                (index for index in range(len(TINT_PALETTE)) if index not in used),
                0,
            )
            self.slots[name] = slot
            used.add(slot)

    def colours(self, type_name: str) -> Optional[Dict[str, QtGui.QColor]]:
        """The palette entry of the Type ``type_name`` (``tint``,
        ``tintAlt`` and ``bar``) for the current theme, or ``None`` when it
        has no slot."""
        slot = self.slots.get(type_name)
        return None if slot is None else tint_colours()[slot]

    def bar_colour(self, type_name: str) -> Optional[QtGui.QColor]:
        """The gutter band colour of the Type ``type_name``."""
        colours = self.colours(type_name)
        return None if colours is None else colours["bar"]


# ----------------- Locks --------------------------------------------------------------


#: Logical index of the Lock column of :class:`.ModelParameterManager`
#: (plan task 5.3). The existing columns keep their indexes: name (0),
#: unit (1), delegate (2), gutter (3). The view shows the Lock column
#: between the unit and the delegate column.
LOCK_COLUMN = 4

#: Fixed default pixel width of the Lock column in the view (the user can
#: resize it: the section is Interactive).
LOCK_COLUMN_WIDTH = 140

#: The mock's one purple (its ``--log-value`` token): the fill of a row's
#: lock button while its Lock is locked.
LOCK_COLOUR = "#7e5bef"


def lock_button_tooltip(locked: bool, target: str) -> str:
    """The lock/relock button's tooltip for one Lock state (the mock's
    strings), with ``target`` relative to the Parameter Manager. Shared by
    the tree's per-row widget (plan task 5.3) and the Locks panel (plan
    task 5.4)."""
    if locked:
        return f"locked to {target} — unlock and go back to its own value"
    return f"unlocked — lock to {target} again"


def relative_path(full: str, instrument_name: str) -> str:
    """The path relative to the Parameter Manager: ``full`` with the
    ``<instrument_name>.`` prefix stripped. ``PMLockBluePrint.target``
    stores the full dotted path, while model item names and every string
    the GUI shows the user are relative to the Parameter Manager."""
    prefix = f"{instrument_name}."
    return full[len(prefix):] if full.startswith(prefix) else full


def lock_column_text(
    path: str,
    locks: Mapping[str, PMLockBluePrint],
    instrument_name: str,
) -> str:
    """The text the Lock column shows for the parameter row ``path`` (a
    path relative to the Parameter Manager), computed client-side over the
    state's Locks (plan task 5.3; the mock's lock cell).

    A Follower shows its own Lock state: ``locked to <target>`` while
    locked, ``unlocked · <target>`` (middle dot) while unlocked, with the
    Target relative to the Parameter Manager. A parameter that is no
    Follower but the Target of ``N`` Locks — locked and unlocked alike,
    the way :meth:`ParameterManager.followers_of` counts — shows
    ``target ×N`` (multiplication sign). Every other row shows nothing.

    A row that is both Follower and Target shows its Follower text, which
    wins over the Target note (the mock's ``rec.lockedTo || srcNote(p)``).
    """
    lock = locks.get(path)
    if lock is not None:
        # the Follower's own Lock state wins over the Target note
        target = relative_path(lock.target, instrument_name)
        if lock.locked:
            return f"locked to {target}"
        return f"unlocked · {target}"
    full_path = f"{instrument_name}.{path}"
    count = sum(1 for other in locks.values() if other.target == full_path)
    if count:
        return f"target ×{count}"
    return ""


def followers_reaching(
    path: str,
    locks: Mapping[str, PMLockBluePrint],
    instrument_name: str,
) -> List[str]:
    """Paths (relative to the Parameter Manager) of every Follower whose
    locked Lock targets the parameter at ``path``, directly or over a
    chain of locked Locks.

    Only locked hops count (D7): an unlocked Lock answers ``get`` with its
    own value, so the Followers behind it do not see an update made past
    it. The walk follows each hop's Target and stops there — no infinite
    loop on a cycle, and every Follower appears once.
    """
    prefix = f"{instrument_name}."
    found: List[str] = []
    seen: set = set()
    targets = [prefix + path]
    index = 0
    while index < len(targets):
        current = targets[index]
        index += 1
        for follower, lock in locks.items():
            if not lock.locked or lock.target != current or follower in seen:
                continue
            seen.add(follower)
            found.append(follower)
            targets.append(prefix + follower)
    return found


def rank_lock_targets(
    follower: str,
    candidates: Iterable[str],
    claims: Mapping[str, Claim],
    arm_rel: Optional[str] = None,
) -> List[str]:
    """The arm strip's Target candidates in the mock's completer order.

    ``arm_rel`` is the Follower's path relative to its Instance (the part
    behind the Claiming Type's Instance path), or ``None`` when the
    Follower is claimed by no Type; an explicit ``arm_rel`` argument
    overrides it, which the Types tab's Type Lock re-target (plan task
    5.5) uses to rank for a Type's entry path — there is no claimed
    Follower and so nothing to exclude. Rank 0: the candidate's own
    relative path equals ``arm_rel`` (the same leaf on a sibling Instance,
    the mock's first pick). Rank 1: ``.<arm_rel>`` occurs in the candidate
    (a submodule on the way). Rank 2: everything else. Equal ranks order
    alphabetically; the Follower itself is never a candidate. Cycles are
    not filtered here: the Server refuses them and the arm strip shows its
    error text.
    """
    if arm_rel is None:
        follower_claim = claims.get(follower)
        arm_rel = (
            follower[len(follower_claim.instance) + 1:]
            if follower_claim is not None
            else None
        )

    def own_rel(candidate: str) -> Optional[str]:
        claim = claims.get(candidate)
        if claim is None:
            return None
        return candidate[len(claim.instance) + 1:]

    ranked: List[Tuple[int, str]] = []
    for candidate in candidates:
        if candidate == follower:
            continue  # the Follower itself is never a candidate
        rel = own_rel(candidate)
        if arm_rel is not None and rel == arm_rel:
            rank = 0
        elif arm_rel is not None and f".{arm_rel}" in candidate:
            rank = 1
        else:
            rank = 2
        ranked.append((rank, candidate))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))
    return [path for _, path in ranked]


@dataclass
class LockRow:
    """One row of the Locks panel (plan task 5.4): a Target of one or more
    Locks — plain, or the Target of a Type Lock — and the Followers beneath
    it, recursively for chains. ``type_locks`` holds every ``(Type name,
    entry path)`` whose Type Lock Target the row is; ``lock`` is the row's
    own Lock (``None`` for a plain Target)."""

    path: str
    type_locks: List[Tuple[str, str]]
    lock: Optional[PMLockBluePrint]
    children: List["LockRow"]


def lock_root(
    path: str,
    locks: Mapping[str, PMLockBluePrint],
    instrument_name: str,
) -> str:
    """The end of the chain of locked Locks that starts at ``path`` (the
    mock's ``root``): the parameter a locked read at ``path`` finally asks.
    Only locked hops count (D7): an unlocked Lock answers ``get`` with its
    own value, so the walk stops there. A ``seen`` set guards against a
    cycle. Paths are relative to the Parameter Manager, except the stored
    ``PMLockBluePrint.target``, which is relativized on the way."""
    current = path
    seen: set = set()
    while current not in seen:
        seen.add(current)
        lock = locks.get(current)
        if lock is None or not lock.locked:
            return current
        current = relative_path(lock.target, instrument_name)
    return current


def build_lock_rows(
    locks: Mapping[str, PMLockBluePrint],
    types: Mapping[str, PMTypeBluePrint],
    instrument_name: str,
) -> List[LockRow]:
    """The Locks panel's rows from the client-side state (plan task 5.4;
    the mock's locks-panel walk).

    ``locks`` maps each Follower's path (relative to the Parameter
    Manager) to its :class:`PMLockBluePrint`; ``types`` maps each Type's
    name to its :class:`PMTypeBluePrint`. An unlocked Lock still
    remembers its Target (D5), so a Follower's Lock names its Target
    whether the Lock is locked or not.

    The Targets are the unique Targets of the Locks, in ``locks`` order.
    The roots are the Targets that carry no Lock of their own, the Type
    Lock Targets first (a stable sort, like the mock's), each walked
    recursively into its Followers — a ``seen`` set guards against loops —
    and then any Target the first walk did not reach (the mock's second
    pass, e.g. a cycle among Followers). Every row carries its own Lock
    (``None`` for a plain Target) and its ``(Type, entry)`` pairs.
    """

    def target_of(follower: str) -> Optional[str]:
        lock = locks.get(follower)
        return (
            None if lock is None else relative_path(lock.target, instrument_name)
        )

    targets: List[str] = []
    for follower in locks:
        target = target_of(follower)
        if target is not None and target not in targets:
            targets.append(target)

    def type_locks_at(path: str) -> List[Tuple[str, str]]:
        found: List[Tuple[str, str]] = []
        for type_name, blueprint in types.items():
            for entry_path, spec in blueprint.parameters.items():
                entry_target = spec.get("target")
                if (
                    entry_target is not None
                    and relative_path(entry_target, instrument_name) == path
                ):
                    found.append((type_name, entry_path))
        return found

    def followers(path: str) -> List[str]:
        return [
            follower for follower in locks if target_of(follower) == path
        ]

    rows: List[LockRow] = []
    seen: set = set()

    def walk(path: str) -> Optional[LockRow]:
        if path in seen:
            return None
        seen.add(path)
        row = LockRow(
            path=path,
            type_locks=type_locks_at(path),
            lock=locks.get(path),
            children=[],
        )
        for child_path in followers(path):
            child = walk(child_path)
            if child is not None:
                row.children.append(child)
        return row

    # Type Lock Targets first, plain Targets follow — a stable sort,
    # like the mock's
    roots = [target for target in targets if target not in locks]
    roots.sort(key=lambda target: 0 if type_locks_at(target) else 1)
    for target in roots:
        row = walk(target)
        if row is not None:
            rows.append(row)
    # the mock's second pass: any Target the first walk did not reach
    for target in targets:
        row = walk(target)
        if row is not None:
            rows.append(row)
    return rows


def lock_row_paths(rows: List[LockRow]) -> List[str]:
    """Every row path of the built rows, depth first."""
    paths: List[str] = []
    for row in rows:
        paths.append(row.path)
        paths.extend(lock_row_paths(row.children))
    return paths


# ----------------- Types tab ----------------------------------------------------------


@dataclass
class EntryRow:
    """One row of the Types tab's entries pane (plan task 5.5; the mock's
    ``tParamRows``): a submodule row of the selected Type's tree, or one
    entry of it.

    ``kind`` is ``"submodule"`` or ``"entry"``. A submodule row carries
    ``nested_type`` — the Type required at that submodule, or ``None`` for
    a structural row that only carries the rows below it. An entry row
    carries
    the effective entry's ``unit`` and defining Type (``from_type``),
    whether the selected Type defines the entry itself (``own``), its
    ``default`` — an own entry's stored default, a Nested Type entry's
    default as stored on the defining Type — and, own entries only, the
    ``target`` of the entry's Type Lock relative to the Parameter Manager
    (``None`` while it has none).
    """

    path: str
    kind: str
    unit: str = ""
    nested_type: Optional[str] = None
    own: bool = False
    from_type: Optional[str] = None
    default: Any = None
    target: Optional[str] = None


def _nested_type_at(
    blueprint: PMTypeBluePrint,
    types: Mapping[str, PMTypeBluePrint],
    submodule: str,
) -> Optional[str]:
    """The Type required at the submodule ``submodule`` (a dotted path
    relative to the Type ``blueprint``): the walk follows the ``nested``
    maps down the segments, the way :func:`_nested_claim_prefixes` walks.
    ``None`` when no Nested Type is required there — a structural row —
    or when a nested Type of the chain is missing from ``types``."""
    current = blueprint
    for segment in submodule.split("."):
        if current is None:
            return None
        nested_name = current.nested.get(segment)
        if nested_name is None:
            return None
        current = types.get(nested_name)
    return current.name if current is not None else None


def type_entry_rows(
    type_name: str,
    types: Mapping[str, PMTypeBluePrint],
    instrument_name: str = "",
) -> List[EntryRow]:
    """The entries-pane rows of the Type ``type_name`` (plan task 5.5):
    its effective parameter set as a segment-sorted tree of submodule and
    entry rows.

    The sort is segment-wise like the mock's (paths order by their dotted
    segments), so a submodule row sorts directly before the rows below it
    and the list reads as a tree in order.

    An entry the Type defines itself (``from_type == type_name``) is
    ``own``: its ``default`` and ``target`` come from the Type's own
    entry, with the stored Type Lock Target relativized with
    ``instrument_name``. An entry a Nested Type defines shows that Type
    as ``from_type`` and the defining Type's own default for the path
    relative to it (the mock's ``ownerRel``).

    :param type_name: the selected Type's name.
    :param types: the Parameter Manager's Types (``PMState.types``).
    :param instrument_name: the Parameter Manager's name, for
        relativizing the stored Type Lock Targets; without it the stored
        full-form Targets are returned unchanged.
    :return: the rows, parents before children.
    """
    blueprint = types.get(type_name)
    if blueprint is None:
        return []
    at_by_path = _nested_claim_prefixes(blueprint, types)
    rows: List[EntryRow] = []
    submodule_paths: set = set()
    for path in sorted(blueprint.effective, key=lambda entry: entry.split(".")):
        segments = path.split(".")
        for depth in range(1, len(segments)):
            submodule = ".".join(segments[:depth])
            if submodule in submodule_paths:
                continue
            submodule_paths.add(submodule)
            rows.append(
                EntryRow(
                    path=submodule,
                    kind="submodule",
                    nested_type=_nested_type_at(blueprint, types, submodule),
                )
            )
        spec = blueprint.effective[path]
        from_type = spec["from_type"]
        own = from_type == type_name
        if own:
            entry = blueprint.parameters.get(path, {})
            default = entry.get("default")
            target = entry.get("target")
            if target is not None and instrument_name:
                target = relative_path(target, instrument_name)
        else:
            at = at_by_path.get(path, "")
            relative = path[len(at) + 1:] if at else path
            defining = types.get(from_type)
            default = (
                defining.parameters.get(relative, {}).get("default")
                if defining is not None
                else None
            )
            target = None
        rows.append(
            EntryRow(
                path=path,
                kind="entry",
                unit=spec["unit"],
                own=own,
                from_type=from_type,
                default=default,
                target=target,
            )
        )
    return rows


def instances_of_type(
    type_name: str,
    types: Mapping[str, PMTypeBluePrint],
    parameters: Mapping[str, str],
) -> List[str]:
    """Paths (relative to the Parameter Manager) of every Instance of the
    Type ``type_name``, computed client-side over the model's parameter
    rows (plan task 5.5; the mock's ``instancesOf``): the same candidate
    rules :func:`compute_claims` matches by — every proper dotted prefix,
    never the root, never anything under Globals — carrying every
    effective path with the declared unit (D12). An empty Type has no
    Instances. The Instances are sorted, for a stable pane order."""
    blueprint = types.get(type_name)
    if blueprint is None:
        return []
    effective = blueprint.effective
    if not effective:
        return []
    return [
        candidate
        for candidate in _instance_candidates(parameters)
        if _carries_effective_set(candidate, effective, parameters)
    ]


def also_types(
    instance: str,
    types: Mapping[str, PMTypeBluePrint],
    parameters: Mapping[str, str],
) -> List[str]:
    """Every Type the submodule ``instance`` is an Instance of (plan task
    5.5; the mock's ``also`` cell), in ``types`` order. The Types pane
    shows the ones besides the selected Type as ``also <t1>, <t2>``."""
    return [
        type_name
        for type_name in types
        if instance in instances_of_type(type_name, types, parameters)
    ]


def parse_default_text(text: str) -> Any:
    """The value a default line edit's text stands for: ``None`` when the
    text is empty, otherwise the text parsed with ``ast.literal_eval``,
    falling back to the raw string when it does not parse."""
    if text.strip() == "":
        return None
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


# ----------------- Client-side state --------------------------------------------------


class PMState:
    """Client-side cache of a Parameter Manager's Types and Locks.

    The Parameter Manager GUI owns one instance (``ParameterManagerGui.state``)
    so its widgets can react to Types and Locks without querying the Server
    again. It starts empty and is filled from the Parameter Manager — a Proxy
    Instrument or a local one — with :meth:`refresh`; the ``pm-lock-update``
    and ``pm-type-update`` Broadcasts then keep single entries current through
    :meth:`apply_lock` and :meth:`apply_type` (D22).

    ``types`` maps each Type's name to its :class:`PMTypeBluePrint`; ``locks``
    maps each Follower's path relative to the Parameter Manager — the form
    ``list_locks()`` returns — to its :class:`PMLockBluePrint`.
    """

    def __init__(self) -> None:
        self.types: Dict[str, PMTypeBluePrint] = {}
        self.locks: Dict[str, PMLockBluePrint] = {}

    def refresh(self, instrument: Any) -> None:
        """Re-read every Type and Lock from the Parameter Manager.

        Works with a Proxy Instrument and with a local Parameter Manager:
        both expose ``list_types``, ``get_type`` and ``list_locks``.

        :param instrument: the Parameter Manager whose Types and Locks to
            read.
        """
        self.types = {
            type_name: instrument.get_type(type_name)
            for type_name in instrument.list_types()
        }
        self.locks = dict(instrument.list_locks())

    def apply_lock(self, path: str, lock: Optional[PMLockBluePrint]) -> None:
        """Record the change a ``pm-lock-update`` Broadcast reports about
        the Follower at ``path``.

        :param path: the Follower's path relative to the Parameter Manager.
        :param lock: the Follower's :class:`PMLockBluePrint`, or ``None``
            when its Lock was removed (the entry is dropped then).
        """
        if lock is None:
            self.locks.pop(path, None)
        else:
            self.locks[path] = lock

    def apply_type(self, name: str, type_blueprint: Optional[PMTypeBluePrint]) -> None:
        """Record the change a ``pm-type-update`` Broadcast reports about
        the Type ``name``.

        :param name: the Type's name.
        :param type_blueprint: the Type's :class:`PMTypeBluePrint`, or
            ``None`` when the Type was removed (the entry is dropped then).
        """
        if type_blueprint is None:
            self.types.pop(name, None)
        else:
            self.types[name] = type_blueprint
