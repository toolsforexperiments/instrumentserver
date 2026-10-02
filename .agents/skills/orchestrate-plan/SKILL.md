---
name: orchestrate-plan
description: >-
  Run a checkbox plan (e.g. PLAN_parameter_manager_redesign.md) task by task as an Orca
  orchestrator: one coder agent writes and commits each task, six reviewer agents
  (general, tests, plan checker, each on two models) review every commit in parallel, and
  the orchestrator merges their findings into fix rounds until the task is clean. Stops to
  ask the user when the plan does not answer something. Use when the user says
  "/orchestrate-plan", "orchestrate the plan", or "run the plan with agents".
---

# Orchestrate a plan

You are the **orchestrator**. You do not write code. You hand plan tasks to worker
agents (listed in `.agents/roles/ROSTER.md`) through Orca, check their work, merge reviews, commit the paper trail, and ask the
user when the plan runs out of answers.

This skill uses only the `orca` CLI, `git` and the shell, so any agent can follow it.

## Arguments

```
/orchestrate-plan <plan-file> [--only <task>] [--from <task>]
```

- `<plan-file>`: the plan, e.g. `PLAN_parameter_manager_redesign.md`.
- `--only 0.1`: run exactly that task, then stop. Use this for pilots.
- `--from 1.2`: start at that task instead of the first open one.
- With no flags: start at the first task not marked `[x]` and run until the end of that
  task's phase.

## Before you start: load Orca's orchestration guide

Run `orca skills get orchestration` and read it. It is the version-matched rulebook for
every `orca orchestration` command below; where it and this file disagree on command
syntax, the guide wins. Resolve the Orca executable the way that guide says (normally
`orca`) and use the same one for the whole run.

## Roles

Roles and the agents that fill them are listed in **`.agents/roles/ROSTER.md`**. Read it at
startup. It gives, per agent id: its role file, the runner (e.g. opencode), its model, its
launch command, and whether the runner loads the role file itself.

The current roster has eight agents: one `coder`, one `historian` (writes the task's history
section at the end, Step 7), and six **reviewers**, three roles each on two models:

- `reviewer-*`: general code review
- `test-reviewer-*`: do the tests prove the task, and what is untested
- `plan-checker-*`: does the commit match the plan, glossary, decisions, ADRs and scope

The role files in `.agents/roles/` hold each role's standing instructions. Your task specs
(`references/task-specs.md`) only add the specific job. If the roster says a runner does
**not** load the role file, paste the role file's full text at the top of every spec you
send that agent.

Reviewers write only their own report file. Only the coder edits code.

## Fixed rules

1. **One plan task per job.** Finish a task completely before starting the next.
2. **Everything happens in the current worktree**, on its current branch. One agent edits at
   a time: the coder. Reviewers only read.
3. **Commits.** The coder commits code and tests: one commit for the first implementation,
   one per fix round, each message starting with the task number (`0.1: ...`). You commit
   only the history file (`HISTORY_<plan name>.md`, see Step 7) and the plan's checkboxes.
   `orchestration/` is git-ignored working space: never commit it. Nobody pushes, amends,
   squashes, rebases, resets, stashes, switches branches or deletes branches. Ever.
4. **Fresh sessions per task.** Within a task, reuse the same coder and the same six reviewer
   sessions across fix rounds. At task end, release all seven.
5. **Fix-round limit: 5.** If findings are still open after the fifth fix commit, stop and
   ask the user.
6. **You never edit source or test files yourself.** Every code change goes through the coder.
7. Follow the plan's own session protocol and rules (caller checks, glossary, test
   commands, scope rules). Pass them to workers; do not restate them from memory.

## Preflight (once per run)

1. `orca status --json`: the runtime must be `ready`. If not, `orca open --json` and retry.
2. `git status --porcelain`: the working tree must be clean. If anything is modified or
   untracked, **stop and ask the user** to commit or clean it; do not commit their work.
   The plan file itself must be tracked, since you will commit checkbox changes to it.
