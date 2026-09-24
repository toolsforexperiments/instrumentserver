# 0.4 — plan-checker-qwen — round 0

Verdict: approve

## Findings

(None.)

## Notes

- Commit 56ece34 is a single commit touching exactly the four files task 0.4 names:
  `src/instrumentserver/apps.py`, `src/instrumentserver/server/core.py`,
  `test/pytest/test_apps.py`, `test/pytest/test_param_manager.py`. Commit message
  starts with `0.4:` per session protocol step 6.

- **Acceptance, point by point** (task text: "0.4 Pre-existing fixes (D24, first two)"):
  1. `_newOrDeleteParameterDetection` now uses `kwargs.get("initial_value")` and
     `kwargs.get("unit", "")` (server/core.py:629-630) — exactly as specified.
  2. `parameterManagerScript` passes `sub_port=args.port + 1, sub_host="localhost"`
     into `ParameterManagerGui` (apps.py:149) — exactly as specified. I verified the
     kwargs are real: `ParameterManagerGui.__init__` forwards `**kwargs` to
     `InstrumentParameters`, which pops `sub_host`/`sub_port` into `ModelParameters`,
     which hands them to `SubClient` (gui/instruments.py:413-424, 555-558).
  3. Both existing param-manager launcher tests in `test_apps.py`
     (`test_param_manager_script_instrument_exists`,
     `test_param_manager_script_instrument_missing`) are extended to assert
     `mock_pmg.assert_called_once_with(mock_pm, sub_port=4568, sub_host="localhost")`
     for `--port 4567`.
  4. The named proxy test exists:
     `test_add_parameter_without_initial_value_succeeds_and_broadcasts` in
     `test_param_manager.py`, using the `param_manager` proxy fixture against the live
     server. It calls `params.add_parameter("x")` with no `initial_value`/`unit`, asserts
     success, exactly one Broadcast, and `bp.action == "parameter-creation"`,
     `bp.value is None`, `bp.unit == ""`.

- **The `type=int` judgment call is in scope, not scope creep.** Task 0.4 specifies
  `sub_port=args.port + 1`; argparse without `type=` yields a string for a CLI-passed
  `--port`, so `args.port + 1` would raise `TypeError` (and the task's own tests use
  `--port 4567` and assert the int `sub_port=4568`, which cannot pass without it). The
  change is the minimum needed to make the specified expression work, matches
  `Client.__init__(port: int)` (client/proxy.py:453), and touches only the
  `parameterManagerScript` parser — `serverScript`, `detachedServerScript` and
  `clientStationScript` keep their existing string-port behaviour, which rule 6 ("Do
  not widen scope. Pre-existing defects not listed in Phase 0 are noted in
  `TEST_AUDIT.md`, not fixed.") requires leaving alone. The pinned test
  `test_server_script_passthrough_args` still asserts `kwargs["port"] == "9999"` and
  passes.

- **D24 item three untouched.** `ParameterManagerTreeView.onItemNewValue`
  (gui/instruments.py) is not modified — correct, it belongs to task 5.1 ("Fix D24 item
  three: `ParameterManagerTreeView.onItemNewValue` uses `widget._setMethod(value)`").
  No work from other tasks appears in the commit.

- **The proxy test can fail on unfixed code.** Before the fix, `kwargs["initial_value"]`
  raised `KeyError` after `obj(*args, **kwargs)` in `_invoke()`, so the server answered
  with `ServerResponse(error=...)` and `BaseClient.ask` (default
  `raise_exceptions=True`) would raise from `params.add_parameter("x")`. The new test
  therefore fails pre-fix and passes post-fix; it is a genuine regression test, and it
  also pins the wire format (value serialises as `"None"` → `None` on
  deserialisation; `""` round-trips as `""` — verified against
  `bluePrintToDict`/`deserialize_obj` in blueprints.py).

- **Vocabulary.** New test names, docstrings and comments use "Broadcast" / "Broadcasts"
  per CONTEXT.md; the helpers `capture_broadcasts` / `wait_for_broadcasts` mirror the
  identically named helpers already committed in task 0.3's `test_broadcaster.py`.
  Action string `"parameter-creation"` stays a literal, as D10 requires ("Action strings
  stay strings; module-level constants for all actions" — the constants are task 0.5).

- **Decisions and ADRs.** Consistent with ADR-0003 ("Direct `add_parameter` /
  `remove_parameter` calls keep being announced by the Server"), D24, and D27 (the
  SubClient port comes from the `server_port` fixture, `server_port + 1`, never a fixed
  port). Rule 7 protected APIs: no signature or behaviour change to `add_parameter` or
  any other listed method.

- **Tests run.**
  - `uv run pytest test/pytest/test_apps.py test/pytest/test_param_manager.py -v` →
    `31 passed in 12.47s`.
  - `uv run pytest` (whole suite) → `174 passed, 4 warnings in 68.71s`. The 4 warnings
    are pre-existing `PytestUnknownMarkWarning`s for `@pytest.mark.integration` in
    `test_apps.py`, unrelated to this commit.
