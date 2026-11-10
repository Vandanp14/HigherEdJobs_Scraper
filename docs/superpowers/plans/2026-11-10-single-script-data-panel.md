# One Launch Script and Data Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `./run.sh` is the only script; the dashboard can run scrapes, clear all data, delete one source's data, and do a fresh run.

**Architecture:** Two `Database` methods (per-source counts, per-source delete) back three new FastAPI routes guarded by the existing in-process `RUNNING` set. A new `DataPanel` React component calls them. Shell scripts shrink to `run.sh` without auto-scrape.

**Tech Stack:** Python 3 / FastAPI / sqlite3, pytest (+ optional playwright browser tests), React + TypeScript (Vite), bash.

**Spec:** `docs/superpowers/specs/2026-11-10-single-script-data-panel-design.md`

## Global Constraints

- `data/browser-state.json` is never read, changed or deleted by any new code.
- Deletes must not rely on FK cascades: delete child rows (`sponsorship_analysis`, `job_search_matches`) explicitly, then `jobs`, then `scrape_runs`, in one transaction.
- Per-source delete returns 409 if that source is in `main.RUNNING`; clear-all returns 409 if `RUNNING` is non-empty.
- Every destructive UI action has an in-page confirm step (no `window.confirm`/`alert`) that shows job, Applied, and with-notes counts.
- `run.sh` never starts a scrape.
- Python: four-space indent, `snake_case`. TS: two-space indent, `camelCase`, `PascalCase` components.
- Tests point `main.database` at a `tmp_path` DB (pattern in `backend/tests/test_api.py`); never touch `data/jobs.sqlite3`.

## Review Focus

1. Deleting one source while a *different* source is running must succeed (only same-source is blocked). → Task 2 test `test_delete_source_allowed_while_other_source_runs`.
2. Fresh run when the clear returns 409 must not start any run. → Task 3 browser test `test_fresh_run_does_not_scrape_when_clear_is_refused`.
3. A source that has only `scrape_runs` rows (jobs already gone) is not listed, and per-source delete returns 200 removing its run rows (404 only when nothing matched) — and its run rows are removed by clear-all. → Task 1 test `test_source_counts_ignores_run_only_sources`.
4. After deleting the source currently shown on the board/filter, the dashboard reloads to an empty or page-1 view, not an error. → Task 3 browser test `test_deleting_a_source_refreshes_counts_and_jobs`.
5. Fresh run runs AIR and HigherEdJobs at once, but each scraper returns `latest_run()` with no source, so one notice can show the other source's numbers. → Task 4 fix + test `test_run_result_is_for_its_own_source`.
6. `application_status` other than `New`/`Opened` (`Applied`) and non-empty `notes` are counted; whitespace-only notes count as no notes. → Task 1 test `test_source_counts_report_applied_and_notes`.

---

### Task 1: Database counts and per-source delete

**Files:**
- Modify: `backend/app/database.py` (add methods next to `clear_jobs`, ~line 294)
- Test: `backend/tests/test_data_admin.py` (create)

**Interfaces:**
- Produces:
  - `Database.source_counts() -> list[dict]` — one dict per distinct `jobs.source` with ≥1 job: `{"source": str, "jobs": int, "applied": int, "with_notes": int}`, ordered by `jobs` desc then `source`. `applied` = rows with `application_status='Applied'`; `with_notes` = rows with `TRIM(notes) <> ''`.
  - `Database.delete_source(source: str) -> dict` — returns `{"jobs": int, "runs": int}` deleted counts; `{"jobs": 0, "runs": 0}` if nothing matched (caller decides 404).
  - `Database.clear_jobs() -> dict` — now returns `{"jobs": int, "runs": int}` (behaviour otherwise unchanged).

