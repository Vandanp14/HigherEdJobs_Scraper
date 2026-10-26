# HigherEdJobs Review

Local job discovery and sponsorship-language review based on `HigherEdJobs_PRD.md`.

## Daily use

| Command | What it does |
|---|---|
| `./daily.sh` | Morning: wipe saved jobs, then run a fresh scrape (`clear.sh` + `run.sh`). |
| `./run.sh` | Open the dashboard and scrape **without wiping**. Jobs already saved with a description are skipped, so a later run the same day only opens new listings. Statuses and notes are kept; jobs that failed before are retried. |
| `./view.sh` | Open the dashboard with the jobs already saved. Nothing is scraped or wiped. |
| `./clear.sh` | Wipe saved jobs only. Refuses while the server is running. |

`./clear.sh` (and so `./daily.sh`) **wipes all saved jobs**, including application statuses (Opened, Applied, Skipped) and notes. The saved browser session in `data/browser-state.json` is kept.

`./run.sh` rebuilds the dashboard if its source changed, serves the API and dashboard at `http://127.0.0.1:8000`, opens it, and starts the HigherEdJobs and AIR runs. Saved jobs show immediately; new ones appear as they are fetched.

If HigherEdJobs asks for human verification, you hear a sound and the terminal prints a message. Solve the check in the browser window the run opened. The run waits up to 5 minutes (`HEJ_VERIFICATION_TIMEOUT`, in seconds), saves the session, and continues. `scripts/codegen.sh` is no longer needed for daily runs.

Each job page is opened at most once: not again when another search group matches it, and not on later runs once it is saved. The "University IT Titles" group repeats the Software and Systems queries, so it is off by default; re-enable it under **Search sources** if wanted.

The terminal prints timestamped progress: each search group and results page, every job as
`✓` saved, `✗` failed (with the reason), or `↺` already saved, and totals
when each source finishes.

Only one browser window opens, for HigherEdJobs, and it reuses two tabs for the whole run so it
does not keep pulling you back to its desktop. AIR runs without a window because it has no
verification.

Press `Ctrl+C` to stop.

## Start the app for development

Open two terminals in this project folder.

**Terminal 1 — API and scraper**

```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload
```

**Terminal 2 — dashboard**

```bash
cd frontend
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`. Stop either process with `Ctrl+C`.

The HigherEdJobs browser opens visibly by default. Keep it open while a search runs; if the
site asks for verification, complete it there and let the run continue. To explicitly opt into
headless mode, add `HEJ_HEADLESS=true` to `.env` (this can cause HigherEdJobs to reject a
previously verified session).

## Use the dashboard

1. Click **Run HigherEdJobs** to run every enabled keyword query, or **Run AIR Career Center** to fetch AIR directly without running HigherEdJobs searches.
2. Use **Search sources** to enable or disable the eight HigherEdJobs groups and run either source.
3. Filter by source, date, search group, sponsorship signal, application status, or text.
4. Click an evidence excerpt to show its full source context. AIR salary and application due dates are shown in the unified table.
5. Open a listing or application link to mark a new job as **Opened**. Change the status manually as needed.

The run works sequentially to be considerate of HigherEdJobs. A small run can finish in minutes; a run with roughly 150 job listings can take 8–15 minutes.

### AIR Career Center

AIR is a curated, read-only source at `https://www.airweb.org/community/Career-Center/`.
The dashboard fetches its table, follows each listing detail page, and stores
AIR rows by `(source, source_job_id)` independently from HigherEdJobs. AIR has
no keyword groups. A missing salary remains empty, and an unparseable due date
is kept as the source text rather than guessed.

If a detail page cannot be captured, the row remains visible with
`description_status=Failed`; this is different from a successfully captured
description with `No Mention Found`. A pending row has not yet had its detail
page captured. Existing application status and notes survive AIR reruns.

For selector discovery (never commit browser storage or recorded credentials):

```bash
.venv/bin/playwright codegen \
  --save-storage data/air-browser-state.json \
  https://www.airweb.org/community/Career-Center/
```

The API also exposes `POST /api/runs/air`, `GET /api/sources`, and the
source-aware `GET /api/jobs?source=air` endpoint. AIR errors include the
listing URL where available.

Existing HigherEdJobs databases migrate on application startup: legacy rows
are assigned `source=higheredjobs`, while `higheredjobs_id` and
`higheredjobs_url` remain readable. New uniqueness uses source identity and
source URL; application status, notes, first-seen timestamps, and run history
are not reset.

## Refresh HigherEdJobs access

The scraper reuses the saved session in `data/browser-state.json`. If HigherEdJobs presents a human-verification screen or the scraper reports an access check, refresh that session:

```bash
bash scripts/codegen.sh
```

In the browser window, complete the verification manually, perform a search, visit a next page and a job listing, then close the browser. This updates `data/browser-state.json`.

## Manage local data

All job data is stored locally in `data/jobs.sqlite3`. It is a single SQLite file; nothing is uploaded.

```bash
# Show database size, job count, and browser-session size
.venv/bin/python scripts/manage-data.py status

# Save space: remove original HTML while keeping jobs, evidence, classifications, and statuses
.venv/bin/python scripts/manage-data.py compact

# Delete saved jobs and scrape history; keeps browser-state.json
.venv/bin/python scripts/manage-data.py clear-jobs
```

`clear-jobs` means a future run must collect job data again. It does not require codegen again unless HigherEdJobs asks for a new verification.

## Project commands

```bash
# Install Python dependencies into the local virtual environment
.venv/bin/python -m pip install -e '.[dev]'

# Install browser used by the scraper, if it is missing
.venv/bin/playwright install chromium

# Install frontend dependencies, if node_modules is missing
cd frontend && npm install

# Make a production frontend build
cd frontend && npm run build

# Run backend parser, migration, API, and classifier tests
.venv/bin/pytest
```

## Local files

| File or directory | Purpose |
|---|---|
| `data/jobs.sqlite3` | Saved jobs, descriptions, evidence, statuses, and run history. |
| `data/browser-state.json` | Saved HigherEdJobs browser session. Keep this file to avoid repeated verification. |
| `backend/app/` | FastAPI API, Playwright scraper, SQLite storage, parser, and classifier. |
| `backend/tests/fixtures/` | Sanitized HigherEdJobs and AIR HTML fixtures for deterministic parser tests. |
| `frontend/` | React dashboard. |
| `scripts/codegen.sh` | Starts manual browser discovery and refreshes the saved session. |
| `scripts/manage-data.py` | Checks, compacts, or clears local job data. |
