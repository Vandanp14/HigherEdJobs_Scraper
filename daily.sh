#!/usr/bin/env bash
# Daily run: wipe saved jobs, serve the dashboard, and fetch fresh HigherEdJobs and AIR listings.
set -euo pipefail
cd "$(dirname "$0")"

URL="http://127.0.0.1:8000"
say() { echo "$(date +%H:%M:%S) [daily] $*"; }

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 8000 in use — stop the other server first." >&2
  exit 1
fi

# Build before wiping so a failed build never leaves an empty database and no dashboard.
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  say "Building dashboard (frontend changed)..."
  (cd frontend && npm run build >/dev/null)
fi

say "Wiping saved jobs (browser session is kept)..."
.venv/bin/python scripts/manage-data.py clear-jobs

# A short graceful-shutdown timeout cancels in-flight scrapes on Ctrl+C; without it uvicorn
# waits for the run to finish and keeps scraping after this script exits.
say "Starting server..."
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level warning --timeout-graceful-shutdown 3 &
SERVER=$!
RUNS=""
cleanup() {
  if [ -n "$RUNS" ]; then
    pkill -P "$RUNS" 2>/dev/null || true
    kill "$RUNS" 2>/dev/null || true
  fi
  kill "$SERVER" 2>/dev/null || true
  wait "$SERVER" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM

for _ in $(seq 60); do
  curl -sf "$URL/api/health" >/dev/null && break
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo "Server failed to start." >&2
    exit 1
  fi
  sleep 0.5
done
if ! curl -sf "$URL/api/health" >/dev/null; then
  echo "Server did not answer within 30 seconds." >&2
  exit 1
fi

say "Server ready. Opening dashboard: $URL"
open "$URL"
say "Starting AIR Career Center and HigherEdJobs runs side by side. Progress lines follow."
say "If HigherEdJobs asks for verification you'll hear a sound; solve it in the browser window it opened."
(
  curl -s -X POST "$URL/api/runs/air" >/dev/null &
  AIR=$!
  curl -s -X POST -H 'content-type: application/json' -d '{}' "$URL/api/runs" >/dev/null &
  HEJ=$!
  wait "$AIR" "$HEJ" || true
  say "All runs finished. Review jobs at $URL — Ctrl+C here when done."
) &
RUNS=$!
wait $SERVER