3. `git branch --show-current`: note the branch. Every commit in this run must land on it.
4. Read the whole plan, then every file its session protocol says to read (for the
   parameter-manager plan: `CONTEXT.md` and `docs/adr/*`). Find the tasks to run.
5. `orca orchestration run-create --objective "<plan-file>: tasks <first>..<last>" --json`.
   Keep the Run id.
6. Create `orchestration/` if missing. Append a run header to `orchestration/RUNS.md` (local only, not committed):
   date, plan, tasks, branch, starting commit (`git rev-parse HEAD`).

## The loop for one task

Use `T` for the task number (e.g. `0.1`) and `D=orchestration/T` for its folder.

### Step 1: start

- Change the task's checkbox in the plan to `[~]`.
- Create `D/decisions.md` with a header naming the task.
- Record the base commit: `BASE=$(git rev-parse HEAD)`.

### Step 2: coder, first implementation

1. Write the coder's spec from `references/task-specs.md` ("Coder: implement"). Copy
   the task text from the plan word for word. Do not paraphrase it.
2. Create the Task: `orca orchestration task-create --spec "<spec>" --task-title "T coder" --json`.
3. Launch the coder (see "Launching a worker" below).
4. Wait (see "Waiting").
5. When its `worker_done` arrives:
   - `outcome failed` → read its summary and treat it as an escalation (see "Stopping").
   - `outcome succeeded` → check: `git log --oneline $BASE..HEAD` shows exactly one new
     commit starting with `T:`; `git status --porcelain` shows nothing outside
     `orchestration/`; the branch did not change; the commit touches no file under
     `orchestration/`. Anything else is a problem to log and fix with the coder or ask about.
   - Keep the coder's terminal for reuse: `orca orchestration worker-retain --dispatch <id> --json`.
6. Run the task's named tests **and** the full suite yourself, using the plan's commands.
   Paste the summary lines into `D/decisions.md`. If anything is red, skip the reviewers:
   send the failure output to the coder as a fix round (Step 5). It counts toward the limit.

### Step 3: six reviewers

1. Create the round folder yourself (`mkdir -p D/round-0`) so reviewers do not need to.
   For each of the six reviewer ids, write its spec from `references/task-specs.md`
   ("Reviewer: first review"). The review target is the commit range `$BASE..HEAD`.
   Its report path is `D/round-0/<agent-id>.md`.
2. Create six Tasks and launch all six workers before waiting for any of them.
3. Wait until all six have sent `worker_done`. Retain each one (`worker-retain`).
4. Check that every report file exists and follows the report format. A missing or
   malformed report: give that reviewer a follow-up Dispatch in its same terminal asking
   it to write or fix the report. If its process has exited, follow the guide's recovery
   reference. Do not merge without all six.

### Step 4: merge and decide

Read all six reports and write `D/round-<n>/fix-list.md` (`n` = the round the reports
came from, `0` for the first review). Rules:

- **Both models of one role raised it** → keep it.
- **Only one model raised it** → read the code yourself. Keep it only if you can confirm it.
- **Nit** (style, wording, naming preference that no plan rule requires) → do not send
  it. Log it in `decisions.md` as "not sent: nit".
- **Out of scope** (the plan's scope rule forbids it, e.g. a pre-existing defect not in the
  task) → do not send. Log it; if the plan says where such things go (the
  parameter-manager plan: `TEST_AUDIT.md`), have the coder add a note there in the next fix round.
- **It would change a recorded decision, a glossary term or an ADR** → do not send.
  **Stop and ask the user.**
- **Reviewers contradict each other** → you decide, and log why. If you cannot decide from the
  plan, ask the user.
- **Merge duplicates** into one item, listing which reviewers raised it.

Write one line per decision in `decisions.md`: finding, source reviewers, kept or dropped,
and why.

If the fix list is empty and every reviewer's verdict is `approve` (or its remaining
findings were all dropped with a logged reason) → go to Step 6.

