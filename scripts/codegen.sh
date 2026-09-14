#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
.venv/bin/playwright codegen \
  --target python-async \
  --save-storage data/browser-state.json \
  --output scripts/recording.py \
  https://www.higheredjobs.com/search/advanced.cfm
