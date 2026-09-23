# Task specs and report format

Fill these in for every Dispatch. Orca adds its own worker preamble (IDs, how to `ask`,
how to send `worker_done`) above your spec; do not repeat it. Replace every `<...>`.
Specs must stand alone: a worker has not seen this conversation, the other workers, or
earlier tasks. The role's standing instructions live in its role file (`.agents/roles/`);
if `ROSTER.md` says the runner does not load it, paste it above the spec.

Orca's spec contract asks for Target, Change, Constraints, Ownership and Observable
acceptance. The templates below cover all five.

---

## Coder: implement

```
ROLE: coder for plan task <T>.

TARGET: repository at <worktree path>, branch <branch>. Plan file: <plan-file>.

READ FIRST, in this order: <plan-file> (whole file), then every file its session protocol
lists (<e.g. CONTEXT.md, docs/adr/*.md>). Follow that protocol and its "rules every task
follows" exactly, except where this spec overrides them.

THE TASK, copied from the plan:
<task text, verbatim, including its Acceptance and Tests lines>

CHANGE: implement exactly this task. Nothing from other tasks, no drive-by fixes.

CONSTRAINTS:
- Before editing any function or class, do the caller check the plan describes and
  report what you found in your worker_done summary.
- Use only terms from the glossary. If you need a word it lacks, use Orca `ask` and wait.
- If the plan does not answer a question, use Orca `ask` and wait. Do not guess.
- If you cannot finish without going outside the task, send an Orca escalation.

OWNERSHIP: you may edit files under src/ and test/, and <any other paths the task names>.
Do not edit <plan-file>, orchestration/, or any other plan or doc file unless the task
says so. You are the only agent editing files.

COMMIT: when the named tests and the full suite pass, make exactly ONE commit:
  git add <only the files you changed>      (never `git add -A` or `git add .`)
  git commit -m "<T>: <short summary of what this commit does>"
Never add anything under orchestration/. Never push, amend, rebase, reset, stash,
checkout or switch branches.

ACCEPTANCE: the task's named tests and the full suite pass (<test commands from the
plan>). In worker_done include: the commit hash, the test summary lines, the caller
check results, and anything you were unsure about.
```

## Coder: fix round

```
ROLE: coder for plan task <T>, fix round <k> of at most 5.

You implemented this task earlier in this session. The reviewers found the problems
below. The orchestrator has already filtered them: fix every item. If you believe an
item is wrong, do not skip it silently: use Orca `ask` and explain why.

FIX LIST (also in <D>/round-<k-1>/fix-list.md):
<numbered items: what, where (file:line), why, which reviewers raised it>

<If tests were red: FAILING TEST OUTPUT: <output>>

Same constraints, ownership and commit rules as before. Make exactly ONE commit:
  git commit -m "<T>: fix from review round <k>: <short summary>"

ACCEPTANCE: every item addressed, named tests and full suite pass. In worker_done list
each item number with what you did, plus the commit hash and test summary lines.
```

## Reviewer: first review

```
ROLE: <agent-id> (<role>) for plan task <T>. You are one of six reviewers. You only read.

TARGET: the commits `git log <BASE>..<HEAD>` on branch <branch> in <worktree path>.
Look at them with `git show` and `git diff <BASE>..<HEAD>`. Read surrounding code as needed.

READ FIRST: <plan-file> (whole file) and every file its session protocol lists
(<e.g. CONTEXT.md, docs/adr/*.md>). The task, copied from the plan:
<task text, verbatim>

YOUR FOCUS: as your role file says (.agents/roles/<role>.md). Stay in that lane.

OWNERSHIP: you may create exactly one file: <report path>. Do not edit any other file.
Do not run git commands that change anything. You may run the test suite.

OUTPUT: write the report in the format below to <report path>. In worker_done give the
verdict and the count of findings per severity, and pass --report-path <report path>.
```

## Reviewer: re-review

```
ROLE: same as before, plan task <T>, re-review after fix round <k>.

The coder made a fix commit: <hash>. See it with `git show <hash>`.
Your previous report: <previous report path>. The fix list the coder worked from:
<D>/round-<k-1>/fix-list.md (some of your findings may have been dropped on purpose;
the reasons are in <D>/decisions.md).

Do three things:
1. For each of your previous findings: fixed / not fixed / dropped by orchestrator.
2. Did the fix commit break or weaken anything in your focus area?
3. New findings in your focus area caused by the fix commit.

OWNERSHIP and OUTPUT: same as before, but write to <new report path>.
```

---

## Report format (all reviewers)

```markdown
# <T> — <agent-id> — round <n>

Verdict: approve | changes-needed

## Findings

### F1 — must-fix | should-fix | nit
- Where: path/to/file.py:123
- What: one sentence.
- Why: one or two sentences; quote the plan line if it is a plan rule.
- Suggested fix: one or two sentences.

### F2 — ...

## Previous findings (re-review only)
- F1: fixed | not fixed (why) | dropped by orchestrator

## Notes
Anything else, e.g. tests run and their summary line.
```

Severity meaning:
- **must-fix**: wrong behaviour, a broken rule from the plan, a missing named test, a test
  that cannot fail.
- **should-fix**: real weakness that is cheap to fix now (missing edge-case test, unclear
  error message, duplicated logic).
- **nit**: preference only. The orchestrator will not send these to the coder.

Verdict is `approve` only when there are no must-fix or should-fix findings.
