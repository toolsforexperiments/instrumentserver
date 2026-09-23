# 0.1 — test-reviewer-deepseek — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/test_param_manager.py:220 (test_submodules_are_groups)
- What: The "no longer lists the working directory" half of the first acceptance item is only proven transitively through `isinstance(params.q01, ParameterGroup)`, never asserted directly.
- Why: The caplog assertion (`"parameter file not found" not in caplog.text`) covers only the logging clause of the acceptance, not the working-directory listing clause. A hypothetical regression that re-introduced `refresh_profiles()` (listdir) on submodule creation without the `fromFile()` log would slip past both assertions. The plan acceptance reads "creating `q01.IF` no longer lists the working directory or logs 'parameter file not found'".
- Suggested fix: assert directly that creating a submodule does not touch the working directory — e.g. `monkeypatch` `os.listdir` and assert it is not called (or is called only by the root's own `refresh_profiles`) while running `add_parameter("q01.IF", ...)`, or assert `params.profiles` is unchanged by submodule creation.

### F2 — nit
- Where: test/pytest/test_param_manager.py:220 (test_submodules_are_groups)
- What: The test runs in the repo's real cwd rather than an isolated `tmp_path`.
- Why: `caplog.clear()` then asserting no "parameter file not found" is emitted depends on there being no `parameter_manager-q01.json` in cwd. If such a file is ever present, the log assertion becomes vacuous (no warning is logged because the file exists), leaving only the isinstance assertion to catch a regression. The sibling test (`test_submodule_does_not_load_parameter_file`) already shows the isolated pattern via `monkeypatch.chdir(tmp_path)`.
- Suggested fix: `monkeypatch.chdir(tmp_path)` (and optionally `monkeypatch.chdir` to a fresh dir) at the top of the test so the caplog assertion is environment-independent.

## Notes
- Both plan-named tests are present and meaningful. `test_submodules_are_groups` would fail on the pre-split code (old `_get_parent` built `ParameterManager(n)` submodules, so `isinstance(q01, ParameterGroup)` is False and submodule `fromFile()` logs "parameter file not found"). `test_submodule_does_not_load_parameter_file` would also fail on old code: the old submodule `ParameterManager("q01")` would load `parameter_manager-q01.json` whose key `q01.file_param` matches its name filter, making `has_param("file_param")` True. Both new tests are local unit tests, matching the plan's `test_param_manager.py` layer (unit, no server).
- The plan's method-split list is respected in the covered behaviour: `ParameterGroup` carries the tree helpers, `ParameterManager` keeps profiles/files/workingDirectory, `_get_parent(create_parent=True)` creates `ParameterGroup(n)`, and the `_to_tree` assertion is `ParameterGroup`. (Plan-conformance detail; flagging only to confirm nothing about tests conflicts.)
- No existing test was weakened, deleted or skipped.
- Tests run:
  - `uv run pytest test/pytest/test_param_manager.py` → `12 passed in 5.15s`. The two new tests are the only additions; all 10 pre-existing tests pass unchanged.
  - `uv run pytest` → `1 failed, 160 passed` — the single failure `test_server_gui.py::test_loading_button` is `ZMQError: Address already in use (addr='tcp://127.0.0.1:5555')`, a port-fixed collision between server-bound test modules in the same session. It passes in isolation (`1 passed in 5.37s`) and is unrelated to this commit (`test_param_manager.py` uses no server and never binds 5555).