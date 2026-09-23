# Deferred type-cleanup: `InstrumentModelBase` parent/filter types

During the mypy sweep, roughly 10 `# type: ignore` comments were concentrated
around `InstrumentModelBase.addItem` / `insertItemTo` / `fillCollapsedDict` in
`src/instrumentserver/gui/base_instrument.py`. They are all symptoms of two
underlying design issues that are worth fixing properly rather than suppressing.

## Problem 1: mutable-default args + wrong Optional annotation

`InstrumentModelBase.__init__` (around line 195):

```python
def __init__(
    self,
    ...
    itemsStar: Optional[List[str]] = [],
    itemsTrash: Optional[List[str]] = [],
    itemsHide: Optional[List[str]] = [],
    ...
):
    ...
    self.itemsStar = itemsStar
    self.itemsTrash = itemsTrash
    self.itemsHide = itemsHide
```

Two bugs:

1. **Mutable default argument.** All callers that don't pass these kwargs share
   the *same* `[]` instance. If anyone ever mutates `self.itemsHide`, the change
   leaks into every subsequent instance. No test currently catches this.
2. **Wrong `Optional`.** The annotation says "could be `None`", but the default
   is `[]` and the consumer (`_matches_any_pattern`) requires `List[str]`. Mypy
   flags every use site as `arg-type` because it sees `List[str] | None`.

### Fix

```python
def __init__(
    self,
    ...
    itemsStar: Optional[List[str]] = None,
    itemsTrash: Optional[List[str]] = None,
    itemsHide: Optional[List[str]] = None,
    ...
):
    ...
    self.itemsStar: List[str] = itemsStar if itemsStar is not None else []
    self.itemsTrash: List[str] = itemsTrash if itemsTrash is not None else []
    self.itemsHide: List[str] = itemsHide if itemsHide is not None else []
```

The stored attributes are now `List[str]` (non-optional), so
`_matches_any_pattern(name, self.itemsHide)` type-checks without ignores.

## Problem 2: `parent` is overloaded to be either the model or an item

In `addItem` (around line 298):

```python
parent = self              # InstrumentModelBase (a QStandardItemModel)
for sm in path:
    ...
    if len(items) == 0:
        parent = subModItem    # ItemBase (a QStandardItem)
    else:
        parent = items[0]      # QStandardItem
```

`insertItemTo` declares `parent: QStandardItem`, but the root case passes
`self` (the model). Internally, `insertItemTo` already handles both:

```python
if parent == self:
    self.setItem(self.rowCount(), 0, item)
else:
    parent.appendRow(item)
```

So the signature is a lie — it actually accepts a union. Mypy flags:
- every reassignment of `parent` (`[assignment]`)
- every call to `insertItemTo(parent, ...)` (`[arg-type]`)
- the same pattern repeats in `fillCollapsedDict` when passing items through

### Fix

Make the signature honest:

```python
def insertItemTo(
    self,
    parent: Union["InstrumentModelBase", QtGui.QStandardItem],
    item: QtGui.QStandardItem,
) -> None:
    if parent == self:
        self.setItem(self.rowCount(), 0, item)
    else:
        assert isinstance(parent, QtGui.QStandardItem)
        parent.appendRow(item)
```

And in `addItem`, give `parent` an explicit union annotation:

```python
parent: Union["InstrumentModelBase", QtGui.QStandardItem] = self
```

All `[arg-type]` / `[assignment]` ignores on `addItem`, `insertItemTo`, and
`fillCollapsedDict` drop out.

## Problem 3: `Lock` vs `RLock` type clash in `_createInstrument`

In `src/instrumentserver/server/core.py` around lines 448-455:

```python
lock = self._get_lock_for_target(spec.name)      # Optional[threading.RLock]
if lock is None:
    lock = (
        self._instrument_locks_lock               # threading.Lock()  (line 189)
    )

with lock:
    ...
```

