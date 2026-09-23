# 0.1 — plan-checker-qwen — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: N/A
- What: No issues found.
- Why: The commit correctly implements all requirements from task 0.1.
- Suggested fix: N/A

## Notes
- Tests run: `uv run pytest test/pytest/test_param_manager.py` — 12 passed in 5.20s.
- All acceptance criteria met:
  - `ParameterGroup(InstrumentBase)` created with tree helpers moved from `ParameterManager`.
  - `ParameterManager(ParameterGroup)` extends `ParameterGroup` with file, profile, workingDirectory logic.
  - `_get_parent(..., create_parent=True)` creates `ParameterGroup` instances.
  - `_to_tree` assertion changed from `ParameterManager` to `ParameterGroup`.
  - Creating `q01.IF` no longer lists working directory or logs "parameter file not found".
  - `isinstance(pm.q01, ParameterGroup)` is `True`, `isinstance(pm.q01, ParameterManager)` is `False`.
  - `test_submodules_are_groups` and `test_submodule_does_not_load_parameter_file` tests added and pass.
