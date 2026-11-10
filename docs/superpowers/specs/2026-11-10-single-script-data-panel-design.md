# One launch script and a Data panel in the dashboard

Status: approved approach (A); short design for a small change.

## Intent

Today four scripts (`run.sh`, `view.sh`, `clear.sh`, `daily.sh`) cover starting, scraping and wiping.
The user wants a single script that starts the dashboard, and everything else done from the UI:
start runs, wipe the database, and delete data for one job board, so the tool is self-contained.

## Goals

- `./run.sh` is the only entry script. It builds if needed, serves the API and dashboard on the
  first free port 8000–8010, and opens the browser. It does **not** start any scrape.
- The dashboard gets a **Data** panel that lists every source present in the database with its
  job count, including leftover Company boards rows (ashby, greenhouse, lever, smartrecruiters,
  workday) that the dashboard otherwise no longer shows.
- Per source: **Delete** removes that source's jobs and everything tied to them.
- **Clear all data** wipes every job, match, analysis row and run history.
- **Fresh run** clears all data, then starts the AIR and HigherEdJobs runs (replaces `daily.sh`).

## Non-goals

- No terminal path for wiping or scraping anymore.
- No deletion by search group, date or status.
- `data/browser-state.json` (HigherEdJobs session) is never touched.

## Anti-goals

- A delete that silently removes Applied jobs or notes without the user seeing counts first.
- A delete or clear racing an in-progress scrape of the same data.

## Approaches considered

- **A (chosen):** new API endpoints plus a Data panel; delete the other scripts. Simplest, matches
  the request exactly; wiping requires the server running, which is the point.
- B: same plus thin CLI wrappers around the API. Rejected: keeps the scripts the user wants gone.
- C: same, but fresh run as one server-side endpoint under one lock. Rejected: extra endpoint to
  close a race only reachable by double-clicking; the 409 guards cover it well enough.

## Design

### API (`backend/app/main.py`, `backend/app/database.py`)

- `GET /api/data/sources` → per distinct `jobs.source`: `{source, name, jobs, applied, with_notes}`.
  `name` uses known display names (HigherEdJobs, AIR Career Center) and falls back to the raw id.
  Sources with zero jobs but run history may be omitted.
- `DELETE /api/data/sources/{source}` → deletes that source's `sponsorship_analysis`,
  `job_search_matches`, `jobs`, and `scrape_runs` rows in one transaction; returns deleted counts.
  409 if `source` is in `RUNNING`. 404 if the source has no rows.
- `DELETE /api/data` → existing `Database.clear_jobs()`; returns deleted counts. 409 if any run is
  active (`RUNNING` non-empty).
- New `Database.delete_source(source)`; deletion must not rely on SQLite foreign-key cascades
  (the old script hit orphan rows that way).
- Running `VACUUM` after a delete is optional (builder's call).

### Dashboard (`frontend/src/main.tsx` and a new component)

- A **Data** button in the toolbar opens a panel styled like **Search sources**.
- Rows: source name, job count, "N Applied · M with notes" when non-zero, **Delete** button.
- Footer: **Clear all data** and **Fresh run**.
- Every destructive action opens a confirm step (in-page, not `window.confirm`) stating the
  counts, e.g. "Delete 64 Greenhouse jobs, including 3 Applied and 1 with notes?"
- Buttons are disabled while any run is active; a 409 shows a notice instead of failing silently.
- After success: reload jobs, sources list and data panel; show a notice with what was removed.
- Fresh run: call `DELETE /api/data`, then start AIR and HigherEdJobs side by side (as `run.sh`
  did). The UI's single `activeRun` state may need a `'fresh'` value or a set; builder's call.

### Storage readout (added 2026-11-10)

The user wants to see storage used before and after a scrape, without adding load.

- Cost: only `os.stat` file sizes, no directory walks, no polling loop beyond the existing
  run-status poll, and no new dependency (no `psutil`).
- Measured: `data/jobs.sqlite3` plus its `-wal`/`-shm` files if present ("Database"), and
  `data/browser-state.json` ("Browser session").
- `scrape_runs` gets nullable `db_bytes_before` and `db_bytes_after` columns. `start_run` records
  the size before and `finish_run` records it after. Old rows stay NULL and the UI shows "—".
- `GET /api/data/storage` returns `{"database_bytes": int, "browser_session_bytes": int}`.
- The Data panel header shows the current Database and Browser session sizes. Each source row
  shows its last run's "before → after" (e.g. `12.1 MB → 12.4 MB`). The run-complete notice
  appends the same. A delete or clear also refreshes the readout.
- Claude's call: storage on disk only. RAM is out of scope, because the server's own memory
  excludes the Chromium process that does the scraping, so the number would mislead.

### Scripts and docs

- `run.sh`: drop the scrape block and `--no-scrape` flag; keep build, port pick, health wait,
  open, Ctrl+C cleanup.
- Delete `view.sh`, `clear.sh`, `daily.sh`. Remove `clear-jobs` from `scripts/manage-data.py`
  (keep `status` and `compact`).
- The "run started from the terminal" notice becomes source-neutral (another tab can still start one).
- README "Daily use" rewritten around `./run.sh` and the Data panel.

## Decisions made by Claude (user may override)

- Deletes remove Applied jobs and notes too; the confirm step shows those counts first.
- `run.sh` never auto-scrapes.

## Tests

- API: list sources with counts; delete one source leaves others intact and leaves no orphan
  matches/analysis/run rows; clear all; 409 while that source is running; 404 for unknown source.
- Dashboard: Data panel lists sources incl. a non-HEJ/AIR source, delete flow updates counts.
