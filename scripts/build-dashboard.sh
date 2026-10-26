#!/usr/bin/env bash
# Rebuild frontend/dist when the dashboard source is newer than the last build.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  echo "$(date +%H:%M:%S) [build] Building dashboard (frontend changed)..."
  (cd frontend && npm run build >/dev/null)
fi
