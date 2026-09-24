# 0.4 — test-reviewer-deepseek — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/test_apps.py:355, :386 (the two param-manager launcher tests)
- What: The two launcher unit tests pass an already-integer port (4567) directly through `sys.argv`, so they exercise the argparse parser only for `sub_port = args.port + 1` behaviour (asserting `sub_port=4568`), not the string-to-int conversion itself.
- Why: This is a harmless gap. If `--port` stayed a string, `args.port + 1` would yield `"45671"` and both asserts would still fail, so the tests do catch a missing `type=int`. The coder's `type=int` addition is a judgment call outside the plan's literal wording, but it is effectively required for `args.port + 1` to work and the existing asserts would catch its regression. Not worth sending to the coder.
- Suggested fix: none.

## Notes
- Plan task 0.4 requires exactly the three things implemented: (1) `kwargs.get("initial_value")` / `kwargs.get("unit", "")` in `_newOrDeleteParameterDetection` (src/instrumentserver/server/core.py:627-631); (2) `sub_port=args.port + 1`, `sub_host="localhost"` into `ParameterManagerGui` (src/instrumentserver/apps.py:146-152); (3) the named tests — `test_apps.py` extended (asserts `sub_port=4568, sub_host="localhost"` in both launcher paths) and the new proxy test in `test_param_manager.py`.
- New proxy test `test_add_parameter_without_initial_value_succeeds_and_broadcasts`: correct layer (uses the `param_manager` proxy fixture over the real server plus a `SubClient` on `server_port + 1`), and meaningful — without the fix the server-side `kwargs["initial_value"]` raises a `KeyError` inside `_invoke()`, breaking the client call, so the test fails against the old code. It asserts parameter existence, exactly one broadcast, `name == "parameter_manager.x"`, `action == "parameter-creation"`, `value is None`, `unit == ""`.
- Broadcast port convention matches production: the server binds `port` for requests and broadcasts on `port + 1` (conftest `server_port` docstring), so `sub_port=server_port + 1` is correct.
- Tests run: `uv run pytest test/pytest/test_apps.py test/pytest/test_param_manager.py -q` → 31 passed in 12.28s.