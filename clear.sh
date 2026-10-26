#!/usr/bin/env bash
# Wipe all saved jobs, statuses, notes, and run history. The HigherEdJobs browser session is kept.
set -euo pipefail
cd "$(dirname "$0")"

source scripts/server.sh
RUNNING=$(running_url)
if [ -n "$RUNNING" ]; then
  echo "The dashboard is running at $RUNNING — stop it (Ctrl+C) before clearing." >&2
  exit 1
fi

echo "$(date +%H:%M:%S) [clear] Wiping saved jobs (browser session is kept)..."
.venv/bin/python scripts/manage-data.py clear-jobs