`_get_lock_for_target` returns `Optional[RLock]`, so mypy infers `lock` as
`RLock | None`. The fallback then reassigns `Lock` into it — `Lock` is not
`RLock` (they're separate classes in `threading`), so mypy flags
`[assignment]`. Because the `[assignment]` ignore suppresses the reassignment,
mypy never narrows out the `None`, so `with lock:` also needs
`[union-attr]`. Two ignores stack up on what is really one design issue.

### Fix

Change `_instrument_locks_lock` at line 189 to `RLock`:

```python
self._instrument_locks_lock = threading.RLock()
```

Then the fallback block becomes type-consistent, and we can simplify the
callsite to one line with an explicit annotation:

```python
lock: threading.RLock = (
    self._get_lock_for_target(spec.name) or self._instrument_locks_lock
)
with lock:
    ...
```

`RLock` is a strict superset of `Lock` (re-entrant from the same thread) and
`_instrument_locks_lock` is only acquired non-recursively at line 631, so the
swap is behavior-preserving. Both ignores drop out.

## Problem 4: `isinstance(obj, tuple(LIST_CONST))` defeats mypy narrowing

In `src/instrumentserver/server/core.py` around lines 518-529:

```python
obj = nestedAttributeFromString(self.station, path)   # returns Any
if isinstance(obj, tuple(INSTRUMENT_MODULE_BASE_CLASSES)):
    instrument_blueprint = bluePrintFromInstrumentModule(path, obj)  # arg-type error
elif isinstance(obj, tuple(PARAMETER_BASE_CLASSES)):
    parameter_blueprint = bluePrintFromParameter(path, obj)          # arg-type error
```

The constants are defined in `blueprints.py:74-77` as **lists**:

```python
INSTRUMENT_MODULE_BASE_CLASSES = [Instrument, InstrumentChannel, InstrumentBase]
PARAMETER_BASE_CLASSES = [Parameter, ParameterWithSetpoints]
```

`isinstance(x, tuple(some_list))` succeeds at runtime, but mypy cannot inspect
the elements of a runtime-constructed tuple. Result: `obj` does not narrow —
it stays as `object` — so passing it to `bluePrintFromInstrumentModule`
(which expects `Instrument | InstrumentChannel | InstrumentBase`) triggers
`[arg-type]`. Same story at the `PARAMETER_BASE_CLASSES` branch. Also occurs
in `blueprints.py:340` (`isinstance(o, tuple(PARAMETER_BASE_CLASSES))`) in
`bluePrintFromInstrumentModule` itself, though that site currently happens to
type-check because `o` is already `object`.

### Fix

Inline the class tuples as literals at the `isinstance` callsites so mypy can
narrow:

```python
# server/core.py
if isinstance(obj, (Instrument, InstrumentChannel, InstrumentBase)):
    # obj narrows to Instrument | InstrumentChannel | InstrumentBase
    instrument_blueprint = bluePrintFromInstrumentModule(path, obj)
    ...
elif isinstance(obj, (Parameter, ParameterWithSetpoints)):
    # obj narrows to Parameter | ParameterWithSetpoints
    parameter_blueprint = bluePrintFromParameter(path, obj)
    ...
```

The module-level `*_BASE_CLASSES` lists can remain — they're still used by
the blueprint-matching loops in `blueprints.py:123, 306` — but narrowing
callsites have to inline the tuple literal. If the lists are considered the
"source of truth" for which classes are instrument/parameter bases, this
creates a small duplication; acceptable trade-off for real type narrowing.

## Catalog of all `# type: ignore` ignores by pattern

The mypy sweep left **208 `# type: ignore` comments** across `src/`. Raw counts
by error code:

| code                         | count |
|------------------------------|-------|
| `union-attr`                 | 91    |
| `arg-type`                   | 48    |
| `attr-defined`               | 31    |
| `override`                   | 16    |
| `assignment`                 | 7     |
| `type-var`                   | 3     |
| `misc`                       | 2     |
| `call-overload`              | 2     |
| `operator`                   | 1 (+1 combined) |
| `return-value`               | 1     |
| `no-untyped-def`             | 1     |
| `method-assign`              | 1     |
| `import-not-found`           | 1     |
| `assignment,method-assign`   | 1     |

Grouped by root cause:

### Bucket A — Qt event-handler `[override]` (16 ignores)

PyQt5 stubs declare event args as `QEvent | None`; our overrides use
`QEvent`. Same fix pattern for all of them.

**Sites:** `gui/misc.py:38, 42, 77, 98, 108, 112, 156, 165, 169`;
`gui/instruments.py:795`; `client/application.py:373`;
`client/proxy.py:276` (`add_parameter` override, different class);
`gui/instruments.py:260, 458, 683` (`createEditor` override);
`params.py:203` (`add_parameter` LSP violation).

**Fix (event handlers):** change signature to `Optional[QEvent]`. Most bodies
immediately use the event, so add an `if a0 is None: return super().foo(a0)`
guard or `assert a0 is not None`. Accept that `assert` technically changes
behavior under `-O`; if acceptable, ignores drop.

**Fix (`add_parameter`/`createEditor` LSP):** these override qcodes/Qt
signatures with incompatible types. Leaving `# type: ignore[override]` is
the pragmatic choice — fixing properly would require wider refactors in
qcodes/Qt inheritance.

### Bucket B — PyQt5 "Optional return" widget/item stubs (~70 `union-attr`)

PyQt5's stubs conservatively mark many widget-returning methods as
`Optional` (e.g. `QMainWindow.addToolBar()` → `QToolBar | None`,
`QTreeView.header()` → `QHeaderView | None`, `QApplication.primaryScreen()`
→ `QScreen | None`, `QStandardItemModel.itemFromIndex()` →
`QStandardItem | None`, `QAbstractProxyModel.sourceModel()` →
`QAbstractItemModel | None`, `QWidget.parentWidget()` → `QWidget | None`,
`QTabWidget.widget(i)` → `QWidget | None`, `QTreeWidgetItem.parent()` →
`QTreeWidgetItem | None`, `QTextEdit.verticalScrollBar()` → `QScrollBar |
None`). At runtime they are never None in this codebase.

**Sites (bulk):** `gui/base_instrument.py:152, 153, 554, 555, 614, 619, 620,
624, 627, 630, 645-671 (many), 689, 691, 694, 695, 704, 706, 832, 840, 846,
853, 854, 859, 860`; `gui/misc.py:127, 158, 160, 206, 244, 257`;
`gui/instruments.py:517, 592, 598, 696`; `gui/__init__.py` (none now);
`client/application.py:172, 246, 248, 342, 344`; `log.py:53, 54`;
`server/application.py:417, 418, 423, 424, 647, 650, 655, 658, 659, 665,
671, 712, 738, 876, 936, 939, 944`.

**Fix:** assign the nullable return to a local, assert/narrow once:

```python
toolbar = self.addToolBar("Tools")
assert toolbar is not None
toolbar.setIconSize(...)   # no ignore needed
toolbar.addAction(...)
```

Tedious but eliminates the single biggest bucket. Same pattern applies to
`header()`, `verticalScrollBar()`, `parentWidget()`, `sourceModel()`, etc.

### Bucket C — Qt int-flag OR → `int` `[arg-type]` / `[call-overload]`

`Qt.AlignmentFlag(int)` has no `__or__` overload in stubs, so
`AlignRight | AlignVCenter` evaluates to `int`, but
`setAlignment(Alignment | AlignmentFlag)` refuses `int`. Same story for
`MatchFlag`, `DropAction`, `QIODevice.OpenModeFlag`.

**Sites:** `gui/misc.py:14, 135`; `gui/instruments.py:56, 62, 68, 83, 97,
338`; `gui/base_instrument.py:315, 347`; `server/application.py:75, 357`;
`client/application.py:41`; `gui/__init__.py:9`.

**Fix:** wrap with the Flags constructor:

```python
from PyQt5.QtCore import Qt
flags = Qt.Alignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
label.setAlignment(flags)
```

Project-wide decision: adopt this wrapping consistently, or leave the
ignores. Uniform wrapping reads slightly worse but removes ~15 ignores.

### Bucket D — PyQt5 Signal `connect(Callable[..., bool])` `[arg-type]`

`pyqtBoundSignal.connect` expects `Callable[..., None]`. Our callbacks that
return `bool` (startServer, SubClient.connect, Listener.connect) trigger
this.

**Sites:** `gui/instruments.py:306`; `client/application.py:129`;
`server/application.py:719` (part of `[arg-type,attr-defined]`);
`server/core.py:668`; `server/application.py:63, 322` (lambda returning
`QAction | None`).

**Fix:** wrap in a discarding lambda, e.g.
`thread.started.connect(lambda: server.startServer())`. Verbose;
arguably the ignore is fine.

### Bucket E — `stationServer`/`stationServerThread` as `Optional` in `ServerGui`

`ServerGui.__init__` sets `self.stationServer = None` /
`self.stationServerThread = None` before `startServer()` creates them. Every
downstream access in `startServer`, `_messageReceived`, `addInstrumentTab`,
`getServerIfRunning` is `union-attr`/`attr-defined`.

**Sites:** `server/application.py:716, 717, 718, 719, 720, 721, 722, 725,
726, 727, 728, 731, 732, 733, 735, 738, 876`.

**Fix:** don't initialize to `None`. Either
(a) construct `StationServer`/`QThread` eagerly in `__init__`, or
(b) introduce a typed container that is populated in `startServer` and
narrow via a helper method (e.g. `_require_server() -> StationServer`).
Option (b) removes 17 ignores in one class.

### Bucket F — `self.cli: Optional[Client]` in `ProxyMixin`/`ProxyInstrumentModule`

`ProxyMixin.__init__` takes `cli: Optional[Client] = None`. In
`ProxyInstrumentModule.__init__` there's a fallback `if cli is None:
self.cli = Client(...)`, but mypy doesn't track that post-init `self.cli`
is no longer `None`.

**Sites:** `client/proxy.py:223, 257, 258, 428` (plus lines 276, 396, 420
in adjacent buckets).

**Fix:** split the declared types. `ProxyMixin.cli: Optional[Client]`
stays, but `ProxyInstrumentModule.cli: Client` can be redeclared (the
subclass guarantees initialization). Or store `self._cli: Client` and
provide a property that enforces the narrowing.

### Bucket G — `QStandardItem | None` vs our `ItemBase` subclass (16 `attr-defined` + several `union-attr`)

Items returned by `findItems`, `parent.child`, `itemFromIndex`, etc. are
typed `QStandardItem | None` by Qt stubs, but we always populate them with
`ItemBase`. Accessing `item.element`, `item.name`, `item.star`, `item.trash`
triggers `attr-defined`.

**Sites:** `gui/instruments.py:270, 273, 365, 366, 465, 466, 469, 690, 691,
698`; `gui/base_instrument.py:894, 896, 897, 899, 900`;
`server/application.py:400, 401, 403, 415, 416`.

**Fix:** `typing.cast(ItemBase, item)` at the boundary where we retrieve
from Qt, then all downstream access is clean. Removes ~20 ignores.

### Bucket H — Already-documented structural issues

Cross-references to earlier sections:

- **Problem 1** (`itemsHide`/`itemsStar`/`itemsTrash` mutable-default +
  wrong `Optional`): `base_instrument.py:261, 265, 267, 328, 330, 332`;
  `gui/instruments.py:341`.
- **Problem 2** (`parent` union in `addItem`): `base_instrument.py:329,
  335, 336, 338, 341, 456, 479, 593, 605`.
- **Problem 3** (`Lock` vs `RLock`): `server/core.py:452, 455`.
- **Problem 4** (`isinstance(obj, tuple(list_var))`): `server/core.py:519,
  526`.

### Bucket I — qcodes `TSubmodule` TypeVar constraint (3 `type-var`)

qcodes's `InstrumentBase.add_submodule` has a TypeVar bound that rejects
our `ProxyInstrumentModule` and `ParameterManager` subclasses.

**Sites:** `client/proxy.py:396, 420`; `params.py:190`.

**Fix:** upstream qcodes would need to loosen the bound. Leave the
ignores; note in upstream bug tracker if desired.

### Bucket J — `self.layout` attribute shadows `QWidget.layout()` method (1 combined)

`ServerStatus.__init__` does `self.layout = QtWidgets.QVBoxLayout(self)`,
which mypy flags as overwriting the `layout()` method on QWidget (hence
`[assignment,method-assign]` at line 127 and `[attr-defined]` on every
subsequent `self.layout.addLayout/addWidget`).

**Sites:** `server/application.py:127, 141, 144, 147`.

**Fix:** rename to `self._layout` (consistent with convention elsewhere in
this codebase). Drops 4 ignores.

### Bucket K — `pollingRates: Optional[Dict]` always-present-at-runtime

Same pattern as `itemsHide`: `PollingWorker.pollingRates: Optional[Dict]`,
but methods dereference it unconditionally.

**Sites:** `server/pollingWorker.py:40, 45, 49, 53, 56`.

**Fix:** store as `Dict[str, int]` with `{}` default, or guard the top of
`run()` with `if self.pollingRates is None: return`.

### Bucket L — `self.client: Client` reassigned to `None` on disconnect (1)

`ClientStation.disconnect` sets `self.client = None`, but
`self.client: Client` was declared non-Optional. Fix: declare as
`Optional[Client]` and narrow at use sites, or don't null it out on
disconnect.

**Site:** `client/proxy.py:912`.

### Bucket M — `send(self.socket, ...)` / `recv(self.socket)` (2)

`BaseClient.socket: Optional[zmq.Socket]`. Inside `ask()`, the `connected`
flag guarantees non-None but mypy doesn't know that.

**Sites:** `client/core.py:96, 97`.

**Fix:** early `assert self.socket is not None` at the start of `ask()`.

### Bucket N — Misc small issues

- `client/proxy.py:232` — `self.remove_parameter = MethodType(...)`: Python
  lets us, mypy doesn't. `[method-assign]`. Leave it; it's an intentional
  monkey-patch.
- `client/proxy.py:385` — `return globs[bp.name]`: `globs` is
  `Dict[str, Any]`, but the function dict-lookup returns `object`. Fix
  with `cast(Callable, globs[bp.name])`.
- `client/proxy.py:608` — `self.getParamDict(instrument=name, *args)`:
  positional-after-keyword potential. `[misc]`. Low priority.
- `client/proxy.py:1027` — `file_path: str | None` passed to
  `paramsToFile(str)`. Fix: narrow before calling.
- `blueprints.py:285, 289, 293` — `self.parameters.items()` on
  `Optional[Dict]`. Same fix pattern as Bucket K.
- `blueprints.py:382` — `self.bp_type`: **real bug**, attribute doesn't
  exist on `ParameterBroadcastBluePrint`. Flagged in the earlier summary.
  Fix: remove the reference in `pprint`, or add the attribute.
- `serialize.py:285` — submodule iteration typed loosely; similar to
  Bucket H Problem-4 pattern.
- `server/core.py:579, 582, 602, 608, 668` — broadcast socket and
  `spec.args` Optionals (same Optional-narrow-at-use pattern).
- `params.py:96` (`getWorkingDirectory` `[no-untyped-def]`) — intentional;
  annotating breaks the proxy `exec()` signature rendering (see earlier
  note in this file).
- `params.py:193, 257, 258` — qcodes submodule typing mismatches; same
  family as Bucket I.
- `server/application.py:565` (`[misc]`) — similar to proxy.py:608.
- `server/application.py:712` (`event.accept()` on `Optional`) — add
  early-return for `event is None`.
- `server/application.py:846` (`setObject(bp)` with `bp` possibly None) —
  change `setObject` signature to `Optional[...]` and guard inside.
- `gui/__init__.py:9` — `QFile.open(flags)` where flags is `int` from
  enum OR (Bucket C).
- `gui/misc.py:217` — `DetachedTab(widget, name, parent=self)` where
  `widget` is `Optional`. Narrow with assertion.
- `monitoring/listener.py:16` — `influxdb_client` import not found. This
  is an optional dependency; `[import-not-found]` is correct — the
  `try/except ImportError` handles runtime.

## Priority if tackling

1. **High value, low risk:** Buckets G (cast ItemBase, −20), J (rename
   `self.layout`, −4), M (assert socket, −2). Plus Problems 1–4 already
   spec'd.
2. **Medium value, some refactor:** Buckets E (require-helper for
   stationServer, −17), F (declare `ProxyInstrumentModule.cli: Client`,
   −4), B (narrow-once locals for widget returns, ~−70).
3. **Low value / project-style decisions:** Buckets A (event handler
   Optional args), C (Flags constructor wrapping), D (wrap connect
   callbacks).
4. **Will not go away:** Bucket I (qcodes upstream), the handful of
   intentional ignores (`[method-assign]`, `[import-not-found]`,
   `[no-untyped-def]`).

Full elimination target: **208 → ~30 ignores** after all of (1) + (2) +
Problems 1–4 are applied.

## Related PyQt5 stub workaround (cannot be cleaned up)

`findItems(name, MatchFlag | MatchFlag, 0)` requires one more ignore that will
*not* go away: PyQt5's stubs declare `MatchFlag(int)` without an `__or__`
override, so `MatchFlag | MatchFlag` resolves to `int`, but `findItems`
expects `MatchFlags | MatchFlag`. Either leave the `# type: ignore[arg-type]`
or wrap flags explicitly:

```python
from PyQt5.QtCore import Qt
flags = Qt.MatchFlags(
    Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive
)
items = self.findItems(smName, flags, 0)
```

Same pattern exists in `gui/instruments.py` and `server/application.py` around
`findItems` and `setAlignment` calls. Worth deciding on a project-wide approach.

## Test gap before refactoring

Nothing in `test/pytest/` directly exercises:

- `InstrumentModelBase.addItem` / `insertItemTo` (covered only transitively
  via `test_server_gui.py::test_opening_new_tab_generic_object`, and only for
  an instrument with submodules).
- The `itemsHide` / `itemsStar` / `itemsTrash` filter branches (no test
  passes these kwargs).
- `fillCollapsedDict` / `restoreCollapsedDict` (only fire on the filter
  textbox signals, which no test triggers).

Before doing the refactor, it is worth adding two small unit tests:

1. Construct `InstrumentParameters` with `parameters-hide=["some_pattern"]`
   and assert the matching parameter is not present in the model.
2. Create two `ModelParameters` instances with no `itemsStar` kwarg and
   assert `m1.itemsStar is not m2.itemsStar` (guards the mutable-default fix).

## Summary

Two root causes produce roughly 10 `# type: ignore` comments. Fixing them:
- removes one latent bug (shared mutable default list),
- drops ignores in `base_instrument.py` and cascades cleanup into
  `gui/instruments.py` (`fillCollapsedDict` callers) and any caller of
  `insertItemTo`,
- needs two small unit tests added first to protect the filter-branch and
  mutable-default behavior that currently has no coverage.
