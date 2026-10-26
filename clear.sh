#!/usr/bin/env bash
# Wipe all saved jobs, statuses, notes, and run history. The HigherEdJobs browser session is kept.
set -euo pipefail
cd "$(dirname "$0")"

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "The dashboard server is running on port 8000 — stop it (Ctrl+C) before clearing." >&2
  exit 1
fi

echo "$(date +%H:%M:%S) [clear] Wiping saved jobs (browser session is kept)..."
.venv/bin/python scripts/manage-data.py clear-jobs