- [ ] **Step 1: Write failing tests** in `backend/tests/test_data_admin.py`. Seed with `JobDraft` via `database.upsert(...)` plus `database.add_match(job_id, "<a real group id from config.SEARCH_GROUPS>")` and `database.start_run([], source=...)`; set Applied/notes with `database.update_job(id, {"application_status": "Applied"})` / `{"notes": "x"}`. Tests:
  - `test_source_counts_report_applied_and_notes`: 2 higheredjobs (1 Applied, 1 notes `"x"`), 1 greenhouse with notes `"   "` → `[{"source":"higheredjobs","jobs":2,"applied":1,"with_notes":1},{"source":"greenhouse","jobs":1,"applied":0,"with_notes":0}]`.
  - `test_delete_source_removes_only_that_source_and_its_children`: after `delete_source("greenhouse")` returns `{"jobs":1,"runs":1}`; no `jobs`, `job_search_matches`, `sponsorship_analysis` rows reference deleted ids (query each table with `WHERE job_id NOT IN (SELECT id FROM jobs)` → 0); higheredjobs jobs, matches and runs untouched.
  - `test_delete_source_unknown_returns_zero`: `delete_source("nope") == {"jobs":0,"runs":0}`.
  - `test_source_counts_ignores_run_only_sources`: a `start_run([], source="lever")` with no lever jobs → `lever` absent from `source_counts()`; `clear_jobs()` returns `runs` ≥ 1 and leaves 0 `scrape_runs`.
  - `test_clear_jobs_returns_counts`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_data_admin.py -v` → FAIL (`AttributeError: ... source_counts`).
- [ ] **Step 3: Implement** the three methods. Use `with self.connection:` for the transaction; count rows before deleting (or use `cursor.rowcount`).
- [ ] **Step 4: Run** `.venv/bin/pytest backend/tests/test_data_admin.py backend/tests/test_daily_database.py -v` → PASS.
- [ ] **Step 5: Commit** `git commit -m "Add per-source counts and delete to the database"`.

### Task 2: Data API routes

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_data_admin.py` (append API tests)

**Interfaces:**
- Consumes: Task 1 methods.
- Produces:
  - `GET /api/data/sources` → `[{"source","name","jobs","applied","with_notes"}]`. `name`: `{"higheredjobs":"HigherEdJobs","air":"AIR Career Center","greenhouse":"Greenhouse","lever":"Lever","ashby":"Ashby","workday":"Workday","smartrecruiters":"SmartRecruiters"}`, else the raw id.
  - `DELETE /api/data/sources/{source}` → `{"deleted": {"jobs","runs"}}`; 404 `"No saved data for this source"` when jobs==0 and runs==0; 409 `"A run for this source is in progress"` when `source in RUNNING`.
  - `DELETE /api/data` → `{"deleted": {"jobs","runs"}}`; 409 `"Stop running scrapes before clearing data"` when `RUNNING` non-empty.

