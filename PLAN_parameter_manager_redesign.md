# Parameter Manager Redesign — Master Plan (Types and Locks)

This is the guiding document for adding **Types** and **Locks** to the Parameter Manager and
rebuilding its GUI around them. It records the goal, every decision taken in the design
interview of 2026-09-16, the way of working, and a phase-by-phase task list sized so that
one task fits one agent session. It is a living document: statuses are updated as work
progresses.

Companion files (read all of them before starting any task):

- `CONTEXT.md` — the canonical glossary. Use its terms exactly (Type, Instance, Nested Type,
  Lock, Target, Follower, Type Lock, Globals, Parameter Group, Broadcaster, instrument mutex).
- `docs/adr/0001-duck-typed-parameter-manager-types.md`
- `docs/adr/0002-pull-based-locks.md`
- `docs/adr/0003-broadcaster-contract.md`
- The Claude Design mock: `https://claude.ai/design/p/1603bddf-2dee-49a1-bf02-14c4e1c430d7`
  (exported copy: `/Users/marcosf2/Downloads/Parameter Manager Redesign Features/`;
  the file `ParameterManager.dc.html` holds the markup and, at its end, the full logic).
  The mock is a **web** prototype; the product is **PyQt**. Section "Design reference" below
  translates it.

---

## How to use this document (session protocol)

Each work session starts fresh from this document.

1. Read this file top to bottom, then `CONTEXT.md`, then the three ADRs.
2. Find the next open task: the first non-`[x]` checkbox in phase order, unless Marcos names
   a different target. Do **one task** per session unless it is trivially small.
3. Before editing any function or class, run a **grep-based caller check**: search the
   whole `src/` and `test/` tree for the symbol name and read every call site. Report what you
   found in your first message. Do **not** use GitNexus (MCP or CLI): it is broken in this
   project. The GitNexus rules in `CLAUDE.md` are suspended for this plan.
4. Implement with tests. Every task below names the test file(s) it must leave green. Run
   `uv run pytest test/pytest/<file>` for the named files, then `uv run pytest` for the whole
   suite, before declaring a task done. Paste the summary line of the run.
5. Mark the checkbox `[~]` when you start and `[x]` when tests pass and you have reported.
   If you stop mid-task, leave `[~]` and write a short "handover" note under the task.
6. **Commit atomic units of work; never push.** All commits go on branch
   `marcosfrenkel/new-param-manager`. The coder commits code and tests, and only when the
   task's named tests pass. The first implementation of a task is one commit; each round
   of review fixes is its own commit. The orchestrator commits only the task's section in
   `HISTORY_parameter_manager_redesign.md` (written by the historian agent from the
   reviews and decision log, which stay in the git-ignored `orchestration/` folder) and
   this file's checkboxes; reviewers never commit.
   Every commit message starts with the task number (`0.1: split ParameterGroup out of
   ParameterManager`). Never amend, squash, rebase or push: Marcos reads the history
   commit by commit afterwards.
7. Update `CONTEXT.md` the moment a term is added or changed. Update this file when a
   decision has to be revisited (add a dated note under "Decision record", never silently
   change a decision).

Status markers: `[ ]` not started · `[~]` in progress · `[x]` done and reported.

---

## Goal

Give the Parameter Manager two new features, controllable from Python clients and from
its Qt GUI alike, with GUIs updating live when another client changes something:

- **Types**: a Type is a named shape (relative parameter paths with defaults and units, plus
  Nested Types). Any submodule carrying that shape is an Instance. Adding an entry to a Type
  writes it into every Instance; the GUI tints rows by their claiming Type.
- **Locks**: a parameter can have a Lock naming another parameter as its Target. While locked
  it reads the Target's value and refuses writes. A Type Lock declares this on a Type entry so
  every Instance follows one Target, by default a parameter under `_globals`.

## Why

- Multi-qubit devices repeat the same structure per qubit; today each copy is edited by hand
  and drifts. Types make the structure explicit and keep copies complete.
- Shared settings (an LO frequency, a readout bandwidth) are duplicated across qubits; Locks
  make one parameter authoritative without copying values around.
- Everything must work from measurement code, not only from the GUI, so the features are
  instrument methods first and widgets second.

## Non-goals (out of scope for this plan)

- Value kinds / validators over the wire (`ParameterTypes`, the disabled type combo in
  `AddParameterWidget`, `vals` in blueprints). Left exactly as is.
- Locks whose Target lives outside the same Parameter Manager (other instruments).
- The design's "offer bar" (lock the others too / make it a type rule) and Ctrl/Shift
  multi-select batch locking. Single-parameter lock flow only.
- Dark theme.
- Renaming or changing the server's `_instrument_locks` (the instrument mutex). Add a
  comment only.
- `TODO_type_cleanup.md` items and the dead `_refreshProxySubmodules` in `client/proxy.py`.

---

## Way of working — rules every task follows

1. **Atomic commits, no pushes.** See session protocol step 6. Reviewers never edit code
   or commit; they write only their own report file.
2. **Glossary terms only**, in code comments, docstrings, test names, log messages and GUI
   strings. If you need a word the glossary lacks, stop and ask.
3. **Validate, then mutate.** Every Parameter Manager method that changes state checks all
   its preconditions first and raises before touching anything. No partial state on error.
   Error messages name the offending paths (all of them, not the first).
4. **Names are strings.** Client-facing methods take and return dotted paths relative to the
   Parameter Manager (`"q01.readout.IF"`), never parameter objects. Paths stored in files use
   the full form with the instrument name, as the existing files do
   (`"parameter_manager.q01.readout.IF"`).
