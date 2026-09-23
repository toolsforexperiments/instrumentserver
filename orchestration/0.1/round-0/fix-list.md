# 0.1 — round 0 — fix list

Empty. All six reviewers returned `approve`. No must-fix findings. The single should-fix
(test-reviewer-qwen F1) was raised by one model only and was not confirmed by the
orchestrator: `test_submodule_does_not_load_parameter_file` already asserts
`isinstance(params.q01, ParameterGroup)` (test/pytest/test_param_manager.py:257).
Remaining findings are nits and were not sent. See decisions.md.