### Step 5: fix round

1. If this would be fix round 6 → **stop and ask the user**, with the open findings.
2. Dispatch the fix list to the **same coder terminal**:
   `task-create` with the "Coder: fix round" spec, then
   `orca orchestration worker-start --task <id> --terminal <coder handle> --worktree current --json`.
3. Wait for `worker_done`. Check as in Step 2.5: exactly one new commit, prefix `T:`,
   nothing uncommitted outside `orchestration/`, no `orchestration/` files in the commit.
   Retain the coder again.
4. Rerun the tests yourself (as in Step 2.6). Red → next fix round with the failure output.
5. Dispatch a re-review to **all six reviewers, in their same terminals**, using the
   "Reviewer: re-review" spec. The target is the new fix commit, and each reviewer gets its
   previous report path. Report path: `D/round-<k>/<agent-id>.md` for fix round `k`.
6. Wait for all six, retain them, go back to Step 4.

### Step 6: close the task's workers

1. Release all seven workers: `orca orchestration worker-release --dispatch <id> --json`
   for each final Dispatch. Because you created their terminals yourself, Orca answers
   `reason: external_terminal` and leaves the process running. After an accepted release,
   close each one: `orca terminal close --terminal <handle> --json`. Then confirm
   `orca orchestration worker-list --run <run_id> --terminal-state reclaimable --json`
   shows none of this task's workers.
2. Add a one-line summary to `decisions.md`: commits (`git log --oneline $BASE..HEAD`),
   fix rounds used, test summary line.

### Step 7: history

The history file is named after the plan: `PLAN_<name>.md` → `HISTORY_<name>.md`, in the
same folder. Create it with a one-line title (`# History: <plan title>`) if it does not exist.

1. Launch the `historian` (see `ROSTER.md`; it is a fresh session every task) with the
   "Historian: write section" spec from `references/task-specs.md`.
2. Wait for its `worker_done`. Check: `git status --porcelain` shows only the history file
   changed (plus the ignored `orchestration/`); the new section is at the end; no earlier
   section changed (`git diff` of the history file only adds lines). Otherwise send it back
   with what to fix, in the same session.
3. Release it and close its terminal, as in Step 6.
4. Change the task's checkbox to `[x]`.
5. Commit: `git add <history file> <plan-file> && git commit -m "T: history"`.
   Only those two paths. Never `git add -A`.
6. Next task. If `--only` was given, or the next task is in a new phase, stop and report.

## Launching a worker

Launch every worker in a terminal you create, using the roster's launch command for that
agent id. Orca then takes over supervision:

```
orca terminal create --worktree active --title "T <agent-id>" --command "<launch command from ROSTER.md>" --json
orca terminal wait --terminal <handle> --for tui-idle --timeout-ms 60000 --json
orca orchestration worker-start --task <task_id> --terminal <handle> --worktree current --json
```

(Orca's own `worker-start --agent <runner>` cannot choose an opencode agent or model, which
is why the terminal comes first.) `worker-start` injects Orca's worker preamble (Task id,
Dispatch id, how to `ask`, how to send `worker_done`) plus your spec into that session.

- If `worker-start` exits non-zero, do **not** relaunch. Read `failedStage` and
  `residualResources` in the receipt and follow
  `orca skills get orchestration --reference references/recovery-and-cleanup.md`.
- Keep a table in memory and in `decisions.md`: agent id → terminal handle → current
  Dispatch id. Reuse always goes by handle; lifecycle always goes by Dispatch id.

## Waiting

Never sit in a long `check --wait`: permission prompts do not arrive as messages, so
workers would stay stuck until the wait ends. Use the watcher instead. It returns within
about 3 seconds of anything that needs you:

```
.agents/skills/orchestrate-plan/scripts/wait-event.sh 600 <handle of every active worker>...
```

It prints one line:

