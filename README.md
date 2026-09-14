# HigherEdJobs Review

Local job discovery and sponsorship-language review based on `HigherEdJobs_PRD.md`.

## Start the app

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

## Use the dashboard

1. Click **Run all searches** to run every enabled query.
2. Use **Search groups** to enable or disable the eight fixed searches.
3. Filter by date, search group, sponsorship signal, application status, or text.
4. Click an evidence excerpt to show its full source context.
5. Open a listing or application link to mark a new job as **Opened**. Change the status manually as needed.

The run works sequentially to be considerate of HigherEdJobs. A small run can finish in minutes; a run with roughly 150 job listings can take 8–15 minutes.

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
python3 scripts/manage-data.py status

# Save space: remove original HTML while keeping jobs, evidence, classifications, and statuses
python3 scripts/manage-data.py compact

# Delete saved jobs and scrape history; keeps browser-state.json
python3 scripts/manage-data.py clear-jobs
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
```

## Local files

| File or directory | Purpose |
|---|---|
| `data/jobs.sqlite3` | Saved jobs, descriptions, evidence, statuses, and run history. |
| `data/browser-state.json` | Saved HigherEdJobs browser session. Keep this file to avoid repeated verification. |
| `backend/app/` | FastAPI API, Playwright scraper, SQLite storage, parser, and classifier. |
| `frontend/` | React dashboard. |
| `scripts/codegen.sh` | Starts manual browser discovery and refreshes the saved session. |
| `scripts/manage-data.py` | Checks, compacts, or clears local job data. |
