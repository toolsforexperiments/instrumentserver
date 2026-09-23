# Roster

Which agents fill which roles, and how to launch each one. The orchestrator
(`.agents/skills/orchestrate-plan`) reads this file. To change who does a job, edit only this
table (and, for opencode, the matching entry in `opencode.json`).

The role files (`coder.md`, `reviewer.md`, `test-reviewer.md`, `plan-checker.md`) are plain
instructions and work with any coding agent.

| Id | Role file | Runner | Model | Launch command | Role file loaded by runner? |
|---|---|---|---|---|---|
| `coder` | `coder.md` | opencode | lumen/glm-5.3-flash | `opencode --agent coder` | yes |
| `reviewer-deepseek` | `reviewer.md` | opencode | lumen/deepseek-v4-flash | `opencode --agent reviewer-deepseek` | yes |
| `reviewer-qwen` | `reviewer.md` | opencode | lumen/qwen3-coder-next | `opencode --agent reviewer-qwen` | yes |
| `test-reviewer-deepseek` | `test-reviewer.md` | opencode | lumen/deepseek-v4-flash | `opencode --agent test-reviewer-deepseek` | yes |
| `test-reviewer-qwen` | `test-reviewer.md` | opencode | lumen/qwen3-coder-next | `opencode --agent test-reviewer-qwen` | yes |
| `plan-checker-deepseek` | `plan-checker.md` | opencode | lumen/deepseek-v4-flash | `opencode --agent plan-checker-deepseek` | yes |
| `plan-checker-qwen` | `plan-checker.md` | opencode | lumen/qwen3-coder-next | `opencode --agent plan-checker-qwen` | yes |

**Last column.** "yes" means the runner loads the role file itself as standing
instructions. "no" means the orchestrator must paste the role file's full text at the top of
every task spec it sends that agent.

## Permissions every runner must enforce

Whatever runner fills a role, set up its permission system to match these three levels. For
opencode they live in `opencode.json`.

**Always allowed (all roles):** reading and searching files; `git status`, `diff`, `log`,
`show`, `blame`, `rev-parse`; `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`;
`uv run pytest ...`; the `orca orchestration` worker commands (`check`, `send`, `ask`) that
Orca's preamble tells workers to run.

**Coder also:** editing files; `git add <paths>`; `git commit -m ...`.

**Reviewers also:** creating or editing files under `orchestration/` (including `mkdir -p` there), and nothing else.

**Always denied (all roles):** `git push`, `rebase`, `reset`, `commit --amend`, `stash`,
`checkout`, `switch`, `branch -d/-D`, `clean`; `git add -A`, `git add .`, `git add --all`.
**Reviewers also:** editing anything outside `orchestration/`, `git add`, `git commit`.

**Everything else: ask.** The question goes to whoever watches the agent: the
orchestrator, which decides per `SKILL.md` "Permission prompts".

## Switching a role to another runner (example)

To make the coder a Claude Code session instead of opencode, change its row to runner
`claude`, launch command `claude --model <id> --append-system-prompt "$(cat .agents/roles/coder.md)"`,
and give that session the permission levels above (e.g. in `.claude/settings.json`). The
orchestrator needs no other change.
