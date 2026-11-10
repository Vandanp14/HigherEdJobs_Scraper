# HigherEdJobs Review

Local job discovery and sponsorship-language review based on `HigherEdJobs_PRD.md`.

## Daily use

| Command | What it does |
|---|---|
| `./daily.sh` | Morning: wipe saved HigherEdJobs and AIR jobs, then run a fresh scrape (`clear.sh` + `run.sh`). |
| `./run.sh` | Open the dashboard and scrape **without wiping**. Jobs already saved with a description are skipped, so a later run the same day only opens new listings. Statuses and notes are kept; jobs that failed before are retried. |
| `./view.sh` | Open the dashboard with the jobs already saved. Nothing is scraped or wiped. |
| `./clear.sh` | Wipe saved HigherEdJobs and AIR jobs only. Refuses while the server is running. |

The dashboard uses port 8000, or the first free port up to 8010 if another project holds 8000; the terminal prints the URL. The scripts recognise this dashboard by its `/api/health` response, so only it, not another project, blocks `clear.sh` and a second `run.sh`. The development setup below still assumes port 8000.

`./clear.sh` (and so `./daily.sh`) **wipes saved HigherEdJobs and AIR jobs**, including their application statuses (Opened, Applied, Skipped) and notes. Company boards jobs, their statuses and notes, and the company list are kept. The saved browser session in `data/browser-state.json` is kept.

`./run.sh` rebuilds the dashboard if its source changed, serves the API and dashboard, opens it, and starts the HigherEdJobs, AIR and Company boards runs. Saved jobs show immediately; new ones appear as they are fetched.

HigherEdJobs runs only look back **14 days**: older listings are skipped, and each search stops
paging once a whole results page is older than that. Listings with no date are kept. Change it with
`HEJ_MAX_AGE_DAYS` in `.env` (`0` means no limit). AIR is a single small board and is always read in full.

If HigherEdJobs asks for human verification, you hear a sound and the terminal prints a message. Solve the check in the browser window the run opened. The run waits up to 5 minutes (`HEJ_VERIFICATION_TIMEOUT`, in seconds), saves the session, and continues. `scripts/codegen.sh` is no longer needed for daily runs.

Each job page is opened at most once: not again when another search group matches it, and not on later runs once it is saved. The "University IT Titles" group repeats the Software and Systems queries, so it is off by default; re-enable it under **Search sources** if wanted.

Keyword phrases are exact on HigherEdJobs and wildcards do not work inside quotes, so each keyword group lists its word variants (for example "web developer", "web development", "front-end developer"). The "Category:" groups leave the keyword empty and search HigherEdJobs' own job categories. They catch listings whose text never names the role, such as a "Digital Content Specialist" filed under Web Developer. The seven IT categories (Web Developer, Software Engineer/Programmer, Database Administrator, Network/System Administrator, IT Support and Training, IT Manager/Director, Other IT) are trusted: any non-teaching title is kept. Two more groups cover every other category where a scan of all 237 HigherEdJobs categories (2026-10-27) found CS titles, such as institutional research, HR systems, libraries, CIO roles, and postdoc or research roles in faculty categories; only CS titles are kept from them. HigherEdJobs allows at most 30 categories per search, so larger groups run in batches, and searches load 100 results per page. Groups are defined in `backend/app/config.py`; edits there apply on the next start and keep each group's on/off choice.

HigherEdJobs keyword search matches anywhere in a description, so keyword results are kept only when the title names a computer science / IT role (`backend/app/relevance.py`); a chemistry faculty post that mentions "data analysis" is skipped without opening its page. Teaching and academic-track roles (professor, lecturer, instructor, faculty, adjunct, tenure-track, tutor, dean, department chair) are skipped from every group, including category groups. Jobs saved before this filter stay in the database but are hidden from the dashboard. AIR listings are not filtered.

The terminal prints timestamped progress: each search group and results page, every job as
`✓` saved, `✗` failed (with the reason), or `↺` already saved, and totals
when each source finishes.

Only one browser window opens, for HigherEdJobs, and it reuses two tabs for the whole run so it
does not keep pulling you back to its desktop. AIR runs without a window because it has no
verification.

Press `Ctrl+C` to stop.

## Company boards

Early-career software roles from any company's public job board, at no cost and with no account or
API key. No search engine is used: Google blocks automated searches and its search API is closing.

