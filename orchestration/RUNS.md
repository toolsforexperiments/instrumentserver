# Orchestration runs

## Run 2026-09-23 — run_caa796369a9e

- Plan: PLAN_parameter_manager_redesign.md
- Tasks: 0.1 (--only 0.1, pilot)
- Branch: marcosfrenkel/new-param-manager
- Starting commit: 447c7f71542e443410684849084ae230cbc8ecfc

### Report

| Task | Outcome | Commits | Fix rounds | Final tests |
|---|---|---|---|---|
| 0.1 | done | `46e34cd 0.1: split ParameterGroup out of ParameterManager` | 0 | named file 12 passed; full suite 161 passed, 4 warnings |

- Six reviewers, all `approve`. One should-fix (test-reviewer-qwen) dropped as factually wrong; five nits not sent. Details: `orchestration/0.1/decisions.md`.
- Open questions for the user: none.
- Workers still alive: none. Stopped because `--only 0.1` was given.
- Permission prompts handled: 5 allowed (all read-only), 1 rejected (reviewer-deepseek tried `git worktree add /tmp/...`).
- Process notes for the next run: (1) reviewer-deepseek's turn ended once without sending worker_done and needed a terminal nudge; (2) three reviewers running `uv run pytest` at the same time collided on fixed ports 5555/5599 and each saw one spurious failure. Consider telling reviewers to run only the task's named test file, or stagger full-suite runs. (3) opencode's bash allowlist misses read-only commands chained with `&&` or prefixed with `cd ... &&`, which caused most prompts.

## Run 2026-09-23 — run_da269441b6ac

- Plan: PLAN_parameter_manager_redesign.md
- Tasks: 0.0, 0.2, 0.3, 0.4, 0.5 (rest of Phase 0; 0.1 already done)
- Branch: marcosfrenkel/new-param-manager
- Starting commit: dcac611241cfbf698885d126a67e8fe11332ffc0