- [ ] **Step 1: Write failing tests** (use `TestClient(main.app)`, swap `main.database` as in `test_api.py`, and `main.RUNNING.add(...)` / `discard` in `try/finally`):
  - `test_data_sources_lists_every_source_with_names` (includes a `greenhouse` row → name `"Greenhouse"`, and an unknown `"foo"` → name `"foo"`).
  - `test_delete_source_endpoint_deletes_and_404s_after` (second call → 404).
  - `test_delete_source_blocked_while_that_source_runs` → 409, rows still there.
  - `test_delete_source_allowed_while_other_source_runs` (`RUNNING={"higheredjobs"}`, delete `air`) → 200.
  - `test_clear_all_blocked_while_any_run_active` → 409; with empty `RUNNING` → 200 and `/api/data/sources` returns `[]`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_data_admin.py -v` → new tests FAIL (404 from static mount or 405).
- [ ] **Step 3: Implement** routes in `main.py`, declared **before** the `StaticFiles` mount.
- [ ] **Step 4: Run** `.venv/bin/pytest backend/tests -q` → all PASS (browser tests may skip).
- [ ] **Step 5: Commit** `git commit -m "Add data management API endpoints"`.

### Task 3: Data panel and fresh run in the dashboard

**Files:**
- Create: `frontend/src/DataPanel.tsx`
- Modify: `frontend/src/main.tsx` (toolbar ~line 238, panel area ~line 246, `activeRun` type line 52, terminal notice line 121), `frontend/src/types.ts` (add `DataSource`), `frontend/src/index.css` (reuse `.sources` styles; add only what the confirm row needs)
- Test: `backend/tests/test_data_panel_dashboard.py` (create; copy the uvicorn-thread + `playwright` fixture pattern and `frontend/dist` skip from `test_dashboard_pagination.py`)

**Interfaces:**
- Consumes: Task 2 routes.
- Produces:
  - `type DataSource = { source: string; name: string; jobs: number; applied: number; with_notes: number }` in `types.ts`.
  - `DataPanel` props: `{ busy: boolean; onClose(): void; onChanged(message: string): Promise<void>; onFreshRun(): Promise<void> }`. It fetches `/api/data/sources` on mount and after each action.
  - `activeRun` union gains `'fresh'`.

- [ ] **Step 1: Write failing browser tests** (accessible names are the contract):
  - `test_data_panel_lists_sources_including_leftover_boards`: seed 2 higheredjobs + 1 greenhouse; click button named `Data`; panel (`role=region` name `Data`) shows rows `HigherEdJobs` "2 jobs" and `Greenhouse` "1 job".
  - `test_deleting_a_source_refreshes_counts_and_jobs`: click `Delete Greenhouse` → confirm text contains `Delete 1 Greenhouse job` → click `Confirm delete` → Greenhouse row gone, notice contains `Deleted 1 Greenhouse job`. Cancel path: `Cancel` leaves the row.
  - `test_clear_all_shows_applied_and_notes_counts`: one Applied + one with notes → clicking `Clear all data` shows text containing `1 Applied` and `1 with notes`; `Confirm clear` → panel shows `No saved data`, job table total `0`.
  - `test_fresh_run_does_not_scrape_when_clear_is_refused`: add `"air"` to `main.RUNNING` in the test; `Fresh run` → `Confirm fresh run` → notice contains `Stop running scrapes before clearing data`; assert via monkeypatched `HigherEdJobsScraper.run`/`AIRScraper.run` call counters that neither was called; rows still present.
- [ ] **Step 2: Build and run** `(cd frontend && npm run build) && .venv/bin/pytest backend/tests/test_data_panel_dashboard.py -v` → FAIL (no `Data` button).
- [ ] **Step 3: Implement** `DataPanel.tsx` and wire it in `main.tsx`:
  - Toolbar button `Data` (lucide `Database` icon) toggles the panel; opening it closes Search sources and vice versa.
  - Confirm copy: `Delete {jobs} {name} job(s){, including N Applied}{ and M with notes}?` / `Clear all data: {total} job(s){…}? Run history goes too.` / fresh run: same as clear plus `Then run AIR and HigherEdJobs.` Buttons `Confirm delete` / `Confirm clear` / `Confirm fresh run` and `Cancel`.
  - All panel actions disabled when `busy` (`Boolean(activeRun) || externalRun`).
  - On a non-OK response show the API `detail` in the notice; do not throw past the panel.
  - `onChanged`: `setPage(1)`, `await load()`, `setNotice(message)`.
  - Fresh run in `main.tsx`: `beginRun('fresh')`; `DELETE /api/data`; if it fails → notice with detail, `finishRun()`, stop. Else fire `POST /runs/air` and `POST /runs` (body `'{}'`) with `Promise.allSettled`, then notice summarising both results like `runAir`/`runHigherEdJobs` do, `await load()`, `finishRun()`. Progress banner label for `'fresh'`: `Fresh run (AIR + HigherEdJobs)`.
  - Line 121 notice → `'A run started elsewhere is in progress — new jobs appear automatically.'`
- [ ] **Step 4: Build and run** `(cd frontend && npm run build) && .venv/bin/pytest backend/tests -q` → PASS, browser tests not skipped.
- [ ] **Step 5: Commit** `git commit -m "Add Data panel with delete, clear and fresh run"`.

### Task 4: Storage readout before and after runs

**Files:**
- Modify: `backend/app/database.py` (`__init__` stores `self.path = path`; `_migrate_columns` adds `scrape_runs.db_bytes_before INTEGER`, `scrape_runs.db_bytes_after INTEGER`; `start_run`, `finish_run`), `backend/app/main.py`, `frontend/src/DataPanel.tsx`, `frontend/src/main.tsx` (run-complete notices), `frontend/src/types.ts` (`Run` gains `db_bytes_before?: number | null; db_bytes_after?: number | null`)
- Test: `backend/tests/test_data_admin.py`, `backend/tests/test_data_panel_dashboard.py`

**Interfaces:**
- Consumes: Task 2 routes, Task 3 `DataPanel`.
- Produces:
  - `Database.storage_bytes() -> int` — sum of `os.stat` sizes for `self.path` and `self.path` + `-wal` / `-shm` when they exist.
  - `start_run` sets `db_bytes_before = storage_bytes()`; `finish_run` sets `db_bytes_after = storage_bytes()`. `close_interrupted_runs` leaves `db_bytes_after` NULL.
  - `GET /api/data/storage` → `{"database_bytes": int, "browser_session_bytes": int}`; `browser_session_bytes` = size of `settings.state_path` (0 if missing). Read-only — never opens the file.
  - Frontend `formatBytes(bytes: number | null | undefined): string` in `DataPanel.tsx` (exported): `null/undefined → '—'`, `< 1024 → 'N B'`, KB/MB/GB with one decimal.

- [ ] **Step 1: Write failing tests:**
  - `test_runs_record_storage_before_and_after`: `start_run` then insert jobs then `finish_run` → `latest_run()["db_bytes_before"] > 0` and `db_bytes_after >= db_bytes_before`.
  - `test_legacy_runs_have_null_storage`: run a migration on a DB whose `scrape_runs` lacks the columns (pattern: `test_legacy_database_gets_source_columns_without_losing_identity`) → old row has `None` for both.
  - `test_storage_endpoint_reports_sizes`: returns ints; `browser_session_bytes == 0` when the setting points to a missing tmp path; file at that path unchanged (mtime equal) when it exists.
  - Browser: `test_data_panel_shows_storage`: panel contains `Database` and a size matching `/\d+(\.\d)? (B|KB|MB)/`; a source row with a finished run shows `→`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_data_admin.py -v` → FAIL.