5. **Tests per layer** (see "Testing"): unit tests without a server for all logic; proxy
   tests for every client-facing method and broadcast; pytest-qt tests for GUI behaviour.
6. **Do not widen scope.** Pre-existing defects not listed in Phase 0 are noted in
   `TEST_AUDIT.md`, not fixed.
7. **Do not break the existing API.** `add_parameter`, `remove_parameter`, `list`, `get`,
   `set`, `has_param`, `parameter`, `toFile`, `fromFile`, `switch_to_profile`,
   `refresh_profiles`, `list_profiles`, `to_tree`, `remove_all_parameters`,
   `remove_empty_submodules` keep their signatures and behaviour (except where a decision
   below explicitly changes them).
8. **Casing**: the code base mixes `snake_case` (`add_parameter`) and `camelCase`
   (`toFile`). New methods are `snake_case`. New classes are `CamelCase` with the existing
   `BluePrint` spelling for blueprint dataclasses.
9. **Docs pages** (Phase 6) follow the docs protocol in `PLAN_docs_refactor.md`: nothing
   is documented without a verification script under `test/docs_verification/`, and the
   site must build clean (`cd docs && uv run make clean && uv run make html`, zero warnings).

---

## Current architecture — facts an agent must know (verified 2026-09-16)

Package lives under `src/instrumentserver/`.

**Parameter Manager** (`params.py`): `ParameterManager(InstrumentBase)`. `add_parameter`
forces `parameter_class=Parameter`, `set_cmd=None`, default `vals=Anything()`, and creates
missing submodules via `_get_parent(..., create_parent=True)`, which today instantiates a
**full `ParameterManager`** per submodule (`params.py:189`). Each such constructor calls
`refresh_profiles()` (lists the working directory) and `fromFile()` (tries to load
`parameter_manager-<submodule>.json`). Persistence: `toFile` → `toParamDict` →
`serialize.toParamDict([self], includeMeta=["unit"])`, which reads the **qcodes snapshot with
`update=False`** (cache, never `get`). `fromFile` → `fromParamDict`. Profile files are
`parameter_manager-<profile>.json`, a flat map `{"<instrument>.<path>": {"unit", "value"}}`.
`switch_to_profile` saves the current profile, `remove_all_parameters()`, loads the new one.

**Server** (`server/core.py`): `_callObject` (:469) resolves the dotted target with
`nestedAttributeFromString(self.station, target)`, takes the per-instrument `RLock`
(`_get_lock_for_target`, :616), calls the object, and **broadcasts only**: `parameter-update`
(set), `parameter-call` (get), and via `_newOrDeleteParameterDetection` (:593)
`parameter-creation` / `parameter-deletion` when the called method is literally named
`add_parameter` / `remove_parameter` (it reads `kwargs["initial_value"]` and
`kwargs["unit"]` unconditionally: a latent `KeyError`). Any other method call broadcasts
nothing. `_broadcastParameterChange` (:570) calls `sendBroadcast(socket, topic=instrument
name, blueprint)`, on the worker thread. Instruments enter the Station in two places:
`_createInstrument` (:461, `self.station.add_component`) and at startup from the station
config (`self.station.load_instrument`, :146).

**Blueprints** (`blueprints.py`): `ParameterBroadcastBluePrint(name, action, value, unit)`
(:356). `bluePrintToDict` (:415) serialises dataclasses field by field; `deserialize_obj`
(:929) rebuilds any dict with a `_class_type` key by evaluating that class name **in the
`blueprints` module namespace**, so new blueprint dataclasses must be defined there and carry
`_class_type`. `ParameterBluePrint` has no `vals`.

**Client / proxy** (`client/proxy.py`): `ProxyInstrumentModule.update()` (:256) is the only
structural refresh; `Client.getBluePrint` caches (:539) and only `update()` invalidates.
Methods of the instrument are proxied generically from `MethodBluePrint`, so **any new public
method on `ParameterManager` is callable from clients with no client changes**, and its
return value must be JSON-serialisable by `ServerResponse` (dataclass blueprints are).
`SubClient` (:669) is the ZMQ SUB listener emitting `update(ParameterBroadcastBluePrint)`.

**GUI** (`gui/instruments.py`, `gui/base_instrument.py`, `gui/parameters.py`):
`ParameterManagerGui(InstrumentParameters)` (:747) = `ProfilesManager` combo +
`ParameterManagerTreeView` (`QTreeView`, delegate column 2 holds a `ParameterWidget` with a
red delete button per row) + `AddParameterWidget` strip. Model `ModelParameters`
(`QStandardItemModel`, columns `[name, unit, delegate]`) owns a `SubClient` on a `QThread`
and handles broadcasts in `updateParameter` (:441): creation → `instrument.update()` +
`addItem`; deletion → `removeItem`; update/call → `itemNewValue` signal.
`ParameterManagerTreeView.onItemNewValue` (:705) calls `widget.paramWidget.setValue`, which
only `AnyInput`/`NumberInput` implement (the generic tree uses `widget._setMethod`).
Launcher `apps.py:parameterManagerScript` (:123) builds `Client(port)` and
`ParameterManagerGui(pm)` **without** `sub_port`, so the GUI listens on `localhost:5556`
regardless of `--port`.

