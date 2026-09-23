# Documentation Refactor — Master Plan

This is the guiding document for the instrumentserver documentation refactor. It records the
goal, the philosophy, the agreed structure, and the phase-by-phase breakdown of the work.
It is a living document: statuses are updated as work progresses, and section lists are
refined during each page's grilling session.

Companion files:

- `CONTEXT.md` — the canonical glossary. All docs use its terms exactly.
- `TEST_AUDIT.md` — tracker for test and docstring gaps discovered while documenting.
- `test/docs_verification/` — verification scripts (one per page; see Workflow).

## How to use this document (session protocol)

Each work session starts fresh from this document. The intended unit per session is one
sub-sub-phase (a page section), or a few small ones. On session start:

1. Read this file top to bottom, then `CONTEXT.md`, then `TEST_AUDIT.md`.
2. Find the next open item: the first non-`[x]` checkbox in phase order, unless Marcos
   names a different target.
3. Start with GRILL, and GRILL means **interviewing Marcos**: ask questions one at a
   time, with a recommendation per question, until the section's scope and claims are
   agreed. Never skip this or self-answer it.
4. Work the loop (GRILL → VERIFY → DRAFT → REVISE → AUDIT). Update the checkbox status
   marker in this file as the section moves through the loop.
5. Update `CONTEXT.md` immediately when a term is resolved, and `TEST_AUDIT.md` at every
   AUDIT step. Leave all changes uncommitted (see Ground rule).

Building the site locally: ALWAYS build from a clean slate, from the `docs/` folder:

```bash
cd docs && uv run make clean && uv run make html
```

Never trust an incremental build when checking work: stale caches hide warnings and
keep deleted pages alive. Output lands in `docs/build/`. The quality bar is a green
clean build with **zero Sphinx warnings**. (CI runs the same html target; pandoc is
the only system dep.)

---

## Goal

Replace the current under-construction documentation site with a complete, **verified**,
well-organized site covering everything the package actually ships — modeled on the
structure and toolchain of the sibling labcore docs, published at
`toolsforexperiments.github.io/instrumentserver`.

## Why

- The current site documents a fraction of the package. Of the five console entry points,
  only the server is described; the Client Station, the monitoring/deployment stack, the
  Parameter Manager's profiles, polling, chained servers, and virtual instruments are
  invisible.