- [ ] **Step 3: Implement** per Interfaces. The panel fetches `/api/data/storage` alongside `/api/data/sources` (mount, after actions, and when `activeRun` goes back to null), and the last-run before → after per row from the existing `/api/sources` `last_run` (HEJ/AIR only; other sources show nothing). In `backend/app/scraper.py` lines 63 and 270, return `self.database.latest_run("higheredjobs")` / `latest_run("air")` instead of `latest_run()`, so a fresh run running both side by side reports each source's own numbers (add `test_run_result_is_for_its_own_source`). `runAir`/`runHigherEdJobs`/fresh-run notices append ` Storage {before} → {after}.` when both are present.
- [ ] **Step 4: Build and run** `(cd frontend && npm run build) && .venv/bin/pytest backend/tests -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "Show storage before and after each scrape run"`.

### Task 5: Single launch script and docs

**Files:**
- Modify: `run.sh`, `scripts/manage-data.py`, `scripts/server.sh` (header comment only), `README.md` ("Daily use" section and run-button list), `AGENTS.md` only if it names removed scripts
- Delete: `view.sh`, `clear.sh`, `daily.sh`

- [ ] **Step 1:** `run.sh`: remove `SCRAPE`/`--no-scrape`, the `RUNS` subshell and its cleanup branch; after opening the URL print `Dashboard ready. Run scrapes and manage data from the dashboard. Ctrl+C to stop.` then `wait $SERVER`. Keep build, already-running check, port pick, health wait, `trap cleanup EXIT`.
- [ ] **Step 2:** `scripts/manage-data.py`: drop `clear-jobs` (choices `("status", "compact")`) and its branch.
- [ ] **Step 3:** `git rm view.sh clear.sh daily.sh`; `grep -rn "view.sh\|clear.sh\|daily.sh\|clear-jobs\|no-scrape" --exclude-dir=node_modules --exclude-dir=docs .` → no hits outside historical docs.
- [ ] **Step 4:** README "Daily use": one-row table for `./run.sh`; describe Data panel (per-source delete incl. leftover Company boards rows, Clear all data, Fresh run = old `daily.sh`), that deletes include Applied/notes after a counted confirm, and that the browser session is kept.
- [ ] **Step 5: Verify** `bash -n run.sh && .venv/bin/python scripts/manage-data.py status && .venv/bin/pytest backend/tests -q` → syntax OK, status prints, tests PASS. Then start `./run.sh`, confirm it opens without scraping (no `[hej]`/`[air]` progress lines in 10 s), Ctrl+C exits cleanly.
- [ ] **Step 6: Commit** `git commit -m "Make run.sh the only launch script"`.
