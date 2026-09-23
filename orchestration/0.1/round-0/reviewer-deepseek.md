# 0.1 — reviewer-deepseek — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/test_param_manager.py:220
- What: `test_submodules_are_groups` asserts only the "logs 'parameter file not found'" half of the acceptance clause; it never observes "no longer lists the working directory".
- Why: The acceptance reads "creating `q01.IF` no longer lists the working directory **or** logs 'parameter file not found'". Listing the working directory (calling `refresh_profiles()`) is not directly observable from outside a `ParameterGroup` (it has no `.profiles`), and the second added test (`test_submodule_does_not_load_parameter_file`) already proves no file logic runs on a submodule, so the clause is covered by construction. Not a real gap, hence nit.
- Suggested fix: none strictly needed; if desired, the docstring/comment could note the directory-listing clause is covered inductively via `test_submodule_does_not_load_parameter_file`.

## Notes

- The split matches the plan (task 0.1 / D15 / D26): all listed tree helpers (`_get_param`, `_get_parent`, `has_param`, `parameter`, `to_tree`/`_to_tree`, `list`, `remove_empty_submodules`, dotted `add_parameter`/`remove_parameter`/`get`/`set`) live in `ParameterGroup`; `ParameterManager(ParameterGroup)` keeps `workingDirectory`, profiles, files, `createFromParamDict`, `remove_all_parameters`. `_get_parent(..., create_parent=True)` builds `ParameterGroup(n)` (params.py:109); `_to_tree` asserts `isinstance(sm, ParameterGroup)` (params.py:76). Acceptance `isinstance(pm.q01, ParameterGroup)` and not `ParameterManager` is satisfied and asserted.
- Both required tests were added and are meaningful regression tests: `test_submodule_does_not_load_parameter_file` would have failed before the change (a full `ParameterManager('q01')` would have loaded `parameter_manager-q01.json` and populated `file_param`).
- External callers of `ParameterManager` are unaffected: the public API surface (add_parameter/remove_parameter/list/get/set/has_param/parameter/to_file/from_file/switch_to_profile/refresh_profiles/list_profiles/to_tree/remove_all_parameters/remove_empty_submodules) is inherited unchanged; src/qodex callers (gui/instruments.py, apps.py, client/proxy.py) only construct/reference the root `ParameterManager`.
- Tests run:
  - `uv run pytest test/pytest/test_param_manager.py -q` → `12 passed`.
  - `uv run pytest -q` → `160 passed, 4 warnings, 1 error`. The single error is a **setup error** for `test/pytest/test_param_manager.py::test_param` ("Exceptions caught in Qt event loop", with a `serialize.py` TypeError `'1.0 is not an int; Parameter: cs_dummy.int_param1'`). It originates during dummy-instrument serialization in `serialize.py` inside the `param_manager` fixture's server startup and is unrelated to this commit's files; I did not re-run the base to confirm pre-existence since running the base requires a write-outside-repo git worktree (disallowed).