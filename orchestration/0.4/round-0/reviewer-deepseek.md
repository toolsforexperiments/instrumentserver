# 0.4 — reviewer-deepseek — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/test_param_manager.py:62
- What: The `capture_broadcasts` / `wait_for_broadcasts` helpers duplicate the capture pattern already in `test_broadcaster.py`.
- Why: Pure test-side duplication; not production dead code and not in the general reviewer's lane to enforce.
- Suggested fix: Optionally factor a shared capture helper into `conftest.py` when later tasks (2.5, 3.2) also need broadcast capture. Not required for this task.

## Notes

- `_newOrDeleteParameterDetection` (server/core.py:624-631) now reads `kwargs.get("initial_value")` / `kwargs.get("unit", "")`, fixing the latent `KeyError` that D24 lists. When the args are absent the broadcast carries `value=None` / `unit=""`, which match `ParameterBroadcastBluePrint`'s own defaults (`value: int | None = None`, `unit: str = ""`).
- `apps.py:parameterManagerScript` passes `sub_port=args.port + 1, sub_host="localhost"` into `ParameterManagerGui`. Wiring verified end to end: `ParameterManagerGui.__init__` forwards `**kwargs` to `InstrumentParameters.__init__`, which pops `sub_port`/`sub_host` into `modelKwargs` (instruments.py:555-558), consumed by `ModelParameters` for its `SubClient` (instruments.py:413-424). `args.port + 1` matches the server's broadcast-port convention (server binds `port`, broadcasts on `port + 1`), so the GUI now follows `--port`.
- **Judgement on `type=int`:** it is required for the plan-mandated `args.port + 1` to be valid arithmetic — `args.port` would otherwise stay a `str` and `args.port + 1` would raise `TypeError`. It also makes the CLI match `Client(port: int)`'s signature (client/core.py:32). This is a necessary prerequisite for the task's specified change, not a scope-widening extra fix, so it does not violate plan rule 6 ("Do not widen scope"). Side effect: argparse now rejects a non-integer `--port`, which is strictly more correct.
- Caller context (server/core.py:483-487): `_newOrDeleteParameterDetection` runs after the call; the fix only changes how the broadcast payload is built, not the add/remove flow.
- Tests: `uv run pytest test/pytest/test_apps.py test/pytest/test_param_manager.py -q` → `31 passed in 12.42s`. The two launcher tests assert `sub_port=4568, sub_host="localhost"`; the new proxy test `test_add_parameter_without_initial_value_succeeds_and_broadcasts` covers the no-`initial_value`/`unit` path over the wire using `server_port + 1`.

Verdict is approve: no must-fix or should-fix findings.