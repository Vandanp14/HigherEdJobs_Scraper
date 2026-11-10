#!/usr/bin/env bash
# Wipe saved HigherEdJobs and AIR jobs, their statuses, notes, and run history. Company boards jobs,
# their statuses and notes, and the company list are kept, as is the HigherEdJobs browser session.
set -euo pipefail
cd "$(dirname "$0")"

source scripts/server.sh
RUNNING=$(running_url)
if [ -n "$RUNNING" ]; then
  echo "The dashboard is running at $RUNNING — stop it (Ctrl+C) before clearing." >&2
  exit 1
fi

echo "$(date +%H:%M:%S) [clear] Wiping saved HigherEdJobs and AIR jobs (Company boards jobs and browser session are kept)..."
.venv/bin/python scripts/manage-data.py clear-jobs
