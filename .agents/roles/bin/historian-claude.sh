#!/usr/bin/env bash
# Launch the historian role as a Claude Code session with only the tools it needs:
# read anything, read-only git, Orca worker commands, and edits to HISTORY_*.md only.
# Run from the repository root. Extra arguments are passed to claude.
set -eu
root="$(git rev-parse --show-toplevel)"
cd "$root"
export PYTHONDONTWRITEBYTECODE=1
exec claude \
  --model "${HISTORIAN_MODEL:-opus}" \
  --append-system-prompt-file .agents/roles/historian.md \
  --permission-mode default \
  --allowedTools \
    "Read" "Grep" "Glob" \
    "Edit(/HISTORY_*.md)" "Write(/HISTORY_*.md)" \
    "Bash(git log:*)" "Bash(git show:*)" "Bash(git diff:*)" "Bash(git status:*)" \
    "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)" \
    "Bash(orca orchestration send:*)" "Bash(orca orchestration check:*)" \
    "Bash(orca orchestration ask:*)" \
  --disallowedTools \
    "Bash(git commit:*)" "Bash(git add:*)" "Bash(git push:*)" "Bash(git reset:*)" \
    "Bash(git checkout:*)" "Bash(git stash:*)" "Bash(rm:*)" \
  "$@"
