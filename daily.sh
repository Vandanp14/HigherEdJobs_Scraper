#!/usr/bin/env bash
# Morning routine: wipe saved jobs, then run a fresh scrape. Use ./run.sh alone to keep saved jobs.
set -euo pipefail
cd "$(dirname "$0")"

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 8000 in use — stop the other server first." >&2
  exit 1
fi

# Build before wiping so a failed build never leaves an empty database and no dashboard.
scripts/build-dashboard.sh
./clear.sh
exec ./run.sh