**Tests** (`test/pytest/`): `conftest.py` starts one server per module on port 5555
(`start_server`), `cli`, `param_manager` fixtures. `test_param_manager.py` is mostly local
(no server) and asserts the flat file shape (`data["params.my_param"]["value"]`).
`test_gui_navigation.py` is the pytest-qt pattern (`qtbot`, server on port 5599).
`pyproject.toml` has `pytest-qt`, `qt_api = "pyqt5"`.

---

## Decision record

Numbered as taken in the interview. Each is final unless a dated note below it says otherwise.

**D1 — Types are duck-typed.** A submodule is an Instance because it carries the shape.
Nothing stores membership. (ADR-0001.)

**D2 — Vocabulary.** "Type" is the structural concept; the `ParameterTypes` enum is a
"value kind" in prose. "Lock" is the user-facing concept; the server RLock is the
"instrument mutex" in prose, code unchanged. Full definitions in `CONTEXT.md`.

**D3 — Locks pull on `get`.** A locked Follower asks its Target. `set` on a locked Follower
**raises** `ValueError` naming the Target. The Target knows nothing. Unlocking exposes the
Follower's own underlying value (no copying on unlock). Followers are computed by scanning.
(ADR-0002.)

**D4 — Broadcaster contract.** A `Broadcaster` mixin (`add_broadcast_sink`,
`remove_broadcast_sink`, `broadcast`); the server registers itself as a sink when an
instrument with the mixin joins the Station. (ADR-0003.)

**D5 — Three Lock states**: no Lock; Lock present and **unlocked** (Target remembered); Lock
present and **locked**.

**D6 — `set` on a locked Follower raises.** No redirect, no silent ignore.