1. **Company list.** Boards are found from two free public sources, Common Crawl's URL index and the
   community-maintained [SimplifyJobs new-grad list](https://github.com/SimplifyJobs/New-Grad-Positions).
   The list refreshes when it is empty or more than 7 days old. Add a company by hand with
   `.venv/bin/python scripts/add-company.py <board-or-job-url>`.
2. **Boards read.** Greenhouse, Lever, Ashby and SmartRecruiters public APIs, and Workday's career-site
   endpoint (unofficial). Every enabled company is checked on every run, one request at a time per
   ATS with `HEJ_BOARD_DELAY` seconds between requests (default 1). Different ATSes run side by side.
3. **Kept jobs.** The rules in `backend/app/early_career.py` stand in for the original search queries:
   a software engineer, developer, backend or full stack title; not senior, staff, principal, lead,
   manager, intern, or level II and above; early-career wording in the title (new grad, junior, entry
   level, associate, Software Engineer I) or the description (new grad, 2026/2027 graduate, 0-2
   years); and a US, remote or unknown location. Sponsorship wording never removes a job: it is
   labelled like any other job.

The dashboard's **Company boards** tab has a **Ranked** view (by resume fit) and an **All jobs**
view with ATS, posted-date (including past 24 hours), sponsorship, status and closed filters. The
existing For you tab stays HigherEdJobs-only.

- A board that answers 403, 429 or a challenge page is not retried: requests to that host stop for
  the run and its companies go first next time. One blocked Workday tenant skips that tenant; three
  in a row stop Workday for the run.
- A failed board keeps its saved jobs open. A job missing from a fully read board is marked closed
  and hidden (unless you applied), and reopens if it comes back. Rows are never deleted.
- With about 2,700 companies (1,300 of them Workday), a full run can take hours. Workday is the
  slowest. The dashboard shows progress and stays usable.
- Postings older than `HEJ_BOARD_MAX_AGE_DAYS` (default 7) are not saved; undated ones are kept, and
  `0` means no limit. Workday and SmartRecruiters skip the detail request for old postings, which
  shortens runs. Jobs saved before the limit are kept.
- Companies on no public list are missed. Add them with `scripts/add-company.py`.
- `.venv/bin/python scripts/run-boards.py --limit 5` runs a quick check of 5 companies per ATS from
  the terminal.

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

Sponsorship labels are tuned for an F-1 → OPT → STEM OPT → cap-exempt H-1B path (classifier 2.0.0):

- **Not Worth It** — a plain refusal, including refusing sponsorship "now or in the future", a
  "Sponsorship available: No" field, U.S.-citizens-only, or a required security clearance.
- **Likely No Sponsorship** — hedged wording such as "may not be eligible for sponsorship". Kept visible.
- **Sponsorship Possible** — sponsorship available or considered, or "Sponsorship available: Yes".
- **Unsure - Review** — visa wording that matches no rule.
- **No Mention Found** — nothing about sponsorship. "Must be authorized to work in the U.S." alone lands
  here, because OPT meets it; the sentence is still shown as evidence.

Badges under the label: **E-Verify** (needed for STEM OPT), **Cap-exempt**, and a **Non-college employer**
warning (often not cap-exempt). Pick several sponsorship labels at once with the Sponsorship chips;
results stay newest first. Saved jobs are re-labelled automatically when the classifier version changes.

1. Click **Run HigherEdJobs** to run every enabled keyword and category group, or **Run AIR Career Center** to fetch AIR directly without running HigherEdJobs searches.
2. Use **Search sources** to enable or disable the eight HigherEdJobs groups and run either source.
3. Filter by source, date, search group, sponsorship signal, application status, or text. The text search is fuzzy: words match in any order, partial words work, and small typos are tolerated ("sofware devloper" finds "Software Developer").
4. Click an evidence excerpt to show its full source context. AIR salary and application due dates are shown in the unified table.
5. Open a listing or application link to mark a new job as **Opened**. Change the status manually as needed.

The run works sequentially to be considerate of HigherEdJobs. A small run can finish in minutes; a run with roughly 150 job listings can take 8–15 minutes.

### For you

The **For you** tab ranks every saved HigherEdJobs job against your master resume. AIR listings are not ranked. Nothing is hidden: weak matches, senior roles, and sponsorship denials only move down and are dimmed.

- Put the resume at `data/resume.json` (JSON Resume layout; an optional `skill_check.declined` list names skills you do not have). Set `HEJ_RESUME` to use another path. `data/` is git-ignored, so the resume stays on this device. Edit it and restart: every job is rescored.
- **Fit (0–100)** comes mostly from skills: required skills count more than preferred ones, skills you have used in a project or job count more than listed ones, and required skills you declined count against the job. Sponsorship wording, seniority flags, and role type adjust it. "Not worth it" caps fit at 15. "No mention found" is never treated as a yes.
- **Order:** within the last 14 days, the better match wins and newer jobs only break close calls. After 14 days, age takes over; jobs older than 30 days rank below every newer one. Switch **Sort** to *Fit only* to ignore age.
- The side panel explains the selected job: required skills matched, missing skills, the sponsorship sentence, and how age moved its rank. Keys: `j`/`k` or arrows move, `Enter` opens the listing, `a` marks it applied, `Esc` collapses the panel.
- Check the weights against your own data with `.venv/bin/python scripts/fit-report.py 40 10`, which rescores and prints the top 40 and bottom 10.

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
