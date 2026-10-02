# Parameter Manager

The Parameter Manager is instrumentserver's flagship Virtual Instrument: a
hierarchical, persistent, profile-aware store of experiment parameters. It
lives entirely in the Server, has no hardware behind it, and exists to be the
single source of truth for the numbers of your experiment: which frequency
each qubit uses, which gain each amplifier runs at, which LO every receiver
shares.

You get one onto a Server like any other instrument, through a
[Client](client.md):

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client()
>>> pm = cli.find_or_create_instrument(
...     "parameter_manager",
...     "instrumentserver.params.ParameterManager",
... )
```

Everything the Parameter Manager can do works from Python and from its GUI
alike, and the two stay in sync live. This page walks through the pieces in
order: plain hierarchical parameters, Types, Locks, Type Locks and Globals,
profile files, the GUI, and a full measurement-script example at the end.
Each section is a fresh start: the snippets assume an empty Parameter
Manager, so the outputs are exactly the ones you will see.

## Concept

The Parameter Manager is a Virtual Instrument: an instrument the Server owns
that has no hardware behind it. Its parameters are ordinary QCoDeS parameters
on the Server, which is what makes it the single source of truth:

- Every Client and every GUI reads the same values, because there is only one
  copy, and it lives in the Server. A Proxy Instrument never keeps a
  diverging local value.
- Every change is announced as a Broadcast, so GUIs and Listeners follow
  along without polling. The wire format is described in
  [Broadcasts](../technical_guide/broadcasts.md).

Two Clients see the same values with no refresh in between:

```pycon
>>> pm_a = Client().find_or_create_instrument(
...     "parameter_manager",
...     "instrumentserver.params.ParameterManager",
... )
>>> pm_a.add_parameter("q01.IF", initial_value=10e6, unit="Hz")
>>> pm_b = Client().get_instrument("parameter_manager")
>>> pm_b.q01.IF()
10000000.0
>>> pm_a.q01.IF.set(11e6)
>>> pm_b.q01.IF()
11000000.0
```

`pm_b` never refreshed anything: the read asked the Server, and the Server
holds the one value. When the change happened, the Server also put a
`parameter-update` Broadcast on its PUB socket, which is what the Parameter
Manager GUI listens to. When the Parameter Manager itself creates or edits
something, for example a Lock or a Type, it announces that with its own
Broadcast; the Technical Guide page above lists them all.

## Hierarchical parameters

Parameters live at dotted paths relative to the Parameter Manager, such as
`q01.readout.IF`. Every level of the path is a Parameter Group, a plain
container of parameters and further Parameter Groups, created on demand the
first time a path needs it. Only the root is the Parameter Manager itself;
the groups hold no files, no Types and no Locks.

```pycon
>>> pm.add_parameter("q01.readout.IF", initial_value=20e6, unit="Hz")
>>> pm.add_parameter("q01.power", initial_value=-10, unit="dBm")
>>> pm.list()
['q01.readout.IF', 'q01.power']
>>> pm.has_param("q01.readout.IF")
True
>>> pm.has_param("q01.readout.bw")
False
```

Through the Proxy Instrument, the hierarchy is attribute access, and
parameters read and set like any QCoDeS parameter:

```pycon
>>> pm.q01.readout.IF()
20000000.0
>>> pm.q01.readout.IF.set(21e6)
>>> pm.q01.readout.IF()
21000000.0
>>> pm.q01.readout.IF.unit
'Hz'
```

:::{note}
The Proxy reflects the Server-side tree as it was when the Proxy was built or
last refreshed. When someone else creates parameters (another Client, or a
method that creates parameters as a side effect such as `add_instance`), call
`pm.update()` to pick them up.
:::

`remove_parameter` deletes a parameter and prunes the Parameter Groups it
empties:

```pycon
>>> pm.remove_parameter("q01.readout.IF")
>>> pm.list()
['q01.power']
```

To keep emptied Parameter Groups around instead, pass `cleanup=False` to
`remove_parameter` and sweep them up later with `remove_empty_submodules()`.

## Types

Lab devices repeat: six qubits on one chip, four delivery channels per
module, each copy carrying the same parameters. The Parameter Manager makes
the repetition explicit with a Type. A Type is a named shape: a set of
relative parameter paths, each with a default value and a unit, plus Nested
Types required at named submodules.

A Parameter Group that carries the whole shape is an Instance of that Type.
Nothing stores that membership anywhere: an Instance is found by shape, on
every query, and never registered. So a Parameter Group becomes an Instance
the moment it carries the shape, and stops being one the moment it does not.

```pycon
>>> pm.add_type("qubit")
>>> pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
>>> pm.add_type_parameter("qubit", "octave_gain", default=10, unit="dB")
>>> pm.instances_of("qubit")
[]
>>> pm.add_instance("qubit", "q01")
>>> pm.add_instance("qubit", "q02")
>>> pm.instances_of("qubit")
['q01', 'q02']
>>> pm.update()
>>> pm.q01.IF()
10000000.0
>>> pm.q01.octave_gain()
10
```

A fresh Type has no Instances, because nothing carries its shape yet.
`add_instance` writes the shape into a Parameter Group: every missing entry
is created with the Type's default value and unit, and parameters that exist
at those paths already are kept as they are.

The shape-finding works in the other direction too. `q03` below was never
registered anywhere; it simply carries the shape, so it counts:

```pycon
>>> pm.add_parameter("q03.IF", initial_value=99e6, unit="Hz")
>>> pm.add_parameter("q03.octave_gain", initial_value=1, unit="dB")
>>> pm.instances_of("qubit")
['q01', 'q02', 'q03']
>>> pm.types_of("q03.IF")
['qubit']
```

The same cuts both ways: delete a parameter an Instance needs, and that
submodule stops matching, with no other change. `q02` above stops being an
Instance the moment `q02.IF` is removed.

### Editing a Type

Adding an entry to a Type writes it into every Instance that lacks it, with
the entry's default and unit:

```pycon
>>> pm.add_type_parameter("qubit", "window", default=0.5, unit="s")
>>> pm.update()
>>> pm.q03.window()
0.5
```

Changing the default touches nobody who exists; only parameters created
later start with it:

```pycon
>>> pm.set_type_parameter_default("qubit", "window", 1.0)
>>> pm.q01.window()
0.5
>>> pm.add_instance("qubit", "q04")
>>> pm.update()
>>> pm.q04.window()
1.0
```

`set_type_parameter_unit` changes the entry's unit and propagates it to that
parameter in every Instance. The unit is part of the shape, so a parameter
with the wrong unit keeps its Parameter Group out of the Instance list.

### Nested Types

A Type can require another Type at one of its submodules. A `qubit` needs a
`readout`; the Nested Type expands under the submodule it is required at:

```pycon
>>> pm.add_type("readout")
>>> pm.add_type_parameter("readout", "bw", default=20e6, unit="Hz")
>>> pm.add_nested_type("qubit", "readout", "readout")
>>> pm.update()
>>> pm.q01.readout.bw()
20000000.0
```

What a Type requires in total is its effective set: its own entries plus
every Nested Type's entries under their submodule names. `get_type` returns
it together with the rest of the definition:

```pycon
>>> qubit = pm.get_type("qubit")
>>> qubit.nested
{'readout': 'readout'}
>>> qubit.effective["readout.bw"]
{'unit': 'Hz', 'from_type': 'readout'}
```

When several Types cover one parameter, the innermost Instance wins, then
the one with the larger effective set. That Claiming Type is what the GUI
tints a row with:

```pycon
>>> pm.types_of("q01.readout.bw")
['readout', 'qubit']
>>> pm.instances_of("readout")
['q01.readout', 'q02.readout', 'q03.readout', 'q04.readout']
```

### Removing from a Type

Removing an entry, a Nested Type or a whole Type leaves every parameter
alone. The submodules keep what they carry; matching simply follows the
shape, which the removal changed:

```pycon
>>> pm.remove_type_parameter("qubit", "window")
>>> pm.has_param("q01.window")
True
>>> pm.remove_nested_type("qubit", "readout")
>>> pm.has_param("q01.readout.bw")
True
>>> pm.remove_type("qubit")
>>> pm.list_types()
['readout']
>>> pm.has_param("q01.IF")
True
```

A Type that is still required as a Nested Type refuses to be removed, naming
the Types that nest it.

## Locks

Shared settings want one authoritative value. A Lock ties a parameter (the
Follower) to another parameter (its Target). A Lock has three states:

- no Lock: the parameter behaves as a plain parameter;
- a Lock that is present but unlocked: the parameter answers `get` with its
  own value, but remembers its Target so it can be locked again;
- a Lock that is locked: the parameter answers `get` with the Target's value
  and refuses `set`.

```pycon
>>> pm.add_parameter("q01Data.IF", initial_value=10e6, unit="Hz")
>>> pm.add_parameter("q01.IF", initial_value=5e6, unit="Hz")
>>> pm.lock("q01.IF", "q01Data.IF")
>>> pm.get_lock("q01.IF")
PMLockBluePrint(target='parameter_manager.q01Data.IF', locked=True, _class_type='PMLockBluePrint')
```

While locked, the Follower pulls the Target's value on every `get`. Nothing
is ever pushed into the Follower, and the Target knows nothing about its
Followers:

```pycon
>>> pm.q01.IF()
10000000.0
>>> pm.q01Data.IF.set(11e6)
>>> pm.q01.IF()
11000000.0
```

A locked Follower refuses `set` with an error naming the Target. Over the
connection, Server-side errors arrive as a generic `Exception` (the
[Python Client](client.md) page describes this), and the message carries the
pair:

```pycon
>>> try:
...     pm.q01.IF.set(12e6)
... except Exception as exc:
...     message = str(exc)
>>> "parameter_manager.q01.IF is locked to parameter_manager.q01Data.IF" in message
True
```

Locking never touches the Follower's own value. Unlocking exposes it again,
and relocking goes back to the Target; `toggle_lock` switches between the
two states:

```pycon
>>> pm.unlock("q01.IF")
>>> pm.q01.IF()
5000000.0
>>> pm.relock("q01.IF")
>>> pm.q01.IF()
11000000.0
>>> pm.toggle_lock("q01.IF")
>>> pm.get_lock("q01.IF").locked
False
>>> pm.toggle_lock("q01.IF")
>>> pm.get_lock("q01.IF").locked
True
```

`remove_lock` removes a Lock entirely and forgets the Target.
`list_locks` reports every Lock in the Parameter Manager, and
`followers_of` names the Followers of one parameter:

```pycon
>>> pm.followers_of("q01Data.IF")
['q01.IF']
>>> pm.list_locks()
{'q01.IF': PMLockBluePrint(target='parameter_manager.q01Data.IF', locked=True, _class_type='PMLockBluePrint')}
```

A Lock never points at its own parameter, and its Target lives in the same
Parameter Manager.

### Chains and cycles

A Target may itself have a Lock, and each hop reads according to its own
state at read time:

```pycon
>>> pm.add_parameter("q02.IF", initial_value=0, unit="Hz")
>>> pm.lock("q02.IF", "q01.IF")
>>> pm.q02.IF()
11000000.0
>>> pm.unlock("q01.IF")
>>> pm.q02.IF()
5000000.0
```

`q02.IF` is still locked, but it reads through `q01.IF`, which now answers
with its own value. Relock `q01.IF`, and `q02.IF` follows the Target again.

Locks may chain but never cycle. A Lock that would close a cycle is refused,
with the whole chain in the error:

```pycon
>>> try:
...     pm.lock("q01Data.IF", "q02.IF")
... except Exception as exc:
...     cycle_message = str(exc)
>>> cycle_message
'cannot lock parameter_manager.q01Data.IF to parameter_manager.q02.IF: cycle in Lock targets: parameter_manager.q02.IF -> parameter_manager.q01.IF -> parameter_manager.q01Data.IF'
```

Deleting a parameter removes the Locks that pointed at it; its Followers
become plain parameters and answer `get` with their own values again. A
Follower of a survivor keeps its Lock:

```pycon
>>> pm.remove_parameter("q01Data.IF")
>>> pm.get_lock("q01.IF")
None
>>> pm.q01.IF()
5000000.0
>>> pm.get_lock("q02.IF")
PMLockBluePrint(target='parameter_manager.q01.IF', locked=True, _class_type='PMLockBluePrint')
>>> pm.remove_lock("q02.IF")
>>> pm.list_locks()
{}
```

Every Lock method that changes a Lock emits one `pm-lock-update` Broadcast
per affected Follower, which is how the GUI and any other listener stay
current; [Broadcasts](../technical_guide/broadcasts.md) shows the payload.

## Type Locks and Globals

One Lock ties two parameters together. Usually you want one value shared by
every Instance of a Type: one LO frequency for all qubits. A Type Lock
declares that on a Type entry, and every Instance follows:

```pycon
>>> pm.add_type("qubit")
>>> pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
>>> pm.add_instance("qubit", "q01")
>>> pm.add_instance("qubit", "q02")
>>> pm.update()
>>> pm.lock_type_parameter("qubit", "IF")
[]
```

With no Target given, the Target is the Globals parameter
`_globals.<type>.<path>`, created on demand with the entry's default value
and unit. Every current Instance gets an ordinary, locked Lock on it:

```pycon
>>> pm.has_param("_globals.qubit.IF")
True
>>> cli.call("parameter_manager.get", "_globals.qubit.IF")
10000000.0
>>> pm.get_lock("q01.IF")
PMLockBluePrint(target='parameter_manager._globals.qubit.IF', locked=True, _class_type='PMLockBluePrint')
```

Setting the Globals parameter moves every Follower at once:

```pycon
>>> cli.call("parameter_manager.set", "_globals.qubit.IF", 12e6)
>>> pm.q01.IF()
12000000.0
>>> pm.q02.IF()
12000000.0
```

:::{note}
Why `Client.call`? On a Proxy Instrument, `pm.get` and `pm.set` are QCoDeS'
own local shorthands, and they only take a plain parameter name: a dotted
path raises `KeyError`. Attribute access does reach the Globals submodule
once the Proxy knows it; a Proxy built before the Globals parameter existed
needs one `pm.update()` first. The Parameter Manager's own dotted `get` and
`set` run through `Client.call`, as above.
:::

An explicit Target names any parameter of the same Parameter Manager
instead:

```pycon
>>> pm.add_parameter("lo.frequency", initial_value=1e6, unit="Hz")
>>> pm.remove_lock("q02.IF")  # let q02 join the new Target below
>>> pm.lock_type_parameter("qubit", "IF", target="lo.frequency")
['q01.IF']
```

The return value names the Instance parameters that were skipped, and the
Parameter Manager logs a warning: `q01.IF` already carried a Lock on another
Target (the Globals parameter), and a Lock is never re-pointed behind its
holder's back. Everything else is locked to the new Target. Declaring the
same Type Lock again is how the GUI's lock all button re-applies it to
everyone.

`unlock_type_parameter` removes only the rule. The Locks it created stay
until they are removed individually, and Instances created after the removal
get no Lock:

```pycon
>>> pm.unlock_type_parameter("qubit", "IF")
>>> pm.get_type("qubit").parameters["IF"]["target"] is None
True
>>> pm.get_lock("q02.IF") is not None
True
>>> pm.add_instance("qubit", "q03")
>>> pm.get_lock("q03.IF")
None
```

Globals itself is never an Instance of anything, and its parameters are
created on demand by the Type Lock, not through `add_parameter`, which
refuses the name with "the Globals submodule name is reserved". Otherwise a
Globals parameter is ordinary: it shows up in `list()`, can be read and set,
and is saved with the profile.

## Profiles and files

A Parameter Manager saves itself as a JSON profile document in the working
directory of the Server process, so the state survives restarts and can be
switched per experiment. This section starts from two parameters and a Lock
between them, so the document below shows all three shapes:

```pycon
>>> pm.add_parameter("lo.frequency", initial_value=5e9, unit="Hz")
>>> pm.add_parameter("q01.IF", initial_value=10e6, unit="Hz")
>>> pm.lock("q01.IF", "lo.frequency")
>>> pm.toFile()
```

The default file is `parameter_manager-parameter_manager.json`, and it holds
the version-2 document:

```json
{
  "parameters": {
    "parameter_manager.lo.frequency": {
      "unit": "Hz",
      "value": 5000000000.0
    },
    "parameter_manager.q01.IF": {
      "lock": {
        "locked": true,
        "target": "parameter_manager.lo.frequency"
      },
      "unit": "Hz",
      "value": 10000000.0
    }
  },
  "types": {},
  "version": 2
}
```

Three things to read off that document:

- Parameter keys are the full dotted paths with the instrument name in
  front, the same form the Locks and the Type Lock Targets use.
- `value` is always the parameter's own value. A locked Follower saves its
  own value plus its `lock`, never the Target's value, so unlocking exposes
  what was saved.
- `lock` appears only on parameters that carry a Lock, in either state. The
  `types` section holds the Type definitions, with each entry's default,
  unit and Type Lock Target.

`fromFile` loads a document back, restoring own values and Lock states:

```pycon
>>> pm.lo.frequency.set(6e9)
>>> pm.fromFile()
>>> pm.lo.frequency()
5000000000.0
>>> pm.get_lock("q01.IF")
PMLockBluePrint(target='parameter_manager.lo.frequency', locked=True, _class_type='PMLockBluePrint')
```

Loading removes parameters the document does not list; that is the
`deleteMissing` default of the reader underneath, and `fromFile` always
loads with that default today. The dictionary variant takes it explicitly,
so a document that omits one parameter shows the difference:

```pycon
>>> pm.add_parameter("temp.extra", initial_value=1)
>>> document = pm.toParamDict()
>>> del document["parameters"]["parameter_manager.temp.extra"]
>>> pm.fromParamDict(document, deleteMissing=False)
>>> pm.has_param("temp.extra")
True
>>> pm.fromParamDict(document)
>>> pm.has_param("temp.extra")
False
```

Any file named `parameter_manager-<profile>.json` in the working directory
is a profile. `refresh_profiles` re-reads the directory, `list_profiles`
reports what it found, and `switch_to_profile` moves between them: it saves
the profile being left, clears every parameter, Type and Lock, then loads
the profile you name:

```pycon
>>> pm.toFile(name="cooldown")
>>> sorted(pm.refresh_profiles())
['parameter_manager-cooldown.json', 'parameter_manager-parameter_manager.json']
>>> pm.unlock("q01.IF")
>>> pm.lo.frequency.set(8e9)
>>> pm.switch_to_profile("parameter_manager")
>>> pm.lo.frequency()
5000000000.0
>>> pm.get_lock("q01.IF").locked
True
>>> pm.switch_to_profile("cooldown")
>>> pm.lo.frequency()
8000000000.0
>>> pm.get_lock("q01.IF")
PMLockBluePrint(target='parameter_manager.lo.frequency', locked=False, _class_type='PMLockBluePrint')
```

A file without a top-level `version` key is the old flat map from before
Types and Locks existed. Write one (any file named
`parameter_manager-<profile>.json` works) and load it:

```json
{
  "parameter_manager.old_target": {"unit": "Hz", "value": 5},
  "parameter_manager.old_param": {"unit": "M", "value": 123}
}
```

```pycon
>>> pm.add_parameter("old_target", initial_value=5, unit="Hz")
>>> pm.add_parameter("old_param", initial_value=1, unit="M")
>>> pm.lock("old_param", "old_target")
>>> pm.unlock("old_param")  # present but unlocked, so the load can set its value
>>> pm.fromFile("parameter_manager-legacy.json")
>>> pm.old_param()
123
>>> pm.list_locks()
{'old_param': PMLockBluePrint(target='parameter_manager.old_target', locked=False, _class_type='PMLockBluePrint')}
```

:::{note}
The legacy reader writes no Types and no Locks. Parameters it does not list
are removed as above, their Locks with them; a Lock whose parameters stay is
untouched, exactly as the load above leaves the unlocked `old_param` Lock.
Saving always writes the version-2 document, so one save over an old file
upgrades it.
:::

## The GUI

The Parameter Manager GUI is one window with two tabs, Parameters and Types.
You can run it standalone:

```{prompt} bash
instrumentserver-param-manager --port 5555
```

The launcher connects a Client to the Server on that port, creates the
Parameter Manager named `parameter_manager` if it does not exist yet, and
opens the window. `--name` chooses a different Parameter Manager. The Server
window itself opens the generic instrument widget for a Parameter Manager
unless the station config's `gui` entry names
`instrumentserver.gui.parameter_manager.ParameterManagerGui`, as the
`serverConfig.yml` in the repository does; then the Server window embeds the
same widget, and the launcher above is the sure way to get it. Configs that
still name the older path `instrumentserver.gui.instruments.ParameterManagerGui`
keep working.
[the Server](server.md) covers launching and the station config, and
[GUI features](gui_features.md) describes the `gui` entry and the patterns
shared by every instrument window: starring, trashing, filtering, and the
detachable tabs.

### The Parameters tab

The Parameters tab is the tree of parameters: name, unit, a value editor per
row, and the strip at the bottom to add a parameter. Three things are
specific to the Parameter Manager:

- **Tints and gutter bands.** Every parameter of an Instance is tinted with
  the colour of its Claiming Type, and the thin coloured band at the left
  edge stacks one segment per Type covering the row, outermost first, up to
  three. When a Client edits a Type, the tints follow live, because the
  Parameter Manager emits a `pm-type-update` Broadcast.

:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
The Parameters tab with two Types tinting their rows: the parameter tree
with `qubit` rows in one tint and `readout` rows in another, the coloured
gutter bands stacked at the left edge, the "locked to" column showing
`locked to _globals.qubit.IF` on the locked rows, and the lock button on one
of them. Light theme:
`docs/_static/user_guide/parameter_manager/tree_tints_light.png`, dark
theme: `docs/_static/user_guide/parameter_manager/tree_tints_dark.png`.
:::

%
% ```{image} ../_static/user_guide/parameter_manager/tree_tints_light.png
% :class: only-light
% :alt: The Parameters tab: the parameter tree with Type tints and gutter bands
% ```
%
% ```{image} ../_static/user_guide/parameter_manager/tree_tints_dark.png
% :class: only-dark
% :alt: The Parameters tab: the parameter tree with Type tints and gutter bands
% ```

- **The "locked to" column.** A Follower shows `locked to <target>` while
  its Lock is locked and `unlocked · <target>` while unlocked; a parameter
  that is a Target shows `target ×N` for its N Followers. The lock button on
  the row, purple while locked, toggles the Lock.
- **The context menu.** Right-clicking a row offers "Lock to…" and "Unlock"
  beside the usual actions.

"Lock to…" arms the Target picker: a strip appears under the toolbar, naming
the Follower, with a line edit that completes over every parameter path,
ranked so that the same relative path on another Instance comes first, then
paths containing that relative path, then the rest, and a Cancel button.
Click a tree row or complete a path to pick the Target. If the Server
refuses, for a cycle for example, the strip shows the error.

:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
The arm strip in action: the strip under the toolbar reading
"Target for q01.IF", the line edit showing a typed partial path with the
completion popup open over the candidate paths, and the Cancel button at
its right. Light theme:
`docs/_static/user_guide/parameter_manager/arm_strip_light.png`, dark
theme: `docs/_static/user_guide/parameter_manager/arm_strip_dark.png`.
:::

%
% ```{image} ../_static/user_guide/parameter_manager/arm_strip_light.png
% :class: only-light
% :alt: The arm strip picking a Target under the toolbar
% ```
%
% ```{image} ../_static/user_guide/parameter_manager/arm_strip_dark.png
% :class: only-dark
% :alt: The arm strip picking a Target under the toolbar
% ```

### The Locks panel

The lock icon in the toolbar, or Ctrl+Shift+L, opens the Locks panel next to
the tree. It shows the same Locks from the Target side: one row per Target,
with each Target's Followers nested beneath it, recursively for chains. Type
Lock Targets come first and are labelled with their Type, as
`[type: qubit] _globals.qubit.IF`.

Each row carries what it needs. A Target row has a value editor, and setting
it repaints every Follower watching. A locked Follower row shows its value
read-only, with a lock or relock toggle and a remove button. A Type Lock row
has lock all, which re-applies the Type Lock to every Instance, and remove
rule, which removes only the rule and leaves the Locks. "Lock selection
to…" arms the picker for the row currently selected in the tree.

:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
The Locks panel open next to the tree: the Type Lock Target row labelled
`[type: qubit] _globals.qubit.IF` with its value editor, two Follower rows
nested beneath it with read-only values and their toggle and remove buttons,
and the "Lock selection to…" button with the selected-parameter label at the
bottom. Light theme:
`docs/_static/user_guide/parameter_manager/locks_panel_light.png`, dark
theme: `docs/_static/user_guide/parameter_manager/locks_panel_dark.png`.
:::

%
% ```{image} ../_static/user_guide/parameter_manager/locks_panel_light.png
% :class: only-light
% :alt: The Locks panel with a Type Lock Target and its Followers
% ```
%
% ```{image} ../_static/user_guide/parameter_manager/locks_panel_dark.png
% :class: only-dark
% :alt: The Locks panel with a Type Lock Target and its Followers
% ```

### The Types tab

The Types tab (Ctrl+Shift+Y switches between the two tabs) keeps the
structure work in one place, in three panes:

- Left: the list of Types, each with its number of Instances and parameters,
  tinted in the Type's colour, and the "New type:" strip below.
- Top right: the selected Type's entries as a tree. An entry of the Type
  itself has an editable default, a Remove button, and the Type Lock toggle
  in the "locked to" column; while the entry is locked, the column also
  shows a re-target button and the Target's path. Entries that come from a
  Nested Type are read-only and say "defined by <type>"; submodule rows show
  which Type they require and can drop the requirement. The "Add to type"
  and "Nested type" strips below add entries and Nested Type requirements.
- Bottom right: the Instances of the selected Type, each with its parameter
  count and the other Types it also carries. "Show" jumps to the Parameters
  tab and selects the Instance; the "New instance:" strip adds one.

:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
The Types tab with a Type selected: the tinted type list on the left, the
entries tree in the top right pane with an editable default, a Type Lock
toggle and a "defined by readout" row, the two strips below it, and the
Instances pane in the bottom right with one Instance row and its Show
button. Light theme:
`docs/_static/user_guide/parameter_manager/types_tab_light.png`, dark
theme: `docs/_static/user_guide/parameter_manager/types_tab_dark.png`.
:::

%
% ```{image} ../_static/user_guide/parameter_manager/types_tab_light.png
% :class: only-light
% :alt: The Types tab with its three panes
% ```
%
% ```{image} ../_static/user_guide/parameter_manager/types_tab_dark.png
% :class: only-dark
% :alt: The Types tab with its three panes
% ```

### Deleting a Target

Deleting a parameter that others follow is the one destructive action with a
safety net: the Parameter Manager names every Follower whose Lock will
vanish and asks for confirmation. Cancel leaves the Server untouched; a
parameter without Followers is deleted without asking.

:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
The "Remove Target?" confirmation dialog for a parameter with two
Followers: the question text listing each Follower with its Lock state,
with Cancel as the default button. Light theme:
`docs/_static/user_guide/parameter_manager/delete_confirmation_light.png`,
dark theme:
`docs/_static/user_guide/parameter_manager/delete_confirmation_dark.png`.
:::

%
% ```{image} ../_static/user_guide/parameter_manager/delete_confirmation_light.png
% :class: only-light
% :alt: The Remove Target confirmation dialog
% ```
%
% ```{image} ../_static/user_guide/parameter_manager/delete_confirmation_dark.png
% :class: only-dark
% :alt: The Remove Target confirmation dialog
% ```

### Keyboard shortcuts

The shortcuts below matter most in this window; the defaults come from the
GUI's shortcut registry, and [GUI features](gui_features.md) shows how to
rebind them.

| Action | Default keys | What it does |
| --- | --- | --- |
| Delete parameter | `Ctrl+Backspace` | Delete the selected parameter |
| Lock to… | `Ctrl+L` | Lock the selected parameter to… (pick a Target) |
| Unlock | `Ctrl+U` | Unlock the selected parameter |
| Show the Locks panel | `Ctrl+Shift+L` | Show or hide the Locks panel |
| Switch tabs | `Ctrl+Shift+Y` | Switch between the Parameters and Types tabs |
| Add parameter | `Ctrl+N` | Jump cursor to the add parameter bar |
| Load parameters | `Ctrl+Shift+O` | Load parameters from JSON file |
| Save parameters | `Ctrl+Shift+S` | Save parameters to JSON file |
| Refresh all | `Ctrl+Shift+R` | Refresh all parameters from instrument |

## Using it from measurement code

A measurement script treats the Parameter Manager like any instrument: find
it or create it, then read and set through the Proxy Instrument. One-time
setup declares the shape, and a Type Lock shares one value across every
Instance:

```pycon
>>> from instrumentserver.client import Client
>>> cli = Client()
>>> pm = cli.find_or_create_instrument(
...     "parameter_manager",
...     "instrumentserver.params.ParameterManager",
... )
>>> pm.add_parameter("power", initial_value=-10, unit="dBm")
>>> pm.add_type("qubit")
>>> pm.add_type_parameter("qubit", "IF", default=10e6, unit="Hz")
>>> pm.add_instance("qubit", "q0")
>>> pm.add_instance("qubit", "q1")
>>> pm.update()
>>> pm.lock_type_parameter("qubit", "IF")
[]
```

The sweep sets the Globals Target and reads the Followers; both qubits move
together, and any GUI watching follows live:

```pycon
>>> for if_hz in (10e6, 11e6, 12e6):
...     cli.call("parameter_manager.set", "_globals.qubit.IF", if_hz)
...     print(pm.q0.IF(), pm.q1.IF())
10000000.0 10000000.0
11000000.0 11000000.0
12000000.0 12000000.0
```

When one qubit has to deviate, unlock it first: setting a locked Follower
raises, naming its Target. The Follower keeps its own value the whole time,
so unlocking exposes it, and `relock` rejoins the Target:

```pycon
>>> try:
...     pm.q0.IF.set(13e6)
... except Exception as exc:
...     "is locked to" in str(exc)
True
>>> pm.unlock("q0.IF")
>>> pm.q0.IF.set(13e6)
>>> pm.q0.IF()
13000000.0
>>> pm.q1.IF()
12000000.0
>>> pm.relock("q0.IF")
>>> pm.q0.IF()
12000000.0
```

At the end of the experiment, save the profile, and the next run starts
where this one ended:

```pycon
>>> pm.toFile()
```

The [Python Client](client.md) page covers the Client's connection lifecycle
and error handling. The profile files end up in the working directory of the
Server process, as Profiles and files above describes, so where they live
follows from where the Server runs; [the Server](server.md) page documents
the Server itself.
