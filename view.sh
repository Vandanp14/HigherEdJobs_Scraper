#!/usr/bin/env bash
# Open the dashboard with the jobs already saved. Nothing is scraped or wiped.
exec "$(dirname "$0")/run.sh" --no-scrape
