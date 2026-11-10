#!/usr/bin/env bash
# Morning routine: wipe saved jobs, then run a fresh scrape. Use ./run.sh alone to keep saved jobs.
set -euo pipefail
cd "$(dirname "$0")"

source scripts/server.sh
RUNNING=$(running_url)
if [ -n "$RUNNING" ]; then
  echo "The dashboard is already running at $RUNNING — stop it (Ctrl+C) first." >&2
  exit 1
fi

# Build before wiping so a failed build never leaves an empty database and no dashboard.
scripts/build-dashboard.sh
./clear.sh
exec ./run.sh