- `message <n>` → run `orca orchestration check --json` and process the delivery:
  - `question` → answer from the plan if it clearly answers it (`orchestration reply --id
    <msg> --body ...`) and log it. Otherwise **stop and ask the user**, then reply with
    their answer.
  - `escalation` → see "Stopping".
  - `worker_done` → validate it belongs to the Dispatch you expect, then retain or release.
  - Then ack: `orca orchestration check --ack <delivery_id> --json`.
- `permission <handle>` → handle the prompt on that worker (below), then run the watcher again.
- `timeout` → 10 minutes with nothing. Normal for long tasks; run it again. After three
  timeouts in a row, follow the guide's rule: enumerate with `worker-list` and inspect.
  Never stop, abandon or relaunch a worker without proof its process exited.

Pass only the handles of workers currently working (not retained idle ones), so the
watcher stays fast.

## Permission prompts

Every agent has three permission levels, listed in `ROSTER.md` and enforced by its runner
(for opencode, in `opencode.json`):

- **Always allowed**: reading, searching, read-only git, the test command, Orca's worker
  commands; for the coder also editing and `git add`/`git commit`; for reviewers, writing
  under `orchestration/`.
- **Always denied**: `git push`, `rebase`, `reset`, `commit --amend`, `stash`, `checkout`,
  `switch`, `branch -d/-D`, `clean`, `git add -A/./--all`; for reviewers also editing outside
  `orchestration/` and any `git add`/`commit`. You cannot allow these, and must not try.
- **Everything else asks.** That question lands on you.

When a worker is waiting on a permission prompt:

1. Read the exact command or path it wants.
2. Decide: is it needed for this task, limited to this worktree, and easy to undo? Examples
   that are usually fine: running a single test file with extra flags, `git rm` of a file
   the task says to remove. Examples to reject: installing or upgrading packages,
   touching files outside the repo, network access, deleting files the task does not name.
3. If you cannot tell → **stop and ask the user**.
4. Answer the prompt in the worker's terminal with the keystrokes in
   `references/permission-prompts.md`. Never pick "Allow always". **A reject ends the
   worker's turn**: immediately type a follow-up telling it what was rejected, why, and
   to continue.
5. Log it in `decisions.md`: worker, request, allowed or rejected, why.

## Stopping and asking the user

Stop the loop (leave workers paused, not released) and ask the user **in your own
terminal** when:

1. The plan, glossary or ADRs do not answer a question a worker or you have. That includes a
   worker needing a word the glossary lacks.
2. A finding would change a recorded decision, glossary term or ADR.
3. Findings are still open after 5 fix rounds.
4. Tests stay red and the coder says fixing them needs work outside the task.
5. A worker escalates something you cannot resolve from the plan.
6. A permission request you cannot judge.
7. A phase is finished (always stop at the end of a phase).
8. Something breaks the fixed rules: an unexpected commit count, a branch change, a push attempt,
   uncommitted changes outside `orchestration/` after a coder commit.

Orca marks your terminal as waiting and notifies the user; you do not need another
notification channel. Ask one question at a time, in plain words, with your
recommendation. Include: task, which worker, what it wants, what the plan says,
your recommendation. Log the question and the user's answer in `decisions.md`.

## Final report

When the run stops (done, `--only`, phase end, or a question), write to your terminal and
to `orchestration/RUNS.md` (local only, not committed):

- Per task: outcome (`done` / `stopped: <reason>`), commits (`git log --oneline`), fix rounds
  used, final test summary line.
- Open questions for the user, if any.
- Workers still alive and why (should be none unless stopped mid-task).

## Files you produce

```
HISTORY_<plan name>.md             # committed: one historian section per task
orchestration/                     # git-ignored working space, kept on disk
  RUNS.md                          # one header + final report per run
  0.1/
    decisions.md                   # every decision, question, permission, test result
    round-0/<agent-id>.md          # six first reviews
    round-0/fix-list.md            # what went to the coder
    round-1/<agent-id>.md          # six re-reviews of fix commit 1
    round-1/fix-list.md
    ...
```
