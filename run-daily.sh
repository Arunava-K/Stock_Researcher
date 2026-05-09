#!/usr/bin/env bash
# Daily Stock Research routine — wrapper for cron / systemd.
#
# What it does:
#   1. cd to the project directory (where this script lives)
#   2. Optionally pulls the latest code from GitHub
#   3. Invokes Claude Code in non-interactive mode with routine_prompt.md
#   4. Logs the full run to logs/<utc-timestamp>.log
#
# Usage (cron, 08:30 IST = 03:00 UTC weekdays):
#   0 3 * * 1-5 /home/arunava/Stock_Researcher/run-daily.sh
#
# Prerequisites on the homeserver:
#   - Python 3.10+ available as `python` (or edit run.py / requirements)
#   - `claude` CLI installed and authenticated (run `claude` interactively once
#     to confirm auth works; the Notion MCP connector should be enabled in your
#     Claude.ai account so `claude --print` inherits access)
#   - Git installed (for the optional auto-pull)

set -e

cd "$(dirname "$(readlink -f "$0")")"

# Optional: pull latest code. Comment out if you prefer to control deploys manually.
git pull --quiet || echo "[warn] git pull failed; continuing with current checkout"

mkdir -p logs
LOG="logs/$(date -u +%Y-%m-%dT%H%M%SZ).log"

{
    echo "=== Stock Research routine: started $(date -Iseconds) ==="
    echo "Working dir: $PWD"
    echo "Routine prompt: $(wc -l < routine_prompt.md) lines"
    echo

    # Hand the skill body to Claude Code.
    #
    # The skill at .claude/skills/stock-brief.md is the canonical workflow,
    # invokable interactively as `/stock-brief` from inside the repo. Cron uses
    # the same content via stdin.
    #
    # NOTE on the CLI flag: `--print` reads stdin and prints the final response
    # non-interactively. Verify on your homeserver with:
    #     claude --print < .claude/skills/stock-brief.md
    # If your `claude` build uses a different flag, adjust here.
    claude --print < .claude/skills/stock-brief.md

    echo
    echo "=== Stock Research routine: finished $(date -Iseconds) ==="
} > "$LOG" 2>&1

# Print a tail to stdout so cron's mail / journalctl shows the summary.
echo "Log: $LOG"
tail -25 "$LOG"
