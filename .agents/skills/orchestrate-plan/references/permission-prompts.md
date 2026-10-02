# Answering opencode permission prompts

Verified 2026-09-23 with opencode 1.18.30 and Orca 1.4.209 (setup test, `reviewer-qwen`).

## How a prompt shows up

Orca does **not** flag it: `worker-list` / `worker-show` report
`attention.requiresAction: false` and `nextAction: none` while the worker waits. The signs are:

- `orca orchestration worker-read --dispatch <id> --json` → `stage.activity` is `"waiting"`.
- `orca terminal read --terminal <handle> --json` → `result.terminal.tail` contains the lines

  ```
  △ Permission required
    # Shell command            (or the tool name, e.g. an edit)
  $ <the exact command>
   Allow once   Allow always   Reject
  ```

So on every wait timeout, read each active worker's terminal tail and search for
`Permission required`. The line after the `# ...` header is the request.

## Keystrokes

The prompt opens with **Allow once** selected. Right arrow moves the selection.

| Decision | Command |
|---|---|
| Allow once | `orca terminal send --terminal <handle> --text "" --enter --json` |
| Reject | `orca terminal send --terminal <handle> --text $'\e[C\e[C' --json`, then `orca terminal send --terminal <handle> --text "" --enter --json` |

**Never choose "Allow always".** It changes the session's rules for the rest of the task
and leaves no record.

## After a reject: the worker stops

Rejecting ends opencode's whole turn. The agent goes idle **without** sending
`worker_done`. Right after a reject, type a follow-up into its terminal:

```
orca terminal send --terminal <handle> --text "Orchestrator: your request to run '<command>' was rejected because <reason>. <What to do instead>. Then continue the task and send worker_done as instructed." --enter --wait-submit 10 --json
```

## What was checked and works without prompts

- Writing a file under `orchestration/` with the edit tool (reviewer): allowed.
- Writing a file outside `orchestration/` (reviewer): refused with no prompt, and the agent
  moved on.
- `git stash list` (denied pattern): refused with no prompt.
- `orca orchestration send ... worker_done` from the preamble: allowed, no prompt.

## Not tried

An opencode plugin that turns permission requests into Orca `ask` messages. The terminal
route above works, so it is not needed now.
