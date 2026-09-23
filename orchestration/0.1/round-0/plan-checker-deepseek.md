# 0.1 — plan-checker-deepseek — round 0

Verdict: approve

Reviewed commit `46e34cd` ("0.1: split ParameterGroup out of ParameterManager") in `447c7f7..46e34cd` against PLAN_parameter_manager_redesign.md, CONTEXT.md, ADR-0001/0002/0003. The commit touches exactly `src/instrumentserver/params.py` and `test/pytest/test_param_manager.py` — nothing out of scope.

## Findings

No must-fix or should-fix findings.

### N1 — nit
- Where: src/instrumentserver/params.py:99,102
- What: `_get_parent` still accumulates `full_name` (lines 99, 102) but never uses it.
- Why: Pre-existing dead code carried over unchanged when the method moved into `ParameterGroup`; not introduced by this commit and not a plan violation.
- Suggested fix: Drop the `full_name` bookkeeping when next touching the method. Orchestrator need not forward.

## Notes

Plan-task compliance, line by line:
- `ParameterGroup(InstrumentBase)` created at params.py:59 holding all 12 listed tree helpers: `_to_tree` (:72), `to_tree` (:82), `_get_param` (:85), `_get_parent` (:93), `has_param` (:115), `add_parameter` (:122), `remove_parameter` (:149), `get` (:156), `set` (:160), `remove_empty_submodules` (:164), `parameter` (:184), `list` (:192). ✓
- `ParameterManager(ParameterGroup)` (:208) keeps profiles, files and `workingDirectory` (`__init__` :227, property :239, `refresh_profiles` :291, `fromFile`/`fromParamDict`/`toFile`/`toParamDict` :311-442). No Types/Locks yet — correct for Phase 0.1. ✓
- `_get_parent(..., create_parent=True)` creates `ParameterGroup(n)` (:109). ✓
- `_to_tree` assertion changed to `isinstance(sm, ParameterGroup)` (:76); recursion via `cls._to_tree(sm)` still walks nested groups. ✓
- Acceptance: a `ParameterGroup` has no `refresh_profiles()` and no `fromFile()`, so creating `q01.IF` triggers no `os.listdir(workingDirectory)` and no "parameter file not found" warning, and `isinstance(pm.q01, ParameterGroup)` is True while `isinstance(pm.q01, ParameterManager)` is False — covered by `test_submodules_are_groups` (isinstance asserts + `"parameter file not found" not in caplog.text`). ✓
- Tests: `test_param_manager.py` all green unchanged; added `test_submodules_are_groups` (test file :220) and `test_submodule_does_not_load_parameter_file` (:239) which plants a `parameter_manager-q01.json` in `tmp_path` and asserts it is NOT loaded into the `q01` submodule (`not params.q01.has_param("file_param")`, `"q01.file_param" not in params.list()`, `params.q01.my_param() == 1`). ✓

API-preservation (plan way-of-working rule 7): all of `add_parameter`, `remove_parameter`, `list`, `get`, `set`, `has_param`, `parameter`, `toFile`, `fromFile`, `switch_to_profile`, `refresh_profiles`, `list_profiles`, `to_tree`, `remove_all_parameters`, `remove_empty_submodules` retain their signatures and behaviour on `ParameterManager`. ✓

Vocabulary (plan rule 2): new docstrings/comments and test names use glossary terms — "Parameter Group", "Parameter Manager", "Type", "Lock" — consistently. ✓

No other call sites in `src/` or `test/` depended on submodules being `ParameterManager` (grep for `_to_tree`, `isinstance(...ParameterManager)`, `ParameterManager(` across the tree confirms only param_manager tests construct submodules via `add_parameter`, which now yield `ParameterGroup`). ✓

Scope (plan rule 6 / session step 6): single atomic commit, single task, no out-of-scope fixes. ✓

## Tests run

- `uv run pytest test/pytest/test_param_manager.py` → `12 passed in 5.15s` (all prior tests unchanged-green plus the two new ones).
- `uv run pytest` → `161 passed, 4 warnings in 59.92s`. (A first invocation aborted with a hard PyQt interpreter crash mid-suite in a server-basing test; an immediate re-run completed all 161 green, so the crash is a transient macOS/PyQt flake, not this commit. The affected files were not touched by `params.py`.)