- What *is* documented is unverified and partly wrong (the API page references classes
  that don't exist; the overview tells readers to email the maintainer).
- The lab onboards through these docs. Every undocumented feature is re-explained by hand.
- Documenting forces verification: writing each page doubles as an audit of behavior and
  of test coverage.

## Philosophy

1. **Nothing is documented without being executed.** Every behavioral claim on every page
   is backed by a runnable verification script committed to the repo. No claims from
   memory, no claims from reading code alone.
2. **Docs describe what ships, not what's planned.** No aspirational features. The
   under-construction warning shrinks every phase and disappears at the end.
3. **Pages follow features, not entry points.** The five console scripts are launchers for
   three features (Server, Client Station, Monitoring) plus two conveniences (Detached
   GUI, Parameter Manager GUI). Each entry point is documented inside the feature it
   serves.
4. **Two depths, cross-linked.** The User Guide answers "how do I use this?"; the
   Technical Guide answers "how does this work inside?". Same feature, two pages, two
   depths (e.g. external broadcast: mentioned in `server.md`, explained in
   `broadcasts.md`).
5. **One language.** Terminology comes from `CONTEXT.md` (Virtual Instrument, Client
   Station, Blueprint, Broadcast, Listener…). If a page needs a term the glossary lacks,
   the glossary is updated first.
6. **Auto things stay auto.** API reference is pure autosummary — no hand-written
   navigation lists that rot independently of the code.
7. **Documenting drives testing — and docstrings.** Each verified behavior is checked
   against the pytest suite, and each referenced symbol's docstring is checked for
   correctness; gaps go to `TEST_AUDIT.md` and become parallel work, never blocking
   docs. By the end, everything documented is tested and everything referenced has an
   accurate docstring.

## Ground rule

**NEVER COMMIT FOR ANY REASON.** All git commits (and pushes) are done by Marcos
personally. Agents and collaborators leave changes in the working tree, always.

## Workflow (the unit of work is a page *section*)

Every page is a **sub-phase**; every section of a page is a **sub-sub-phase**. Each
section goes through this loop:

```
1. GRILL    — discuss scope/claims of this section; resolve terminology against CONTEXT.md
2. VERIFY   — behavior exercised in the page's verification script (a new section of
              test/docs_verification/<area>/verify_<page>.py) — in files, never ad hoc.
              We observe how it *really* works before writing a word about it.
3. DRAFT    — first draft written from the verified behavior
4. REVISE   — feedback loop on the draft until approved
5. AUDIT    — two checks on what this section touched:
              (a) tests — is the verified behavior covered by the pytest suite?
              (b) docstrings — does every class/function/parameter the section
                  references have a correct, current docstring?
              Gaps from either go in TEST_AUDIT.md (tests table / docstrings table)
```

Status legend used throughout this document:

`[ ]` not started · `[G]` grilling · `[V]` verified · `[D]` drafted · `[R]` in revision · `[x]` approved + audited

**Verification scripts**: one script per page, named `verify_<page>.py`, with one clearly
marked section per page section. Runnable standalone (asserts documented behavior,
exits 0). Committed throughout the project; deleted in the final cleanup phase after the
test audit has been fully harvested.

**Shared helpers** (`test/docs_verification/helpers.py`): common utilities in the spirit
of pytest fixtures, so scripts stay focused on the behavior they verify — a single
canonical way to start/stop a server (context manager, with Dummy Instruments and an
optional config file), get a connected client, and capture Broadcasts. Scripts never
hand-roll server startup. Helpers that prove broadly useful are candidates to graduate
into pytest fixtures during the audit harvest.

> Section lists below are **provisional** — each page's grilling session may add, merge,
> or cut sections. The page list and phase order are settled.

## Writing style and tone

Rules for all prose on the docs site (drafts are checked against these in REVISE):

- **NEVER use em-dashes (—) or en-dashes (–) as punctuation.** Restructure the sentence,
  or use a comma, colon, parentheses, or a separate sentence instead.
- **Friendly and informal, but authoritative.** Write like a knowledgeable labmate
  explaining the tool at the whiteboard: relaxed language, contractions are fine, the
  occasional aside is fine. But when describing how things work or should be done, state
  it plainly and confidently. No hedging ("should probably", "it seems") about behavior
  we have verified, and no false uncertainty for politeness.
- **Address the reader as "you"**, describe the project's choices as "we".
- **Terminology comes from `CONTEXT.md`**, capitalized terms used consistently.
- Prefer short sentences and concrete examples over abstract description. Every feature
  explanation should reach a runnable snippet or a screenshot quickly.

**Screenshots.** Use them generously, especially anywhere UI behavior is being described.
While drafting, do not block on the image existing: insert a clearly marked placeholder
that spells out exactly what the screenshot must show, e.g.

```markdown
:::{admonition} 📸 SCREENSHOT NEEDED
:class: attention
Parameter Manager GUI with the profile dropdown open, two profiles visible,
one parameter starred. Annotate the star column.
:::
```

Placeholders are gathered per page once the page is finalized; Marcos captures the real
screenshots and replaces the placeholders. A page section can reach `[x]` with
placeholders still in, but Phase 6 closeout requires zero placeholders on the site.

Screenshot conventions (decided during Phase 2):

- Files live in `docs/_static/` in subfolders mirroring the docs tree:
  `_static/<section>/<page>/<what>_{light,dark}.png`.
- Every screenshot is captured twice, app in light and dark theme, and embedded as a
  pair of `{image}` directives with the theme's `only-light` / `only-dark` classes, so
  the site shows the variant matching the reader's theme toggle.
- Placeholder admonitions spell out both file paths and carry the ready-to-uncomment
  image block next to them.
- Old screenshots inherited from the previous site stay in `_static/` root until their
  page is reworked; each is checked against the current UI in its page's VERIFY step.

---

## Site structure (settled)

```
docs/
├── index.md                      — landing page
├── about.md
├── getting_started/
│   ├── index.md
│   ├── installation.md           — tabbed: uv (recommended) / pip / conda; PyPI note
│   ├── quickstart.md             — server + dummy instrument + first client call
│   └── how_it_works.md           — conceptual overview; home of the flow animation
├── user_guide/
│   ├── index.md
│   ├── client.md                 — Python Client (first page; most-used interface)
│   ├── server.md
│   ├── gui_features.md
│   ├── parameter_manager.md
│   ├── client_station.md
│   ├── monitoring.md
│   ├── configuration.md
│   └── advanced/
│       ├── subclient.md            — developer guide to live Broadcast subscriptions
│       ├── virtual_instruments.md
│       └── chaining_servers.md
├── technical_guide/
│   ├── index.md
│   ├── architecture.md
│   ├── blueprints_and_proxies.md
│   ├── broadcasts.md
│   └── custom_widgets.md
└── api/
    └── index.md                  — pure autosummary, all public modules
```

Removed: `examples/` (cut — no good use here), hand-written API quick-navigation.
Kept out of the toctree: `docs/agents/` (excluded via `exclude_patterns` so Sphinx
doesn't warn).

Toolchain: `pydata-sphinx-theme` + MyST + autosummary + GitHub Actions → GitHub Pages,
with **`sphinx-design`** for tabs/cards and **`sphinx-copybutton`** for site-wide code
copy buttons. **`sphinx-prompt`** supplies visible, copy-safe shell prefixes, while
interactive Python examples use `pycon` prompts whose returned values are displayed but
excluded when copied. Look & feel otherwise unchanged.

---

## Phase 0 — Foundations

Small, mechanical, makes every later phase land cleanly.

- [x] Add `sphinx-design` to the docs dependency group; enable in `conf.py`
- [x] Add `sphinx-copybutton` to the docs dependency group; enable copy buttons on all
      code blocks, using the PyData-recommended `nbsphinx`-safe selector
- [x] Add `sphinx-prompt`; use prompt directives for terminal examples and `pycon` for
      interactive Python so prefixes and returned values are visible but copied code
      remains directly runnable
- [x] Add `agents/` to `exclude_patterns` in `conf.py`
- [x] Create the new directory skeleton with stub index pages (stubs marked clearly;
      nothing half-written ever sits in the nav). Each stub page carries a small
      summary of what that page will become — its scope and planned sections — so
      the skeleton doubles as a public roadmap of the site
- [x] Rewrite `index.md` landing page: honest scope statement, link cards to the four
      sections; remove the "email Marcos" warning from all pages
- [x] ~~Touch up `about.md`~~ Decided instead: `about.md` deleted; landing page links to
      the Tools for Experiments organization page externally
- [x] Create `TEST_AUDIT.md` and `test/docs_verification/README.md` (conventions)
- [x] Write `test/docs_verification/helpers.py`: server start/stop context manager
      (Dummy Instruments + optional config), client factory, Broadcast capture —
      the single canonical startup path all verification scripts use. First survey
      the existing pytest fixtures under `test/` and wrap/reuse them rather than
      invent a parallel startup path — one canonical way, not two.
      Decided in grilling: helpers provide BOTH `server()` (in-process, mirrors the
      `start_server` pytest fixture) and `server_process()` (the real CLI,
      headless, for sections about launch behavior); Broadcast capture wraps
      `SubClient` (the intended live-update path); port 5555 default,
      overridable, fail loudly if busy. All helpers smoke-tested green.
- [x] Consolidate `docs/agents/domain.md` vs `CONTEXT.md` — one glossary, not two.
      Resolved on inspection: `domain.md` defines no terms; it instructs agent
      skills to read and use `CONTEXT.md`. One glossary already
- [x] CI builds green with zero Sphinx warnings (local clean build at zero; CI runs the
      same command and will confirm on push)
- [x] Old-page teardown rule in effect from here on: when a new page lands, the old
      page it replaces is deleted in the same change (no two versions in the nav;
      `overview.md`, old `configuration.md`, `instrumentmonitoring.md` all die this way)

## Phase 1 — API Reference (easy wins; everything after can cross-link it)

- Page: `api/index.md`
  - [x] Extend autosummary to all public modules: add `params`, `gui`, `config`,
        `apps`, `testing`, `serialize`, `base` to existing four.
        Decided in grilling: also add `helpers` and `log` (13 modules total);
        `resource.py` excluded (auto-generated Qt resources, not an API). One flat
        autosummary block, modules enumerated explicitly (not a single recursive
        root), short intro prose with pointers to User/Technical Guide
  - [x] Delete the hand-written "Quick Navigation" (already references nonexistent
        classes — `monitoring.monitor.ParameterListener` et al.)
  - [x] Build and review the generated pages; fix import-time errors if any module
        breaks autodoc.
        Found: `testing/create_instrument.py` ran a module-level `InstrumentClient()`
        on import, hanging the build; orphaned (zero dependents per GitNexus) and
        buggy; deleted with Marcos's approval. Five malformed-RST docstrings fixed
        (logged in TEST_AUDIT.md). Build green, zero warnings
  - [x] Triage docstring quality: note worst offenders in the TEST_AUDIT.md docstrings
        table up front; from then on the docstring audit runs continuously as part of
        every section's AUDIT step (not a single pass).
        Decided: module-docstring gaps (11 of 13 modules) logged only, not fixed now;
        skim of public symbols logged 12 worst-offender groups

## Phase 2 — Getting Started

- Page: `installation.md`
  - [x] Grill: supported Python versions, the `--no-deps` story, environment advice.
        Decided: Python 3.11+ (same floor as latest qcodes 0.58.0; lab runs 3.11, CI
        tests 3.13); clone + editable install as the canonical flow, uv recommended;
        per-tool framing (uv: dependency of your measurement project, editable path or
        git dep; conda: one env per measurement setup, pip -e inside it; pip+venv:
        generic; the `--no-deps` aside was drafted but cut in REVISE as confusing); PyPI note as an
        honest admonition at the top. Found+fixed during VERIFY: missing
        `[tool.setuptools.package-data]` made wheels unimportable (logged in
        TEST_AUDIT.md). All four install flows + monitoring extra smoke-tested green
  - [x] Tabbed install: uv (recommended) / pip / conda; "PyPI upload in progress" note.
        Approved after revision (cut lab/CI version aside, fixed clone contradiction,
        added cd-before-clone guidance, cut `--no-deps`). AUDIT: wheel-import gap and
        entry-point docstring gap already tracked in TEST_AUDIT.md
- Page: `quickstart.md` (verification script: `verify_quickstart.py`)
  - [x] Start the server bare (no config file)
  - [x] First client connection; create a Dummy Instrument via
        `find_or_create_instrument` (grilled: `rf.Generator` as the example;
        fixed missing `*IDN?` handling in all three rf dummies so creation
        doesn't log a scary traceback; full pytest suite green after).
        AUDIT: 4 test gaps logged (bare-server-empty, find_or_create
        idempotency, rf.Generator initial values, all in TEST_AUDIT.md);
        find_or_create_instrument docstring blemish logged
  - [x] Get/set a parameter; observe the Broadcast (grilled: observed via the
        GUI updating live, Broadcast name-dropped and linked, no SubClient code).
        AUDIT: end-to-end Broadcast path (live server set → SubClient receive)
        has no pytest coverage; logged as strongest integration-test candidate
  - [x] Starting with a config file (the same setup, declared in YAML; grilled:
        generator + Parameter Manager with its custom GUI; config committed as
        quickstartConfig.yml next to the verification script). REVISED: cut the
        Parameter Manager from the example (deferred to its own page); custom-GUI
        capability now a note linking gui_features.md. AUDIT: server-from-config
        end-to-end instrument creation untested (mocks only); logged
  - [x] Where to go next (links into User Guide; nothing to verify, no audit)
- Page: `how_it_works.md` — conceptual overview; no page-specific verification script
  by decision. Final shape: a brief statement of the shared-hardware problem, the
  approved eleven-step scrollytelling diagram, and four short sections that supplement
  the visual with conceptual context rather than transcribing it. Implementation details
  are deferred to `technical_guide/architecture.md`.
  - [x] **The Server owns the instrument:** explain the real QCoDeS driver's lifetime,
        the Server's authoritative ownership, and configuration versus runtime creation.
  - [x] **The Client builds a Proxy Instrument:** distinguish the Client, Blueprint, and
        Proxy roles; explain that a Proxy provides the local interface but is not a copy
        of the real instrument or its state.
  - [x] **A call reaches the hardware:** explain the Proxy's request/result interaction,
        Server-side execution, and fresh parameter reads without implementation machinery.
  - [x] **A Broadcast reaches subscribers:** distinguish direct calls from observation by
        the Server GUI and Listener; close with the Technical Guide pointer. AUDIT:
        existing and newly identified test/docstring gaps recorded in `TEST_AUDIT.md`.

## Phase 3 — User Guide core

- Page: `client.md` (page title: **Python Client**; verification: `verify_client.py`)
  - [x] **Connect and get an instrument** (verified, tested, built, visually checked,
        and audited). Decided: make the
        section a focused Python Client API walkthrough, not another system overview:
        establish a Client session, inspect the Server's instruments, obtain one usable
        Proxy Instrument, and disconnect. Keep system concepts brief and cross-link the
        Quickstart and `how_it_works.md` for their fuller treatments. Renamed from the
        vague `basic_usage.md` to `client.md`, with the page title **Python Client**.
        To keep the walkthrough fully followable, create its example instrument inline
        with `find_or_create_instrument`; do not require readers to arrive with a preloaded
        Server just to avoid repeating the one-line creation from the Quickstart.
        Start the Server with its GUI (`instrumentserver`) so readers can watch the
        instrument appear. Teach a long-lived `Client` as the primary measurement
        pattern, ending with `disconnect()`; show the context manager briefly as the
        secondary pattern for short scripts. Use `rf.Generator` for this opening
        walkthrough and continue using it for parameter examples. Keep and use the Proxy
        returned by `find_or_create_instrument`; mention `get_instrument` only as the
        alternative when the named instrument already exists, rather than constructing
        a redundant second Proxy in the walkthrough. Spell out `host="localhost"` and
        `port=5555` in the Client example, then note that both are defaults and link to
        `server.md` for addresses and ports. Start with the explicit real CLI spelling
        `instrumentserver -p 5555 -a 127.0.0.1`; note that both values are defaults and
        that `-a` adds listening addresses while loopback is always included. Reuse the
        Quickstart's existing `server_generator_{light,dark}.png` success-state images;
        reference the shared assets directly rather than creating duplicate screenshots.
        Explain that `find_or_create_instrument` intentionally mirrors QCoDeS' method of
        the same name and link its API documentation. Its lookup is name-based: when the
        name exists, it returns a Proxy for that instrument without validating the class
        path supplied for creation. Add a note that constructing `Client` opens the ZMQ
        connection but does not handshake with the Server; the first request confirms
        communication. Keep timeout and reconnection details in their later section
  - [x] **Use a Proxy Instrument** (verified, tested, built, and audited). Retain a compact nested-submodule
        lesson because Blueprints reproduce the driver's hierarchy and users call nested
        parameters and methods through the same Proxy interface. Use
        `DummyInstrumentWithSubmodule` to verify access through `A.ch0` and
        `A.dummy_function`. Document `update()` exactly: it fetches a fresh Blueprint,
        synchronizes parameters and submodules, and adds newly reported methods, but does
        not remove method objects already installed on the Proxy. Verify additions and
        removals against a mutable test instrument and leave stale method removal as a
        separate product improvement. Make the interaction self-contained by showing
        callable parameter get/set and a
        realistic method call: continue with `rf.Generator` for parameters, then create
        `rf.ResonatorResponse` and call `modulate_frequency(delta=1e6)`. State that the
        interface is native QCoDeS behavior: `ProxyParameter` is a QCoDeS `Parameter`
        whose get/set commands call the Server. Show the familiar callable form, mention
        explicit `.get()`/`.set()` without treating either syntax as instrumentserver-specific
        and link the relevant QCoDeS instrument documentation, but do not teach validators,
        snapshots, or general driver authoring here. Retain the custom-serialization
        contract because values used by Proxy Parameters and methods must cross the wire.
        The agreed example uses importable `SweepRequest` and `SweepResult` dataclasses
        with a `ClassVar` named `attributes`, plus an Analyzer method that accepts the
        request and returns the result. Verify built-in transport types, `FieldVector`
        identity boundaries, the complete custom request/result flow, import and
        constructor requirements, non-recursive custom-object and NumPy-field limits,
        tuple/set conversion, top-level versus nested Enum behavior, and numeric-string
        coercion. Audit every executable claim into permanent pytest coverage.
        Completed with focused Client, serialization, Enum, and `FieldVector`
        identity tests
  - [x] **Animate the Proxy Instrument lifecycle.** Decided: add a conceptual
        scrollytelling diagram in the style of `how_it_works.md`. Follow the full
        lifecycle from the Server's Blueprint through local Proxy construction, then
        follow a `FieldVector` parameter set and get across the process boundary. Show
        serialization and deserialization explicitly, but keep wire fields and protocol
        details for `technical_guide/blueprints_and_proxies.md`. Close with a brief note
        that supported values work automatically and custom classes must follow the
        requirements documented below the animation. VERIFY: the page script now checks
        the Blueprint response codec and a live `FieldVector` Proxy Parameter round trip
        with distinct Python objects in both processes. DRAFT: ten-step animation added
        and clean Sphinx build passes with zero warnings. Preliminary AUDIT: lifecycle
        behavior has pytest coverage; the pre-existing `FieldVectorIns` IDN traceback is
        recorded in `TEST_AUDIT.md`. REVISION: moved the animation to the end of the
        Proxy Instrument section so the concepts come first. GRILLED REVISION: the
        eleven-step story now begins with `cli.get_instrument("magnet")`, distinguishes the
        Client, Proxy, Server dispatcher, and real QCoDeS driver, then follows explicit
        `FieldVector` creation, set, driver handoff, set response, get, and return events. The script or
        notebook and InstrumentServer are the two outer regions. Serialization appears
        only as transient messages crossing the ZMQ lane, not as persistent serializer
        objects. Structural objects remain visible after introduction at 55% opacity
        when inactive; only messages disappear. Each relationship has one bidirectional
        route whose active arrow and motion show the current direction. The read action
        hides the earlier target card and leaves the Server-owned current value and newly
        reconstructed returned value visible; its closing text still identifies the
        original target as a third distinct object. The real driver starts with a visible
        zero-valued `FieldVector`; the reconstructed set value moves over and replaces it
        in the driver during Step 7. The continuous diagram is split
        into three labelled actions: create the Proxy Instrument, set the value, and read
        the value. The clean build succeeded. Marcos accepted the animation at page
        closeout and waived the unavailable in-browser review
  - [x] **Save and restore parameter values** (verified, tested, built, and audited; VERIFY found tracked bug
        [#152](https://github.com/toolsforexperiments/instrumentserver/issues/152)).
        Decided: do not invent a
        "batch API" concept. Organize the existing Client methods around one experiment
        state workflow: collect values with `getParamDict`, apply a parameter dictionary
        with `setParameters`, save selected instruments to JSON with `paramsToFile`, then
        change and restore them with `paramsFromFile`. VERIFY against a real Server
        established that `getParamDict` returns flat dotted paths and `setParameters`
        accepts that flat form, while `paramsToFile` writes nested JSON and
        `paramsFromFile` flattens it internally. Show both shapes; warn that passing the
        nested file object directly to `setParameters` is silently ignored. Make clear
        that these Client methods work with any existing Server-owned
        instrument and read/write files on the Client's filesystem. Contrast them with
        `ParameterManager.toFile`/`fromFile`, which execute on the Server, manage profile
        files, preserve units, and can create or remove hierarchical parameters. Found a
        blocking correctness bug: native JSON booleans become `0.0`/`1.0` in
        `deserialize_obj`, so Boolean values fail validation and are not restored by
        `setParameters` or `paramsFromFile`. Do not claim complete type round-tripping
        until that tracked-code bug is fixed and the verification is rerun
  - [x] **Handle errors and timeouts** (verified, tested, built, and audited). Decided:
        do not describe the
        behavior as automatic reconnection. A timed-out request raises by default and
        is not retried; the Client replaces its ZMQ socket so a later request can work
        after the Server becomes available. `disconnect()` permanently closes that
        Client instance. Mention `raise_exceptions=False` as the logging/`None` behavior,
        not as the primary pattern. Add a prominent warning that timeout means "no reply
        before the deadline," not "the Server did not execute": the worker continues,
        so check instrument state before retrying a non-idempotent hardware operation.
        Include two runnable examples: an out-of-range RF Generator set showing how a
        Server-side validation error reaches the Client, and a deliberate call to
        `DummyInstrumentTimeout` showing the timeout followed by a successful later call.
        VERIFY confirmed the validation failure arrives as a generic `Exception`;
        a 0.2-second timeout raised at about 0.201 seconds, the Server method continued
        exactly once, and the same Client's later request succeeded on its replacement
        socket. Fixed during DRAFT: `DummyInstrumentTimeout` now answers `*IDN?`, with a
        regression test, so the documentation example starts cleanly. Present
        `raise_exceptions=False` only in a cautionary note for long-running UI
        infrastructure with its own error reporting; normal measurement code keeps the
        default because logged failures generally return ambiguous `None`
- Page: `server.md` (verify_server.py)
  - [ ] Starting: GUI / headless / CLI flags / addresses & ports
  - [ ] Detached GUI: what it's for (UI faults can't kill the Server)
  - [ ] Instruments from config vs **programmatic creation** (core feature, up front)
        and init scripts
  - [ ] External broadcast: mention + what it enables (live UIs); link to broadcasts.md
- Page: `gui_features.md` (verify where scriptable; GUI behavior verified manually)
  - [ ] Shared concepts: star / trash / hide / filter patterns
  - [ ] Keyboard shortcuts: defaults, customizing via config (post-#138 behavior)
  - [ ] Detachable tabs
  - [ ] Custom instrument widgets: mention + config hook; link to custom_widgets.md
- Page: `parameter_manager.md` (verify_parameter_manager.py)
  - [ ] Concept: the flagship Virtual Instrument; single source of truth
  - [ ] Hierarchical parameters: add / remove / nesting
  - [ ] Persistence: JSON files; profiles (refresh / switch)
  - [ ] The Parameter Manager GUI + `instrumentserver-param-manager` launcher
  - [ ] Using it from measurement code

## Phase 4 — User Guide completion

- Page: `client_station.md` (verify_client_station.py)
  - [ ] Concept: scoped views of one shared Server (the "sub-server" idea, properly named)
  - [ ] YAML config; parameter save/load paths
  - [ ] The Client Station GUI + `instrumentserver-client-station` launcher
  - [ ] Auto-reconnect behavior
- Page: `monitoring.md` (verify_monitoring.py)
  - [ ] Concept: Broadcasts → Listener → sink → dashboard
  - [ ] Polling: making the Server emit without client activity (`pollingRate`)
  - [ ] The Listener app + listenerConfig; CSV sink; InfluxDB sink
  - [ ] Writing a custom Listener
  - [ ] The deployment stack: Docker compose, Grafana + InfluxDB, provisioning,
        dashboards, alerting (absorbs existing instrumentmonitoring.md after
        re-verification)
- Page: `configuration.md` (verify_configuration.py)
  - [ ] File anatomy: every top-level section
  - [ ] Instruments section; gui kwargs; glob patterns
  - [ ] gui_defaults merge order (`__default__` → class → instance)
  - [ ] shortcuts / pollingRate / networking sections
- Page: `advanced/subclient.md` (verify_subclient.py)
  - [ ] Concept and audience: an instrumentserver developer building a live UI or
        another Broadcast-driven component, not ordinary request/reply Client usage
  - [ ] Correct Qt worker-thread lifecycle: construct, move, connect signals, start,
        stop, and clean up without blocking the caller
  - [ ] Subscribe to all instruments or filter by instrument name; handle the
        `ParameterBroadcastBluePrint` emitted by `update`
  - [ ] Link to the Technical Guide for PUB/SUB mechanics and message internals
- Page: `advanced/virtual_instruments.md` (verify_virtual_instruments.py)
  - [ ] Concept (vs Dummy Instruments — see CONTEXT.md)
  - [ ] Writing your own Virtual Instrument
- Page: `advanced/chaining_servers.md` (verify_chaining_servers.py)
  - [ ] Concept: a Server as a Client of another Server
  - [ ] Working setup walkthrough (promote the `instruments_all_the_way_down`
        prototype into a verified, documented configuration)
  - [ ] Limits and gotchas

## Phase 5 — Technical Guide

- Page: `architecture.md` — `how_it_works.md`'s deeper twin (verification script:
  `verify_architecture.py`)
  - [ ] ROUTER/DEALER request path; thread pool; per-instrument locks
  - [ ] PUB/SUB broadcast path; ports (request port, port+1)
  - [ ] Request lifecycle walkthrough (set-parameter end to end)
  - [ ] Process layout: server / detached GUI / clients / listeners
- Page: `blueprints_and_proxies.md` (verify_blueprints_and_proxies.py) — the round trip
  as one story
  - [ ] Server side: introspection → Blueprint
  - [ ] The wire: serialization of blueprints and values
  - [ ] Client side: Blueprint → dynamic proxy (methods, signatures, submodules)
  - [ ] Blueprint caching and invalidation
- Page: `broadcasts.md` (verify_broadcasts.py)
  - [ ] What triggers a Broadcast; message format
  - [ ] SubClient mechanics; how GUIs stay live
  - [ ] External broadcast forwarding (deep dive promised by server.md)
- Page: `custom_widgets.md`
  - [ ] How `gui.type` resolves to a widget class; the widget contract
  - [ ] Writing and registering your own (worked example)
- [ ] Remaining flow animations (per prototype learnings from Phase 2)

## Phase 6 — Closeout

- [ ] Remove the under-construction warning entirely
- [ ] All 📸 screenshot placeholders replaced with real images (zero remain on the site)
- [ ] Full-site read-through: terminology pass against `CONTEXT.md`; link check
- [ ] Harvest `TEST_AUDIT.md`: every entry either has a test, a tracked issue, or a
      written reason it needs neither
- [ ] Delete `test/docs_verification/` (end-of-process cleanup, as agreed)
- [ ] Drop unused docs deps if confirmed unused (e.g. notebook extensions, post-Examples cut)
- [ ] Rewrite `README.md`: short project pitch, install summary, prominent link to the
      docs site (currently it only says "use a developer pip install")
- [ ] Coordinate with labcore: its `user_guide/instruments/instrumentserver.md` and
      `instrumentmonitoring.md` duplicate content (and screenshots) now owned by this
      site; shrink them to links so they don't become the new stale copy

---

## Out of scope (deliberately)

- **PyPI publishing** — wanted, but a separate later effort; installation.md carries an
  "in progress" note.
- **Examples section** — cut; this project doesn't use examples well.
- **URL redirects** from the old structure — site is young; clean break.
- **Look & feel changes** — theme, logo, nav style all stay.
- **`docs/agents/`** — untouched except glossary consolidation (Phase 0).

## Standing risks / notes

- GUI-heavy sections (gui_features, the GUI parts of each app page) can't be fully
  script-verified; those get manual verification noted in the verification script as
  comments, and screenshots regenerated so images match current UI.
- Screenshots in `docs/_static/` are inherited from the old site — every reused image
  must be checked against the current UI in its page's VERIFY step.
- Animation approach is unproven until the Phase 2 prototype; don't reference animations
  from other pages before it lands.
