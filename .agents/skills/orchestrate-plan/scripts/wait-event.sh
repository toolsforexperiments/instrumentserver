#!/usr/bin/env bash
# Block until something needs the orchestrator, then print ONE line and exit:
#   message <count>        an Orca message is waiting (run `orca orchestration check`)
#   permission <handle>    that worker's screen shows an opencode permission prompt
#   timeout                nothing happened within <timeout-seconds>
# Usage: wait-event.sh <timeout-seconds> <worker-terminal-handle>...
# Polls every 3 seconds. Read-only: it never answers prompts or acks messages.
set -u
ORCA="${ORCA_CLI_COMMAND:-orca}"
timeout="${1:?timeout seconds}"; shift
end=$(( $(date +%s) + timeout ))
while :; do
  count=$($ORCA orchestration check --peek --json 2>/dev/null |
    python3 -c 'import sys,json
try: print(json.load(sys.stdin)["result"]["count"])
except Exception: print(0)')
  if [ "${count:-0}" != "0" ]; then echo "message $count"; exit 0; fi
  for h in "$@"; do
    if $ORCA terminal read --terminal "$h" --json 2>/dev/null |
       python3 -c 'import sys,json
try: tail=json.load(sys.stdin)["result"]["terminal"]["tail"]
except Exception: sys.exit(1)
sys.exit(0 if any("Permission required" in l for l in tail) else 1)'; then
      echo "permission $h"; exit 0
    fi
  done
  [ "$(date +%s)" -ge "$end" ] && { echo timeout; exit 0; }
  sleep 3
done
