#!/usr/bin/env bash
# Serve the dashboard and open it. Nothing is scraped or wiped here: start runs and manage
# saved data (delete, clear, fresh run) from the dashboard's Run buttons and Data panel.
set -euo pipefail
cd "$(dirname "$0")"

source scripts/server.sh
say() { echo "$(date +%H:%M:%S) [run] $*"; }

RUNNING=$(running_url)
if [ -n "$RUNNING" ]; then
  echo "The dashboard is already running at $RUNNING — use it, or stop it with Ctrl+C first." >&2
  exit 1
fi
PORT=$(free_port) || { echo "No free port between 8000 and 8010." >&2; exit 1; }
URL="http://127.0.0.1:$PORT"

scripts/build-dashboard.sh

# A short graceful-shutdown timeout cancels in-flight scrapes on Ctrl+C; without it uvicorn
# waits for the run to finish and keeps scraping after this script exits.
say "Starting server..."
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning --timeout-graceful-shutdown 3 &
SERVER=$!
cleanup() {
  kill "$SERVER" 2>/dev/null || true
  wait "$SERVER" 2>/dev/null || true
  rm -f "$PORT_FILE"
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

echo "$PORT" > "$PORT_FILE"
say "Server ready. Opening dashboard: $URL"
open "$URL"
say "Dashboard ready. Run scrapes and manage data from the dashboard. Ctrl+C to stop."
wait $SERVER
