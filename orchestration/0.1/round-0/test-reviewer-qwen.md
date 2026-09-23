# 0.1 — test-reviewer-qwen — round 0

Verdict: approve

## Findings

### F1 — should-fix
- Where: test/pytest/test_param_manager.py:222
- What: Test `test_submodule_does_not_load_parameter_file` asserts `not isinstance(params.q01, ParameterManager)` but does not explicitly verify the `q01` submodule is a `ParameterGroup`.
- Why: The acceptance criteria in task 0.1 requires that submodules be `ParameterGroup` instances. The test should assert both types explicitly to match the pattern in `test_submodules_are_groups`.
- Suggested fix: Add `assert isinstance(params.q01, ParameterGroup)` at the start of the test.

### F2 — nit
- Where: src/instrumentserver/params.py:235
- What: `ParameterManager.__init__` calls `refresh_profiles()` and `fromFile()` unconditionally, but `ParameterGroup` has no such logic.
- Why: The plan task states submodules should not list the working directory or load files. This behavior is already preserved because only `ParameterManager.__init__` (not `ParameterGroup.__init__`) calls these methods; `ParameterGroup` has no `__init__` and `super().__init__` is never invoked on a `ParameterGroup` instance directly in production code. No change is needed, but adding a clarifying comment in `ParameterGroup` would improve maintainability.
- Suggested fix: Add a comment above `class ParameterGroup` noting that it intentionally has no `__init__` to avoid file/profile logic, and that submodules are created via `_get_parent(..., create_parent=True)` using only `ParameterGroup(n)`.

## Notes
All tests in `test/pytest/test_param_manager.py` pass (12 tests, including the two new ones). The full suite passes (161 tests). The implementation correctly splits `ParameterGroup` out of `ParameterManager`, making submodules plain containers without file/profile logic, and `isinstance(pm.q01, ParameterGroup)` holds while `isinstance(pm.q01, ParameterManager)` does not.
