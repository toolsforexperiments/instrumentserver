# 0.1 — reviewer-qwen — round 0

Verdict: approve

## Findings

No findings. The implementation correctly splits `ParameterGroup` out of `ParameterManager`.

## Notes

- Tests run: `uv run pytest test/pytest/test_param_manager.py` — 12 passed.
- The new `ParameterGroup` class holds:
  - Tree helpers (`_get_param`, `_get_parent`, `has_param`, `parameter`, `to_tree`, `list`, `remove_empty_submodules`)
  - Dotted-path methods (`add_parameter`, `remove_parameter`, `get`, `set`)
  - No file, profile, Type or Lock logic
- `ParameterManager` now extends `ParameterGroup`, keeping:
  - Working directory, profiles, file persistence (`fromFile`, `toFile`, `fromParamDict`, `toParamDict`)
  - Profile management (`refresh_profiles`, `switch_to_profile`, `remove_all_parameters`)
- `_to_tree` assertion changed from `isinstance(sm, ParameterManager)` to `isinstance(sm, ParameterGroup)` at line 76.
- `_get_parent(..., create_parent=True)` creates `ParameterGroup(n)` at line 109.
- Two new tests added:
  - `test_submodules_are_groups`: verifies submodules are `ParameterGroup` not `ParameterManager`.
  - `test_submodule_does_not_load_parameter_file`: verifies parameter files are not loaded into submodules.
- Acceptance criteria met:
  - Creating `q01.IF` no longer lists the working directory or logs "parameter file not found".
  - `isinstance(pm.q01, ParameterGroup)` is `True` and `isinstance(pm.q01, ParameterManager)` is `False`.
