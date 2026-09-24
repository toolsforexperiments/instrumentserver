# 0.4 Pre-existing fixes (D24, first two) — decisions log

Run: run_e6f4c00ea2df. Branch: marcosfrenkel/new-param-manager. Base commit: 88eeda0978cae2f3aa5ec76bac7c50444fb6bd85.

## Workers

| agent id | terminal handle | current dispatch id |
|---|---|---|
| plan-checker-qwen | term_7da87644-1284-4941-a634-0c49ef2fed22 | ctx_32138e7e96b9 (task_dc2d726e35aa, round 0) |
| plan-checker-deepseek | term_d339209a-287a-406c-b55d-dec40d32885d | ctx_0f25b3317a4d (task_27e70ad56463, round 0) |
| test-reviewer-qwen | term_68349c14-9cec-4e9a-b7d6-5bf81057dccb | ctx_9dc81465d35c (task_a2cc5b175f7f, round 0) |
| test-reviewer-deepseek | term_ecefb21d-50b0-4e4c-b311-700961f290c6 | ctx_5ddc99b46da4 (task_5d5d55a85fe4, round 0) |
| reviewer-qwen | term_e2ed50a3-68d0-4322-8c96-acf88fd9c980 | ctx_3251bebf2f6c (task_1221a2fc837e, round 0) |
| reviewer-deepseek | term_83491358-911e-447e-8029-7a6aabc0d3d5 | ctx_edd8b4b63a12 (task_74070a014957, round 0) |
| coder | term_153dd2fe-6067-44c9-9e20-ea12cc6d8e43 | ctx_1d64da13fd1e (task_72a86c9e1394, first implementation) |

## Log

- Checkbox 0.4 set to [~]. Base 88eeda0.
- Coder dispatched for first implementation (task_72a86c9e1394 / ctx_1d64da13fd1e).
- Permission: coder asked python/uv import qcodes location + ls of venv dirs (read-only). Allowed once.
- Coder worker_done (succeeded). Commit 56ece34 "0.4: fix latent KeyError in parameter-creation broadcast and pass broadcast port to the parameter manager GUI launcher"; files: src/instrumentserver/apps.py, src/instrumentserver/server/core.py, test/pytest/test_apps.py, test/pytest/test_param_manager.py. Checks: 1 commit, prefix ok, branch unchanged, no orchestration/ files, nothing dirty outside orchestration/ and the plan. Coder retained.
- Coder judgment call: added `type=int` to the launcher's `--port` argparse argument so `args.port + 1` (the plan's prescribed expression) works; before, the port reached Client as a string. Orchestrator view: required by the task text; reviewers will judge.
- Orchestrator tests: `uv run pytest -q test/pytest/test_apps.py test/pytest/test_param_manager.py` -> 31 passed in 12.28s; `uv run pytest -q` -> 174 passed, 4 warnings in 68.94s.
- Six reviewers dispatched for round 0 (target 88eeda0..56ece34).
- test-reviewer-qwen worker_done (succeeded, approve, 2 nits). Retained.
- plan-checker-qwen worker_done (succeeded, approve, 0 findings; type=int judged in scope). Retained.
- reviewer-qwen worker_done (succeeded, approve, 1 nit: duplicated capture helper). Retained.
- plan-checker-deepseek and test-reviewer-deepseek stalled on provider 'Upstream error'; reviewer-deepseek degenerated into garbled output. No reports. All three nudged in their terminals to resume and report.
- Correction: the first nudge never reached the three terminals (orchestrator shell bug: empty handle). Re-sent successfully ~10 min later.
- Permission: plan-checker-deepseek asked access to a garbled '/Users:/Users/...' path outside the repo. REJECTED; told it to use the relative report path.
- Permission: plan-checker-deepseek asked rm of its own report file orchestration/0.4/round-0/plan-checker-deepseek.md to rewrite it. Allowed once (its own file, under orchestration/).
- Round 0 deepseek reviewers after the nudge: reviewer-deepseek wrote a complete report (approve, 1 nit) but hit a provider error before worker_done; test-reviewer-deepseek's report has approve + 1 nit but a garbled Notes tail; plan-checker-deepseek wrote only a skeleton (approve, no findings). All three nudged again with specific instructions.
- plan-checker-deepseek worker_done after nudges (succeeded, approve, 0 findings). Retained.
- test-reviewer-deepseek worker_done after nudges (succeeded, approve, 1 nit). Retained.
- reviewer-deepseek worker_done after nudges (succeeded, approve, 1 nit). Retained. All six round-0 reports present.

## Round 0 merge (six reports, all `approve`; 0 must-fix / 0 should-fix)

- reviewer-qwen F1 + test-reviewer-qwen F1 + reviewer-deepseek note: `capture_broadcasts`/`wait_for_broadcasts` copied verbatim from test_broadcaster.py into test_param_manager.py. Nit by all who raised it; not a plan rule. Not sent: nit. Worth consolidating into conftest.py when a third copy appears (tasks 1.3 / 2.5).
- test-reviewer-qwen F2 + test-reviewer-deepseek F1: launcher tests only exercise the `--port 4567` path, not the default-port path. Not sent: nit; the plan asks only to extend the two existing tests, which was done.
- reviewer-deepseek F1 (nit): `type=int` on `--port` is a judgment call beyond D24's literal text; every reviewer (both plan-checkers explicitly) judges it in scope as a prerequisite for `args.port + 1`. Not sent; accepted.
- Fix list: EMPTY. Task goes to finish.

## Finish
- All seven workers released (Orca: state retained, processAction none) and their terminals closed. `worker-list --terminal-state reclaimable` for run_e6f4c00ea2df: 0 rows.
- Checkbox 0.4 set to [x].

**Summary.** Outcome: done. Commits: `56ece34 0.4: fix latent KeyError in parameter-creation broadcast and pass broadcast port to the parameter manager GUI launcher`. Fix rounds used: 0. Tests (orchestrator): `uv run pytest -q test/pytest/test_apps.py test/pytest/test_param_manager.py` -> 31 passed in 12.28s; `uv run pytest -q` -> 174 passed, 4 warnings in 68.94s.
