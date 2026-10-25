# Daily one-command run — design

## Intent

Make the dashboard practical to use every day. Today, starting it takes two terminals
(venv + `uvicorn`, then `npm run dev`). A HigherEdJobs run takes 8–15 minutes, and
human verification needs a separate `scripts/codegen.sh` step first. The user wants
one script they run while using the Mac. It gives fresh data with no prep steps.
Nothing runs overnight or unattended.

## Goals

- One command, `./daily.sh`, from the project root does everything:
  1. Wipe all saved jobs (fresh start every day; see below).
  2. Start a single server that serves both the API and the built dashboard.
  3. Open the dashboard in the default browser.
  4. Start the HigherEdJobs run (all enabled groups) and the AIR run.
- Jobs appear in the dashboard progressively as they are fetched.
- HigherEdJobs verification is handled inside the run. No separate codegen step.
- Faster HigherEdJobs runs through less duplicate work.
- `Ctrl+C` in the script's terminal stops the server and any browser it started.

## Non-goals

- Scheduled, background, or overnight runs.
- Dock icon or `.app` bundle.
- Two-pass scraping (list first, details later). Possible follow-up if this is still too slow.
- Skipping already-saved jobs. The daily wipe makes it moot.

## Anti-goals

- Reducing `HEJ_REQUEST_DELAY` or running HigherEdJobs detail pages in parallel to gain
  speed. Conservative request rates stay (AGENTS.md: Scraping & Data Integrity).
- Silent failure on a verification screen. The user must always know when the run is
  waiting on them.
- Wiping `data/browser-state.json`. The saved session must survive the daily wipe.

## Decisions (user's)

- **Trigger:** user runs the script manually while using the Mac.
- **Form:** a shell script, not a Dock icon.
- **Data:** wipe all saved jobs every run, including application statuses (`Opened`,
  `Applied`, `Skipped`) and notes. The user accepted this loss explicitly.
- **Verification:** handled in the scraper's visible browser, replacing `codegen.sh` in
  the daily flow.
- **Approach:** A (below).

## Approaches considered

- **A. One script + smarter scraper (chosen).** Script orchestrates wipe, serve, open,
  and run. Scraper dedupes across groups, drops the redundant group, and pauses on
  verification. Fixes all three pain points with modest changes.
- **B. A + two-pass scrape.** Show the full listing set within minutes, then fill in
  descriptions. Faster perceived results, but a bigger scraper change, and sponsorship
  signals stay blank for a while. Deferred.
- **C. Script only, scraper unchanged.** Script checks the session and runs codegen when
  needed. Smallest change, but no speedup and the codegen step remains. Rejected.

## How it works

### `daily.sh`

- Runs from any cwd (`cd "$(dirname "$0")"`); uses `.venv/bin/...` directly.
- Wipes jobs using the same semantics as `scripts/manage-data.py clear-jobs`: jobs,
  matches, analysis, and run history removed; `browser-state.json` kept. Tolerates a
  missing database on first run.
- Builds `frontend/dist` when missing or older than `frontend/src` (cheap staleness
  check), so `main.py`'s existing static mount serves the dashboard on one port.
- Starts `uvicorn backend.app.main:app` (no `--reload`) on `127.0.0.1:8000` and waits
  for `/api/health`.
- Opens `http://127.0.0.1:8000`.
- Triggers `POST /api/runs/air` and `POST /api/runs` (HigherEdJobs). These requests
  block until done, so fire them without blocking the script.
- Traps `INT`/`TERM` to kill the server; Playwright browsers close with it.

### Scraper: cross-group dedupe

`HigherEdJobsScraper` keeps one `seen` set per run, not per group. Today it resets per
group. When a listing was already fetched by an earlier group in this run, do not open
its detail page again. Still record the group match in `job_search_matches`, because
the matched-groups merge (PRD) must stay correct. This needs a small database method
to add a match for an existing job by source URL.

### Scraper: redundant group

The `it` group ("University IT Titles") query is a subset of the `software` and
`systems` queries. Disable it by default so existing databases stop running it. The
group stays visible and can be re-enabled in **Search sources**.

### Scraper: verification pause

When `_ensure_access` detects an access check and the browser is visible:

- Print a clear terminal message and play an audible alert (`afplay` a system sound,
  or the terminal bell).
- Poll the page until the check clears, then continue the run where it stopped.
  Poll every few seconds, up to a timeout of about 5 minutes.
- Save the context's session to `data/browser-state.json` after it clears.
- If it times out, keep today's behavior: record an error for that group, mark rows
  `Failed`, and continue.

In headless mode, keep today's behavior (fail fast).

### Docs

- Update `README.md` "Start the app" to lead with `./daily.sh`, and mention that it wipes
  saved jobs.
- Keep the two-terminal dev setup documented as the development path.

## Left to the builder

- Exact sound and message wording.
- Whether HigherEdJobs and AIR runs fire concurrently. They are different sites, so
  concurrency is fine.
- How the dashboard reflects an in-progress run. Its existing polling or refresh is
  acceptable. Adding a "waiting for verification" status to the run record is optional.
- Tests:
  - cross-group dedupe still records all group matches (fixture-driven)
  - `it` group disabled by default on fresh and migrated databases
  - verification-poll logic with a fake page