**D7 — Chains allowed, cycles refused.** Each hop reads according to its own state (if `q02.x`
is unlocked, `q03.x` locked to it reads `q02.x`'s own value). Cycle detection walks Targets
regardless of locked/unlocked state. No self-lock.

**D8 — Targets only inside the same Parameter Manager.**

**D9 — Lock API**: `lock(name, target)` (creates or re-targets, sets locked),
`unlock(name)`, `relock(name)`, `toggle_lock(name)`, `remove_lock(name)`,
`get_lock(name) -> PMLockBluePrint | None`, `list_locks() -> dict[str, PMLockBluePrint]`,
`followers_of(name) -> list[str]`.

**D10 — `pm-lock-update` broadcast**, one per affected Follower, `name` = full Follower path,
`value` = `PMLockBluePrint(target, locked)` or `None` when removed. Emitted by every Lock
method and by `remove_parameter` when deleting a Target drops Locks. Action strings stay
strings; module-level constants for all actions.

**D11 — Type definition** = name; entries (relative path, default value, unit); Nested Types
(`add_nested_type(type, submodule, nested_type)`). No value kind, no description.

**D12 — Instance matching**: every submodule at any depth, never the root, never under
`_globals`; a match requires every effective path to exist **with the declared unit**; values
irrelevant; an empty Type has no Instances; computed on demand, no cache.

**D13 — Type edits and Instances**: add entry → create in every Instance lacking it with
default and unit; remove entry → nothing; change default → nothing; change unit →
**propagate** to every Instance (API only; no GUI unit editor); add Nested Type → like adding
its entries under the submodule; remove Nested Type → nothing; delete Type → nothing on
parameters.

**D14 — `add_instance(type, name)`**: creates missing effective entries with defaults; keeps
existing ones; dotted names allowed (nested Instances); refuses `_globals`; a unit conflict on
any existing parameter raises **before anything is created**.

**D15 — One Type registry on the root.** Submodules become `ParameterGroup` (plain
containers: parameters, nested groups, tree helpers; no files, profiles, Types, Locks).
`ParameterManager` extends `ParameterGroup` with those responsibilities. Every submodule is
a `ParameterGroup`.

**D16 — Type API**: `add_type(name)`, `remove_type(name)` (raises if nested in another
Type), `add_type_parameter(type, path, default=None, unit="")`,
`remove_type_parameter(type, path)`, `set_type_parameter_default(type, path, value)`,
`set_type_parameter_unit(type, path, unit)`, `add_nested_type(type, submodule, nested_type)`,
`remove_nested_type(type, submodule)`, `list_types()`, `get_type(name) -> PMTypeBluePrint`,
`instances_of(type)`, `types_of(path)` (innermost first, then largest), `add_instance`.

**D17 — Type Lock**: `lock_type_parameter(type, path, target=None)` stores the Target on the
entry, creates `_globals.<type>.<path>` (entry default and unit) when no target is given,
and puts an ordinary locked Lock on that parameter in every current Instance; new Instances
(via `add_instance` or an `add_type_parameter` that completes them) get it at creation.
Instance parameters that **already have a Lock on another Target are skipped**; the method
returns the skipped paths and logs a warning. `unlock_type_parameter(type, path)` removes
**only the rule**; the Locks it created stay (the Locks panel removes them individually).
Individual Followers may be unlocked/relocked freely. Instances that stop matching keep their
Locks. Declaring again re-applies to everyone ("lock all").

**D18 — `_globals`**: created on demand; never an Instance; excluded from matching;
`add_parameter`/`add_instance` under it raise; its parameters are otherwise ordinary (set,
read, saved, may themselves have a Lock); `remove_parameter` on one is allowed and removes
the Locks and the Type Lock rule pointing at it; `_globals` is not a valid Type name.
GUI (Phase 5): deleting any Target asks for confirmation listing the Locks that will vanish.

**D19 — File format version 2**, one file per profile:
```json
{
  "version": 2,
  "parameters": {
    "parameter_manager.q01.IF": {"unit": "Hz", "value": 101735237.0,
                                  "lock": {"target": "parameter_manager.q01Data.IF", "locked": true}}
  },
  "types": {
    "qubit": {
      "parameters": {"IF": {"default": null, "unit": "Hz", "target": null},
                     "octave_gain": {"default": 10, "unit": "dB", "target": "parameter_manager._globals.qubit.octave_gain"}},
      "nested": {"readout": "readout"}
    }
  }
}
```
Stored `value` is the parameter's **own** value. `lock` is present only on Followers. A file
without a top-level `version` key is the legacy flat map and loads as parameters only.
Saving always writes version 2.

**D20 — Load order and validation**: the whole file is validated first (every Lock Target
and every Type Lock Target must exist in the file; otherwise raise **listing all missing
Targets**, leaving current state untouched). Then parameters (with existing `deleteMissing`
semantics), then Type definitions **without Instance side effects**, then Locks.
`switch_to_profile` saves the current profile, then clears parameters, Types and Locks, then
loads.

**D21 — GUI scope**: extend the existing `ParameterManagerGui`; ship tab bar, tints and
gutter bands, lock column and per-row toggle, context menu Lock to…/Unlock, arm strip, Locks
panel, delete-Target confirmation, Types tab, Follower repaint on Target update. Defer offer
bar and multi-select. No dark theme.

**D22 — Live structural updates**: the Parameter Manager re-emits `parameter-creation` /
`parameter-deletion` for parameters it creates/removes as side effects, and emits
`pm-type-update` (`name` = `<instrument>.<type>`, `value` = `PMTypeBluePrint` or `None`)
from every Type-editing method, including `lock_type_parameter`/`unlock_type_parameter`.
GUIs replace that one Type locally and recompute tints; no follow-up fetch.

**D23 — Testing layers and files**: see "Testing".

**D24 — Pre-existing fixes in scope**: `.get()` in `_newOrDeleteParameterDetection`;
`sub_port = port + 1` in `apps.py`; align `ParameterManagerTreeView.onItemNewValue` with the
generic `_setMethod` path. Everything else listed under Non-goals.

**D25 — Docs in scope**: this plan writes the User Guide Parameter Manager page and the
Technical Guide Broadcasts page (with the Broadcaster contract) as Phase 6, then updates
`PLAN_docs_refactor.md`.

**D26 — Names**: actions `pm-lock-update`, `pm-type-update`; classes `PMLockBluePrint`,
`PMTypeBluePrint`; parameter class `ManagedParameter`; container class `ParameterGroup`;
mixin `Broadcaster`.

**D27 — Per-run test ports (added 2026-09-23).** Several agents run the suite at the same
time, and the tests' fixed ports (5555/5556, 5599) made those runs collide. Task 0.0 gives
every pytest session its own free port pair through a `server_port` fixture, and
`AGENTS.md` tells every agent to use it. This widens scope beyond D24 on purpose; it
touches only `test/` and `AGENTS.md`.

---

## Design reference — translating the mock to Qt

The mock's state, and what it becomes:

| Mock | Ours |
|---|---|
| `params[path] = {unit, value, lockedTo, prevLock}` | a `ManagedParameter`: own value in the cache, `lock` = (target, locked) or `None`. `prevLock` ≡ Lock present but unlocked. |
| `templates[type] = {params:[{name, unit, value, lockedTo}], includes:[{type, at}]}` | `PMTypeBluePrint`: `name`, `parameters: {path: {default, unit, target}}`, `nested: {submodule: type}`, plus the computed `effective: {path: {unit, from_type}}`. |
| `instancesOf(type)` | `instances_of(type)` (server side; the GUI calls it or recomputes from `PMTypeBluePrint` + the tree). |
| `claims()` (innermost type wins, then size; stack for gutter bands) | `types_of(path)` server side; the GUI ports `claims()` to compute tint + up to 3 gutter bands per row. |
| `lockOk(follower, source)` | cycle/self check inside `lock()`; walks Targets regardless of state. |
| `root(path)` / `valueOf(path)` | `ManagedParameter.get()` chain walk, hop by hop. |
| `toggleLock` | `toggle_lock`; with no Lock present the GUI arms the picker. |
| `deleteLock` | `remove_lock`. |
| `lockTypeParam` / `unlockTypeParam` / `armTypeLock` | `lock_type_parameter(type, path[, target])` / `unlock_type_parameter` / GUI arm then `lock_type_parameter(..., target=picked)`. |
| `offerFor` / `lockOthers` | deferred. |
| `_globals.<type>.<rel>` created on demand | identical. |
| `doAddInstance` (creates params, auto-locks per type rule) | `add_instance`. |
| `TINTS` (5 light tints + bar colours) | a fixed palette of 5 `QColor` pairs assigned in Type creation order; recycle when exhausted. Row background via the model's `BackgroundRole`; gutter band drawn by a small item delegate on column 0 or a dedicated 10 px column. |
| Lock column text: `locked to <target>` / `target ×N` | a new model column between unit and the delegate column. |
| Arm strip (label + completer + Cancel) | a `QWidget` row shown under the toolbar while arming: `QLabel`, `QLineEdit` with a `QCompleter` over all paths ranked like the mock (same relative path first), Cancel. Clicking a tree row while armed picks it. |
| Locks panel | a second `QTreeView` in a `QSplitter`, toggled by a toolbar action. Rows: Targets at depth 0, Followers beneath; Type Lock group rows first, labelled `[type: qubit] <target>`. Per-row: lock/relock toggle, remove; value editor on Targets. |
| Types tab | a `QTabWidget` around the existing widget: tab 0 = existing Parameters view, tab 1 = Types view with three panes (type list + New type; entries + Add to type + nested type strip; instances + New instance). |

Mock strings worth keeping verbatim (they follow the design system's voice): tooltips
"locked to X — unlock and go back to its own value", "unlocked — lock to X again",
"lock to… — then pick a source" (say **target**), "remove from the type only — instances keep
the parameter and lose the type fill", "Instances are derived: any submodule carrying the
whole set…". Replace every "source" with "target" and every "include" with "nested type".

Icons already in `resource/icons/`: `lock.svg`, `unlock.svg`, `set.svg`, `delete.svg`,
`plus-square.svg`. Check `resource.qrc` lists `lock`/`unlock`; add if missing.

---

## Testing

Three layers, four new files plus the existing one:

| File | Layer | Covers |
|---|---|---|
| `test/pytest/test_param_manager.py` | unit (local `ParameterManager`) | existing behaviour; update file-shape assertions to version 2 in Phase 4 |
| `test/pytest/test_pm_locks.py` | unit + proxy | `ManagedParameter`, Lock API, chains, cycles, deletion cleanup, `pm-lock-update` on the wire |
| `test/pytest/test_pm_types.py` | unit + proxy | Type registry, Nested Types, matching, edits and side effects, `add_instance`, Type Locks, `_globals`, `pm-type-update` and side-effect creation broadcasts |
| `test/pytest/test_pm_persistence.py` | unit | version-2 write/read, legacy read, validation errors, load order, profile switching |
| `test/pytest/test_broadcaster.py` | unit + server | `Broadcaster` mixin; server registers sinks for created and config-loaded instruments; non-Broadcaster instruments unaffected |
| `test/pytest/test_pm_gui.py` | pytest-qt | tabs, tints, lock toggle, arm flow, Locks panel, Types tab, live update from a second client |

Conventions: proxy tests use the `param_manager` fixture; GUI tests copy the
`test_gui_navigation.py` pattern (own server on the `server_port` fixture, never a fixed
port, see D27; `qtbot.waitUntil`).
Every error path decided above has a test asserting the exception type **and** that the
message lists every offending path.

---

## Phases and tasks

Each task: what to build, files touched, acceptance, tests. One task per session.

### Phase 0 — Foundations

- [x] **0.0 Per-run test ports.** Added 2026-09-23 (see Decision record note of that date).
  In `test/pytest/conftest.py` add a session-scoped fixture `server_port` that picks two
  free consecutive ports once per pytest session (the server binds `port` and uses
  `port + 1` for broadcasts). `start_server`, `cli`, the shutdown client in `start_server`
  and every test use it instead of a fixed port: `test_client_station.py` (six
  `ClientStation(port=5555)` and the `"5555"` assert), `test_server_gui.py` (five
  `startServerGuiApplication()` calls), `test_gui_navigation.py` (`TEST_PORT = 5599`).
  Add to `AGENTS.md` under "Testing": "Tests never use a fixed port. Use the `server_port`
  fixture; agents run the suite in parallel." No change to `src/`.
  Acceptance: `git grep -n "5555\|5599" -- test/pytest` finds nothing (tracked source only;
  changed 2026-09-23 from `grep -rn`, which also matched `__pycache__` bytecode); two `uv run pytest` runs
  started at the same time both pass. Tests: whole suite green.
- [x] **0.1 `ParameterGroup` split.** In `params.py` create `ParameterGroup(InstrumentBase)`
  holding parameters and nested groups with the tree helpers moved from `ParameterManager`
  (`_get_param`, `_get_parent`, `has_param`, `parameter`, `to_tree`/`_to_tree`, `list`,
  `remove_empty_submodules`, the dotted `add_parameter`/`remove_parameter`/`get`/`set`).
  `ParameterManager(ParameterGroup)` keeps profiles, files, `workingDirectory`, and (later)
  Types/Locks. `_get_parent(..., create_parent=True)` creates `ParameterGroup(n)`.
  `_to_tree` assertion changes from `isinstance(sm, ParameterManager)` to `ParameterGroup`.
  Acceptance: creating `q01.IF` no longer lists the working directory or logs "parameter
  file not found"; `isinstance(pm.q01, ParameterGroup)` and not `ParameterManager`.
  Tests: `test_param_manager.py` all green unchanged; add `test_submodules_are_groups` and a
  test with a `parameter_manager-q01.json` present in `tmp_path` proving it is **not**
  loaded into the `q01` submodule.
- [x] **0.2 `Broadcaster` mixin.** In `base.py` (next to `sendBroadcast`): class
  `Broadcaster` with `add_broadcast_sink(fn)`, `remove_broadcast_sink(fn)`,
  `broadcast(bp: ParameterBroadcastBluePrint)`; sinks stored in a list; exceptions in one
  sink are logged and do not stop the others; no sinks → no-op. `ParameterManager` inherits
  it (no emissions yet). Tests: `test_broadcaster.py` unit part.
- [x] **0.3 Server registers sinks.** In `server/core.py`: helper
  `_registerBroadcaster(instrument)` doing `hasattr(instrument, "add_broadcast_sink")` →
  `instrument.add_broadcast_sink(self._broadcastParameterChange)`. Call it after
  `self.station.add_component(new_instrument)` in `_createInstrument` and for every
  component after the Station is loaded from config in `__init__`. Add a one-line comment
  above `_instrument_locks` noting prose calls it the "instrument mutex" (ADR-0003); do not
  rename. Tests: `test_broadcaster.py` server part — a dummy `Broadcaster` instrument created
  through `cli.find_or_create_instrument`; calling a method on it that emits a blueprint is
  received by a `SubClient`; a plain dummy instrument still works and gets no sink.
- [x] **0.4 Pre-existing fixes (D24, first two).** `_newOrDeleteParameterDetection`: use
  `kwargs.get("initial_value")` / `kwargs.get("unit", "")`. `apps.py:parameterManagerScript`:
  pass `sub_port=args.port + 1` (and `sub_host="localhost"`) into `ParameterManagerGui`.
  Tests: `test_apps.py` (extend the two existing param-manager launcher tests to assert
  the kwargs); a proxy test in `test_param_manager.py` that `add_parameter("x")` with no
  `initial_value`/`unit` succeeds and broadcasts.
- [x] **0.5 Broadcast action constants.** In `blueprints.py`: `PARAMETER_UPDATE`,
  `PARAMETER_CALL`, `PARAMETER_CREATION`, `PARAMETER_DELETION`, `PM_LOCK_UPDATE`,
  `PM_TYPE_UPDATE` string constants; use them in `server/core.py`, `gui/instruments.py`,
  `client/application.py`, `monitoring/listener.py` wherever the literals appear (grep
  `"parameter-` across `src/`). No behaviour change. Tests: whole suite green.

### Phase 1 — Locks

- [x] **1.1 `ManagedParameter`.** In `params.py`: `ManagedParameter(Parameter)` with
  attribute `lock: PMLockBluePrint | None` plus a private reference to the Target parameter
  object and a `locked` flag. `get_raw`: if locked → `return self._target.get()`; else own
  cached value. `set_raw`: if locked → `raise ValueError(f"{full_name} is locked to
  {target_full_name}")`; else store. Override `snapshot_base` so that while locked `value` is
  the Target's value and a `lock` entry is present. Helper `own_value()` returning the cached
  own value regardless of state. `ParameterManager.add_parameter` uses
  `parameter_class=ManagedParameter`. Also define `PMLockBluePrint(target: str, locked: bool,
  _class_type="PMLockBluePrint")` in `blueprints.py`. Tests: `test_pm_locks.py` unit part
  with two standalone `ManagedParameter`s (no manager): get redirect, set raises with the
  right message, unlocked exposes own value, snapshot values, cache untouched by locking.
- [x] **1.2 Lock API on `ParameterManager`.** `lock`, `unlock`, `relock`, `toggle_lock`,
  `remove_lock`, `get_lock`, `list_locks`, `followers_of` (D9), all validate-then-mutate:
  unknown paths, self-lock, and cycles (walking Targets regardless of state, D7) raise with
  messages naming the paths. `lock` on a parameter with an existing Lock re-targets (after
  the cycle check). `remove_parameter` removes every Lock whose Target is the removed
  parameter (D3) and then deletes. Chains behave per D7. Tests: `test_pm_locks.py` unit part.
- [x] **1.3 `pm-lock-update` and proxy round-trip.** Emit `pm-lock-update` per D10 from every
  Lock method and from the `remove_parameter` cleanup. Tests: `test_pm_locks.py` proxy part
  via the `param_manager` fixture: every method callable through the proxy; `get_lock` /
  `list_locks` deserialise to `PMLockBluePrint`; `pm.q02.x()` returns the Target's value over
  the wire; a `SubClient` receives `pm-lock-update` with a `PMLockBluePrint` value, and
  `None` after `remove_lock`.

### Phase 2 — Types

- [ ] **2.1 Type registry and definitions.** In `params.py`: internal dataclasses
  `_TypeEntry(default, unit, target)` and `_TypeDefinition(name, parameters: dict[str,
  _TypeEntry], nested: dict[str, str])`; registry `self._types` on the root only.
  `add_type`, `remove_type` (raises if any other Type nests it), `list_types`, `get_type`
  → `PMTypeBluePrint(name, parameters, nested, effective)` defined in `blueprints.py`.
  `_effective_parameters(type)` expands Nested Types recursively under their submodule name;
  raises on cycles (checked in `add_nested_type`) and on a path appearing twice. `_globals`
  refused as a Type name. Tests: `test_pm_types.py` unit part (definitions, effective set,
  cycle refusal, collision refusal, blueprint content).
- [ ] **2.2 Instance matching.** `instances_of(type)` and `types_of(path)` per D12 (existence
  **and** unit; every submodule at any depth; never root; never under `_globals`; empty Type
  → none). `types_of` orders innermost first (longest submodule path), then largest effective
  set. Tests: `test_pm_types.py` — the three-tier case from the mock (`qubit` nests `readout`
  nests `pulse_window`), unit mismatch excludes, extra parameters don't matter, two Types on
  one submodule, `q01.readout` is an Instance of `readout` on its own.
- [ ] **2.3 Type edits with Instance side effects.** `add_type_parameter` (creates in every
  Instance lacking it, with default and unit; raises if in the effective set already),
  `remove_type_parameter`, `set_type_parameter_default`, `set_type_parameter_unit`
  (propagates to every Instance's parameter), `add_nested_type` (writes missing entries under
  the submodule into every Instance of the outer Type), `remove_nested_type`. All
  validate-then-mutate. Tests: `test_pm_types.py` — each edit's effect table from D13, plus
  a failing validation leaving the tree byte-identical (compare `list()` and values before
  and after).
- [ ] **2.4 `add_instance`.** Per D14, including the up-front unit-conflict scan that raises
  listing every conflicting path before creating anything, dotted (nested) names, and
  `_globals` refusal. Tests: `test_pm_types.py`.
- [ ] **2.5 `pm-type-update` and side-effect broadcasts.** Every Type-editing method emits
  `pm-type-update` (D22) with the updated `PMTypeBluePrint` (or `None` on `remove_type`).
  Every parameter created by 2.3/2.4 emits `parameter-creation` through `self.broadcast`;
  none is emitted for direct `add_parameter` calls (the server does those). Tests:
  `test_pm_types.py` proxy part: all methods callable via proxy, `get_type` deserialises to
  `PMTypeBluePrint`, a `SubClient` sees `pm-type-update` and one `parameter-creation` per
  created parameter after `add_instance` from a second client, and the first client's
  proxy shows the new parameters after `update()`.

### Phase 3 — Type Locks and `_globals`

- [ ] **3.1 `_globals` rules.** Per D18: `add_parameter` and `add_instance` under `_globals`
  raise; `_globals` excluded from `instances_of`/`types_of` (already in 2.2, assert again);
  internal helper `_ensure_global_target(type, path)` creating `_globals.<type>.<path>` with
  the entry's default and unit. Tests: `test_pm_types.py`.
- [ ] **3.2 `lock_type_parameter` / `unlock_type_parameter`.** Per D17: store `target` on the
  entry; default Target via 3.1; put a locked Lock on every current Instance's parameter,
  skipping those with a Lock on another Target (collect, `logger.warning`, return the list);
  `unlock_type_parameter` clears the rule only. `add_instance` and completing
  `add_type_parameter` apply existing rules to new parameters. `PMTypeBluePrint.parameters`
  carries `target`. Both methods emit `pm-type-update` plus the `pm-lock-update`s of the
  Locks they create. Tests: `test_pm_types.py` — apply, skip-with-warning (use `caplog`),
  new Instance auto-locked, rule removal leaves Locks, Instance falling out keeps Locks,
  re-declare re-applies, explicit `target=` pointing at an ordinary parameter.
- [ ] **3.3 Deletion interplay.** `remove_parameter` on a `_globals` parameter (or any Type
  Lock Target) removes the Locks pointing at it **and** clears the Type Lock rule(s) whose
  Target it was, emitting `pm-type-update` for each affected Type. `remove_type` drops its
  rules but leaves `_globals` parameters and Instance Locks alone. Tests: `test_pm_types.py`.

### Phase 4 — Persistence (version 2)

- [ ] **4.1 Writer.** `toParamDict`/`toFile` produce the D19 layout: `version: 2`,
  `parameters` (own values via `ManagedParameter.own_value()`, `unit`, `lock` only on
  Followers, full paths as keys), `types` (parameters with default/unit/target, nested).
  Keep `json.dump(..., indent=2, sort_keys=True)`. Update `serialize.validateParamDict`
  callers accordingly (validate the `parameters` map with the existing schema) and add a
  `schemas/parameter_manager_v2.json`. Update the flat-shape assertions in
  `test_param_manager.py` to `["parameters"][...]`. Tests: `test_pm_persistence.py` writer
  cases; `test_param_manager.py` green.
- [ ] **4.2 Reader.** `fromParamDict`/`fromFile`: detect legacy (no `version`) vs 2; validate
  the whole document first (every `lock.target` and every Type `target` must be a key in
  `parameters`; otherwise `ValueError` listing **all** missing Targets, state untouched);
  then load parameters (existing `deleteMissing` semantics), then Types without Instance
  side effects, then Locks (locked/unlocked as stored). Tests: `test_pm_persistence.py` —
  legacy fixture file loads; round-trip equality; missing Targets error lists every one and
  leaves the previous state intact; partial Instances are not "completed" on load.
- [ ] **4.3 Profiles.** `remove_all_parameters` also clears Types and Locks (or add
  `_clear_all()` used by `switch_to_profile`); `switch_to_profile` = save → clear → load.
  `refresh_profiles`/`list_profiles` unchanged. Tests: `test_pm_persistence.py` — switching
  between a profile with Types and one without leaves no Type or Lock behind; existing
  switching tests in `test_param_manager.py` green.

### Phase 5 — GUI

- [ ] **5.1 Client-side state and broadcast handling.** In `gui/instruments.py`: a small
  `PMState` helper on `ParameterManagerGui` holding `types: dict[str, PMTypeBluePrint]` and
  `locks: dict[str, PMLockBluePrint]`, filled by `list_types`/`get_type`/`list_locks` on
  load and refresh; `ModelParameters.updateParameter` routes `pm-lock-update` and
  `pm-type-update` to new signals (`lockChanged(path, PMLockBluePrint|None)`,
  `typeChanged(name, PMTypeBluePrint|None)`) which update `PMState`. Fix D24 item three:
  `ParameterManagerTreeView.onItemNewValue` uses `widget._setMethod(value)`. Tests:
  `test_pm_gui.py` — construct `ParameterManagerGui` against a live server; a second client
  locks a parameter; `qtbot.waitUntil` the state holds it.
- [ ] **5.2 Tabs, tints and gutter bands.** Wrap the existing widget in a `QTabWidget`
  (Parameters, Types; Types tab empty for now). Port the mock's `claims()` to a pure
  function over `PMState.types` + the model's paths, producing per row: claiming Type,
  stack of up to 3 Types. Palette of 5 tint pairs + bar colours assigned by Type creation
  order. Apply tint via `BackgroundRole` on all columns and draw the gutter band(s) in a
  dedicated first column with a tiny delegate. Recompute on `typeChanged` and on model
  reload. Tests: `test_pm_gui.py` — after `add_type` + entries from a second client, rows
  under a matching submodule carry the Type's tint; after `remove_type_parameter`, the
  parameter's row loses it.
- [ ] **5.3 Lock column, toggle, context menu, arm strip.** New model column "locked to"
  (text: `locked to <target>` / `unlocked · <target>` / `target ×N` from `followers_of`
  computed client-side over `PMState.locks`). Per-row lock button in the delegate widget
  (visible when a Lock exists; purple fill while locked) calling `toggle_lock`. Context menu
  entries "Lock to…" and "Unlock" beside star/trash. Arm strip under the toolbar: label,
  `QLineEdit` + `QCompleter` over all paths ranked like the mock, Cancel; clicking a row
  while armed picks it; Esc cancels; on pick call `lock(follower, target)` and show the
  server's error text in the strip if it raises. Locked rows render their value read-only.
  On `parameter-update` for X, also refresh every row whose Lock Target chain reaches X.
  Tests: `test_pm_gui.py` — arm via context menu, pick a row, assert `get_lock` on the
  server; toggle unlocks; a cycle attempt shows the error; setting the Target from a second
  client repaints the Follower row.
- [ ] **5.4 Locks panel.** Toolbar action (lock icon, checkable, `Ctrl+Shift+L`) toggling a
  second `QTreeView` in a `QSplitter` right of the tree. Rows built from `PMState.locks`:
  Targets at depth 0 (Type Lock Targets first, labelled `[type: <t>] <target>`), Followers
  beneath, recursively for chains. Per Follower row: lock/relock toggle and remove
  (`remove_lock`). Per Target row: value editor with set button (plain `set` on the Target);
  for Type Lock rows: "lock all" (`lock_type_parameter` again) and "remove rule"
  (`unlock_type_parameter`). "Lock selection to…" button arms for the tree's current row.
  Tests: `test_pm_gui.py` — panel rows reflect `list_locks`; remove from panel removes on
  server; live update when a second client locks.
- [ ] **5.5 Types tab.** Three panes per the Design reference: type list (name, #instances,
  #params; New type strip → `add_type`); entries of the selected Type as a tree (own entries
  editable default → `set_type_parameter_default`, Remove → `remove_type_parameter`, Type
  Lock toggle → `lock_type_parameter`/`unlock_type_parameter`, re-target via arm; entries
  from Nested Types shown read-only with "defined by <type>"; nested submodule rows show
  `type: <t>` and Remove → `remove_nested_type`); "Add to type" strip
  (`add_type_parameter`); "Nested type … at submodule …" strip (`add_nested_type`);
  instances pane (name, #parameters, "also <types>", Show → switch to Parameters tab,
  expand and select; New instance strip → `add_instance`). Skipped-Lock warnings from
  `lock_type_parameter` shown in the pane's note line. Live update on `typeChanged`. Tests:
  `test_pm_gui.py` — create a Type and an Instance through the widgets; server state
  matches; second-client edits appear.
- [ ] **5.6 Delete-Target confirmation and polish.** Deleting a parameter (row delete button
  or shortcut) that has Followers pops a `QMessageBox` listing the Locks that will be removed
  (from `followers_of`) with OK/Cancel. Verify `resource.qrc` has `lock`/`unlock`; add
  shortcuts to `gui/shortcuts.py` for the new actions following its conventions; run
  `instrumentserver-param-manager` against a server on a non-default port and confirm live
  updates end to end (manual check, note the result under this task). Tests:
  `test_pm_gui.py` — the confirmation appears and Cancel leaves the server untouched.

### Phase 6 — Documentation

- [ ] **6.1 User Guide: `docs/user_guide/parameter_manager.md`.** Following the docs
  protocol: concept and single source of truth; hierarchical parameters; Types (shape,
  Instances, Nested Types, `add_instance`); Locks (states, chains, what `set` does); Type
  Locks and `_globals`; profiles and the version-2 file (with the legacy note); the GUI
  (tabs, tints, lock column, arm strip, Locks panel, Types tab) with screenshots; using it
  from measurement code. Verification script
  `test/docs_verification/user_guide/parameter_manager.py`. Zero Sphinx warnings.
- [ ] **6.2 Technical Guide: `docs/technical_guide/broadcasts.md`.** What triggers a
  Broadcast and the wire format; `SubClient`; external forwarding; the **Broadcaster
  contract** (mixin, registration points, threading, no-op standalone) and the Parameter
  Manager's actions with their payload blueprints. Verification script under
  `test/docs_verification/technical_guide/`. Cross-link with the User Guide page.
- [ ] **6.3 Bookkeeping.** Update `PLAN_docs_refactor.md` (mark the two pages done, adjust
  their section lists to what was written), `TEST_AUDIT.md` (gaps noticed, defects left),
  and do a final pass of `CONTEXT.md` and the three ADRs against the shipped behaviour.

---

## Notes for later (not tasks yet)

- The Broadcaster contract makes an `instrument-structure-changed` broadcast trivial if a
  future Virtual Instrument needs it; do not add it speculatively.
- `ServerResponse.__init__` munges string messages (`'`→`"`, `T`→`t`, …) before
  `json.loads`. Blueprint dataclasses avoid it; keep return values as blueprints or plain
  JSON types, never free-form strings.
- If `types_of` performance ever matters (thousands of parameters), cache the effective sets
  per Type and invalidate on Type edits; matching itself stays a tree walk.
