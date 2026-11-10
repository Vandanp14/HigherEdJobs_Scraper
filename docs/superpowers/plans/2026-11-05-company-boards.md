# Company Boards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find early-career software roles at any company, for free, by listing companies from public data, reading their public ATS boards, and applying the user's 18 queries as local rules, shown in dedicated dashboard views.

**Architecture:** `backend/app/sources/` holds URL parsing, company discovery, one adapter per ATS, and an async runner. Kept jobs go through `Database.upsert_job`, so existing labels apply. A new `ats_companies` table tracks boards. The frontend adds a Company boards area with Ranked and All jobs views.

**Tech Stack:** Python 3.11, FastAPI, SQLite, httpx (`MockTransport` in tests), React/Vite, pytest with Playwright browser tests.

**Spec:** `docs/superpowers/specs/2026-11-05-company-boards-design.md`

## Global Constraints

- No Google, Bing or paid API. No API keys.
- No CAPTCHA solving, fingerprint spoofing, proxy rotation, or retrying through a block.
- `User-Agent` is `job-board-reader/1.0`. Never include personal contact details.
- Default delay is 1 second per ATS, set by `HEJ_BOARD_DELAY`, floor 0.5.
- `BOARD_SOURCES = ("greenhouse", "lever", "ashby", "workday", "smartrecruiters")`, defined in `backend/app/config.py`.
- The existing For you tab stays HigherEdJobs-only. `SEARCH_GROUPS` and the HigherEdJobs and AIR scrapers don't change.
- Never delete `jobs` rows for board sources. Never overwrite `application_status` or `notes` on rerun.
- A failed board fetch never closes jobs and never reads as "no sponsorship mention".
- Style: four-space Python, two-space TypeScript. Commit subjects are short and imperative, like `Add board URL parsers`.
- Every commit message ends with `Claude-Session: https://claude.ai/code/session_019L5ef8u6tAG1insvwQhfRW`.
- Never stage `frontend/package-lock.json` or `RESUME_DESCRIPTION.md`. They hold the user's uncommitted work.
- Baseline before this work: `.venv/bin/pytest -q` gives 370 passed. Run `npm run build` in `frontend/` before browser tests, or they skip.

## Review Focus

Each line has a pinned test in its owning task.

1. **Workday job paths repeat across tenants:** two companies with the same `externalPath` stay separate jobs (Task 4).
2. **Escaped Greenhouse `content`:** `&lt;p&gt;` HTML becomes plain text, and sponsorship evidence is a substring of the shown description (Task 4).
3. **Board job with no posted date:** it appears in date windows by `first_seen_at`, not vanishing as HigherEdJobs rows do (Task 6).
4. **The user applied, then the job closed:** it stays visible (Task 6).
5. **A boards run lasting hours:** HigherEdJobs and AIR buttons stay usable, and the dashboard shows progress (Task 8).

---

### Task 1: Query rules

**Files:**
- Create: `backend/app/early_career.py`
- Test: `backend/tests/test_early_career.py`

**Interfaces:**
- Produces: `title_candidate(title: str | None) -> bool` (rules 1 and 2), `early_career(title: str | None, description: str | None) -> bool` (rule 3), `location_allowed(location: str | None) -> bool` (rule 4), `keep_job(title, location, description) -> bool` (all), `WORKDAY_SEARCH_TERMS: tuple[str, ...]`.

- [ ] **Step 1: Write failing parametrized tests**

```python
@pytest.mark.parametrize("title", [
    "Software Engineer I", "Software Engineer 1", "Associate Software Engineer",
    "Software Developer I", "Junior Software Engineer", "Software Engineer, New Grad",
    "New Grad Software Engineering", "Backend Engineer, Entry Level",
    "Full Stack Developer - Early Career", "Frontend Software Engineer I",
])
def test_kept_on_title(title):
    assert keep_job(title, "Remote", None)

@pytest.mark.parametrize("title", [
    "Software Engineer II", "Software Engineer III", "Senior Software Engineer",
    "Sr. Software Engineer", "Staff Software Engineer", "Principal Software Engineer",
    "Lead Software Developer", "Software Engineering Manager", "Software Engineer Intern",
    "Software Engineering Internship", "Associate Product Manager", "Mobile Engineer I",
    "Data Engineer I", "Help Desk Technician",
])
def test_dropped_on_title(title):
    assert not keep_job(title, "Remote", "new grad")

@pytest.mark.parametrize("description", [
    "open to new grads", "New Graduate role", "2026 graduate", "2027 graduate",
    "0-2 years of experience", "0 to 2 years", "0 years of experience",
])
def test_plain_title_kept_on_description(description):
    assert keep_job("Software Engineer", "New York, NY", description)

@pytest.mark.parametrize("description", ["10-20 years", "20 years of experience", "5 years", None])
def test_plain_title_dropped_without_signal(description):
    assert not keep_job("Software Engineer", "New York, NY", description)

@pytest.mark.parametrize("location", [
    None, "", "Remote", "United States", "Seattle, San Francisco, New York City",
    "Toronto, Canada or New York, NY", "Austin, TX", "Remote - USA",
])
def test_location_allowed(location):
    assert location_allowed(location)

@pytest.mark.parametrize("location", ["Israel, Yokneam", "London, United Kingdom", "Remote - Canada", "Bengaluru, India"])
def test_location_rejected(location):
    assert not location_allowed(location)

def test_sponsorship_wording_never_removes_a_job():
    assert keep_job("Software Engineer I", "Remote", "We are unable to sponsor visas.")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_early_career.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/early_career.py`**

Compiled, case-insensitive regexes at module top so the user can edit them. Rule 1 matches `software (engineer|engineering|developer)`, `SDE`, `SWE`, `back[- ]?end (engineer|developer)`, `full[- ]?stack (engineer|developer)`. Rule 2 excludes `senior`, `sr\.?`, `staff`, `principal`, `lead`, `manager`, `intern(ship)?`, and level `II`, `III`, `IV`, `2`, `3`, `4` after engineer or developer. Rule 3's description numbers need `\b0` so `10-20 years` can't match. Location rejects only when a non-US country or major non-US city matches and no US marker does (United States, USA, US, state names or abbreviations, major US cities). `WORKDAY_SEARCH_TERMS = ("software engineer", "software developer", "backend engineer", "full stack developer")`. Add a comment that the user's 18 queries are the source, listing them from the spec.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest backend/tests/test_early_career.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/early_career.py backend/tests/test_early_career.py
git commit -m "Add early-career job rules from the search queries"
```

---

### Task 2: Company table and database methods

**Files:**
- Modify: `backend/app/config.py`, `backend/app/database.py`, `backend/app/parser.py`
- Test: `backend/tests/test_board_database.py`, `backend/tests/test_daily_database.py`

**Interfaces:**
- Produces in `sources/refs.py`: `@dataclass(frozen=True) BoardRef(ats: str, slug: str, host: str = "", site: str = "")`.
- Produces on `Database`:
  - `upsert_company(ref: BoardRef, name: str | None, discovered_via: str) -> bool` (True if new)
  - `companies(enabled_only: bool = True) -> list[dict]`, oldest `last_checked_at` first, never-checked first
  - `record_company_check(company_id: int, error: str | None = None, missing: bool = False) -> None`
  - `save_board_job(company_id: int, draft: JobDraft) -> tuple[int, bool]`
  - `known_job_ids(company_id: int) -> set[str]`: `source_job_id` values with `description_status='Complete'`
  - `reconcile_board(company_id: int, seen_ids: set[str], complete: bool) -> int`: closed count
  - `update_run_progress(run_id: int, discovered: int, new: int, updated: int, summary: dict) -> None`
  - `finish_run(..., summary: dict | None = None)`, keeping existing callers working
- Produces in `database.py`: `FIT_SOURCES = ("higheredjobs", *BOARD_SOURCES)`. In `parser.py`: `normalize_ats_description(raw: str) -> str`.

Schema details. `ats_companies(id INTEGER PRIMARY KEY, ats TEXT NOT NULL, slug TEXT NOT NULL, host TEXT NOT NULL DEFAULT '', site TEXT NOT NULL DEFAULT '', name TEXT, discovered_via TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_checked_at TEXT, last_success_at TEXT, consecutive_failures INTEGER NOT NULL DEFAULT 0, last_error TEXT)`. Unique index on `(ats, slug COLLATE NOCASE, site COLLATE NOCASE)`. `site` is `NOT NULL` because SQLite treats NULLs as distinct, which would break uniqueness. New columns: `jobs.ats_company_id INTEGER`, `scrape_runs.summary TEXT NOT NULL DEFAULT '{}'`.

- [ ] **Step 1: Write failing tests**

```python
def test_company_upsert_is_case_insensitive_and_keeps_first_slug(db):
    assert db.upsert_company(BoardRef("greenhouse", "Stripe"), None, "commoncrawl")
    assert not db.upsert_company(BoardRef("greenhouse", "stripe"), "Stripe", "simplify")
    assert [c["slug"] for c in db.companies()] == ["Stripe"]

def test_five_404s_disable_but_other_errors_do_not(db):
    # record_company_check(id, error="404", missing=True) x5 -> companies() empty
    # record_company_check(id2, error="500") x5 -> still enabled, last_error "500"
    # a success resets consecutive_failures to 0

def test_never_checked_companies_come_first(db): ...

def test_reconcile_closes_missing_and_reopens_seen(db):
    # save two jobs, reconcile seen={first}, complete=True -> returns 1, second active=0
    # reconcile seen={first, second}, complete=True -> second active=1, last_seen_at updated

def test_incomplete_fetch_closes_nothing(db):
    # reconcile seen=set(), complete=False -> returns 0, all active=1

def test_rerun_keeps_status_and_notes(db):
    # update_job(status Applied, notes), save_board_job again -> both unchanged

def test_clear_jobs_keeps_board_rows(db):
    # seed higheredjobs, air, greenhouse jobs; set greenhouse status Applied with notes
    # clear_jobs -> only greenhouse remains, with status, notes and sponsorship_analysis row
    # scrape_runs: 'boards' and 'discovery' rows remain, others deleted; ats_companies untouched

def test_fit_scores_board_jobs_but_not_air(db_with_resume):
    # greenhouse job gets fit_score; air job stays None; rescore_fit includes greenhouse

def test_board_reanalyze_uses_ats_normalizer(db): ...

def test_summary_saved_on_finish_and_returned_by_latest_run(db): ...
```

Fill in commented bodies with those assertions. Reuse the existing fixture pattern from `backend/tests/test_fit_storage.py`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_board_database.py -q`
Expected: FAIL on import of `BoardRef`.

- [ ] **Step 3: Implement**

Add the above. `clear_jobs` becomes parameterized deletes: `DELETE FROM jobs WHERE source NOT IN (...)` (foreign keys are on, so labels and matches cascade), and `DELETE FROM scrape_runs WHERE source NOT IN ('boards','discovery')`. `save_board_job` calls `upsert_job` and then sets `ats_company_id`. Catch `sqlite3.IntegrityError` in the runner (Task 5), not here. Replace `database.py:440,460` checks with `FIT_SOURCES`. In `reanalyze`, use `normalize_ats_description` when `source in BOARD_SOURCES`. Update `scripts/fit-report.py:30` to pass `source=",".join(FIT_SOURCES)` after Task 6 lands, and note it there. Add `latest_run` JSON decoding for `summary`.

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -q`
Expected: all pass, including `test_daily_database.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "Add company table and keep board jobs through wipes"
```

---

### Task 3: URL parsers and company discovery

**Files:**
- Create: `backend/app/sources/__init__.py`, `sources/refs.py` (if not made in Task 2), `sources/client.py`, `sources/discovery.py`, `scripts/add-company.py`
- Modify: `pyproject.toml` (move `httpx>=0.28,<1` to runtime `dependencies`), `backend/app/config.py`
- Test: `backend/tests/test_board_refs.py`, `backend/tests/test_discovery.py`

**Interfaces:**
- Produces: `parse_board_url(url: str) -> BoardRef | None` in `sources/refs.py`.
- Produces in `sources/client.py`:
  - `class BoardBlocked(Exception)` with `host: str, retry_after: str | None`
  - `class BoardMissing(Exception)` (404), `class BoardError(Exception)` (other failures)
  - `class BoardClient(delay: float, transport: httpx.AsyncBaseTransport | None = None)`, with `async get_json(url, key: str)` and `async post_json(url, body, key: str)`. `key` is the rate-limit group, the ATS name. Async context manager.
- Produces in `sources/discovery.py`: `async refresh_companies(database, client) -> dict` returning `{"found": int, "new": int, "errors": list[dict]}`, and `companies_stale(database, max_age_days: int = 7) -> bool`. Each refresh writes a `scrape_runs` row with `source='discovery'`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("url,expected", [
    ("https://job-boards.greenhouse.io/0verwatch?error=true", BoardRef("greenhouse", "0verwatch")),
    ("https://boards.greenhouse.io/stripe/jobs/123", BoardRef("greenhouse", "stripe")),
    ("https://jobs.lever.co/100ms/4c9f19c7?utm_source=x", BoardRef("lever", "100ms")),
    ("https://jobs.ashbyhq.com/ramp/34413f8d", BoardRef("ashby", "ramp")),
    ("https://jobs.smartrecruiters.com/Visa/123", BoardRef("smartrecruiters", "Visa")),
    ("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/X",
     BoardRef("workday", "nvidia", "nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite")),
    ("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite",
     BoardRef("workday", "nvidia", "nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite")),
])
def test_parse_board_url(url, expected): ...

@pytest.mark.parametrize("url", [
    "https://job-boards.greenhouse.io/", "https://job-boards.greenhouse.io/embed/job_app",
    "https://nvidia.wd5.myworkdayjobs.com/", "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/x",
    "https://example.com/careers", "not a url", "",
])
def test_parse_rejects(url): assert parse_board_url(url) is None

# client, using httpx.MockTransport
async def test_404_raises_missing(): ...
async def test_429_raises_blocked_with_retry_after(): ...
async def test_403_raises_blocked(): ...
async def test_html_on_200_raises_blocked():  # a challenge page is not JSON
async def test_500_raises_board_error(): ...
async def test_user_agent_is_generic():  # equals "job-board-reader/1.0"

# discovery, using MockTransport for CDX and SimplifyJobs
async def test_refresh_merges_both_sources_and_names_from_simplify(db): ...
async def test_cdx_504_retries_then_keeps_existing_list_and_reports(db):
    # seeded company survives; errors non-empty; SimplifyJobs results still saved
async def test_stale_when_empty_or_over_seven_days(db): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_board_refs.py backend/tests/test_discovery.py -q`
Expected: FAIL on import.

- [ ] **Step 3: Implement**

`BoardClient` keeps one `asyncio.Lock` and last-request time per `key`. Timeout 30 seconds. `BoardBlocked.host` is the URL host, so Workday tenants differ. Discovery reads the newest collection from `https://index.commoncrawl.org/collinfo.json`, then for each of `job-boards.greenhouse.io/*`, `boards.greenhouse.io/*`, `jobs.lever.co/*`, `jobs.ashbyhq.com/*`, `*.myworkdayjobs.com`, `jobs.smartrecruiters.com/*` asks `showNumPages=true`, then walks pages with `output=json&fl=url`, using key `commoncrawl`. Retry `5xx` 3 times with waits of 5, 15 and 45 seconds, patched to zero in tests. SimplifyJobs URL: `https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json`. Use all rows regardless of `active`, since an old posting still proves the board exists. `scripts/add-company.py <board-url>` uses `parse_board_url`, prints what it added, exits non-zero on an unrecognized URL.

- [ ] **Step 4: Run, install, then measure**

Run: `.venv/bin/python -m pip install -e '.[dev]' && .venv/bin/pytest -q`
Expected: all pass.

Then run a one-off refresh against a scratch database at the scratchpad path (`HEJ_DATABASE` must stay relative to the repo, so use a small Python snippet that builds `Database(Path(...))`). Report companies per ATS and estimated run time at 1 second per request to the coordinator. Don't touch `data/jobs.sqlite3`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml backend/app backend/tests scripts/add-company.py
git commit -m "Add board URL parsers and free company discovery"
```

---

### Task 4: Greenhouse, Lever and Ashby adapters

**Files:**
- Create: `backend/app/sources/adapters.py` (shared `BoardFetch`), `sources/greenhouse.py`, `sources/lever.py`, `sources/ashby.py`
- Create: `backend/tests/fixtures/boards/{greenhouse,lever,ashby}.json` (real responses trimmed to 3 jobs, at least one early-career), `*_empty.json`, `*_changed.json`
- Test: `backend/tests/test_board_adapters.py`

**Interfaces:**
- Consumes: `BoardClient`, `normalize_ats_description`, `JobDraft`.
- Produces: `@dataclass BoardFetch(drafts: list[JobDraft], seen_ids: set[str], complete: bool)`.
- Produces in each module: `async fetch_board(client: BoardClient, company: dict, known_ids: set[str]) -> BoardFetch`. Adapters ignore `known_ids` here, because one list response has everything.
- `source_job_id` is always `f"{company['slug']}:{ats_id}"`, so `seen_ids` and rows can't collide across companies.

| ATS | `source_url` | `apply_url` | `posted_date` (UTC `YYYY-MM-DD`) | `raw_description` | `institution` |
|---|---|---|---|---|---|
| greenhouse | `https://job-boards.greenhouse.io/{slug}/jobs/{id}` | `absolute_url` | `first_published`, else `updated_at` | `content` | `company_name`, else company name, else slug |
| lever | `hostedUrl` | `applyUrl` | `createdAt` (ms) | `description` + each `lists[]` `text`/`content` + `additional` | company name, else slug |
| ashby | `jobUrl` | `applyUrl` | `publishedAt` | `descriptionHtml` | company name, else slug |

Ashby skips `isListed: false`. Set `description_status="Complete"` when text exists and `higheredjobs_url=None` (`__post_init__` handles `source_url`). `source_url` for Greenhouse is built instead of using `absolute_url`, because `absolute_url` can point to a shared company page, and `jobs.higheredjobs_url` is globally unique.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("module", [greenhouse, lever, ashby])
async def test_parses_fixture(module): ...  # exact title, url, posted_date, source, id prefix for one known job

async def test_greenhouse_escaped_content_becomes_plain_text():
    # content "&lt;p&gt;We cannot &lt;b&gt;sponsor&lt;/b&gt; visas&lt;/p&gt;"
    # normalized_description == "We cannot sponsor visas"; classify evidence in normalized_description

async def test_empty_board_is_complete_with_no_jobs(module): ...  # complete True, seen_ids empty

async def test_changed_format_raises_parse_error(module): ...

async def test_ashby_skips_unlisted(): ...

async def test_same_ats_id_in_two_companies_keeps_distinct_rows(db):
    # review focus 1, same pattern across adapters; saved rows == 2

async def test_lever_description_includes_lists_and_additional(): ...

async def test_missing_dates_give_none_not_crash(module): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_board_adapters.py -q`
Expected: FAIL on import.

- [ ] **Step 3: Implement the adapters**

Raise `ParseError` when the top-level shape or a job's `id`/title key is absent. Use `normalize_ats_description`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest backend/tests/test_board_adapters.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources backend/tests
git commit -m "Add Greenhouse, Lever and Ashby board adapters"
```

---

### Task 5: Boards runner

**Files:**
- Create: `backend/app/sources/runner.py`, `scripts/run-boards.py`
- Modify: `backend/app/config.py` (`board_delay` from `HEJ_BOARD_DELAY`), `.env.example`
- Test: `backend/tests/test_board_runner.py`

**Interfaces:**
- Consumes: Tasks 1 to 4.
- Produces: `class BoardsRunner(database, settings, client: BoardClient | None = None, adapters: dict | None = None)` with `async run(limit_per_ats: int | None = None) -> dict`, returning `database.latest_run("boards")`.
- Summary dict keys: `companies_total, companies_checked, companies_succeeded, companies_failed, companies_skipped, jobs_seen, jobs_kept, jobs_closed`.
- `scripts/run-boards.py --limit N` calls `BoardsRunner.run` directly for the real-run check. Don't add `limit` to the API, because `AGENTS.md` requires every API limit to have a frontend caller.

Behavior: refresh first if `companies_stale`. Run one asyncio task per ATS with `gather`. For each company, oldest first: call the adapter with `known_job_ids`, save drafts passing `keep_job`, then `reconcile_board` with `seen_ids` and `complete`, then `record_company_check`. Save `update_run_progress` after each company. Errors keep one entry per failed company, capped at 200 with a final `{"error": "N more errors not listed"}`.

- [ ] **Step 1: Write failing tests**

Use fake adapters and a real temp `Database`.

```python
async def test_only_kept_jobs_are_saved_but_all_count_as_seen(db): ...
async def test_500_keeps_jobs_active_and_records_failure(db):
    # BoardError: earlier job active=1, company last_error set, companies_failed==1, others proceed
async def test_429_stops_only_that_ats(db):
    # greenhouse raises BoardBlocked on company 1: company 2 never called, greenhouse counted skipped,
    # last_checked_at unchanged for skipped; lever still fully runs; error names host and retry_after
async def test_one_blocked_workday_tenant_does_not_stop_others(db): ...
async def test_three_blocked_workday_tenants_in_a_row_stop_workday(db): ...
async def test_success_resets_workday_block_streak(db): ...
async def test_404_counts_toward_disable(db): ...
async def test_parse_error_is_recorded_and_closes_nothing(db): ...
async def test_duplicate_url_recorded_not_fatal(db):
    # second draft with same source_url under another source -> IntegrityError caught, error recorded
async def test_job_missing_from_successful_fetch_closes_then_reopens(db): ...
async def test_refresh_runs_first_when_list_empty(db): ...
async def test_refresh_failure_does_not_stop_run_on_existing_list(db): ...
async def test_progress_visible_before_finish(db):  # completed_at None, summary updates mid-run
async def test_finish_run_called_even_if_unexpected_error(db): ...
async def test_errors_capped_at_200(db): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_board_runner.py -q`
Expected: FAIL on import.

- [ ] **Step 3: Implement `BoardsRunner`**

Stop per host when an ATS uses one host. Workday blocks skip the tenant and count toward the streak. Do not retry after a block.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest backend/tests/test_board_runner.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app .env.example backend/tests scripts/run-boards.py
git commit -m "Add boards runner with per-host block handling"
```

---

### Task 6: API

**Files:**
- Modify: `backend/app/main.py`, `backend/app/database.py`, `scripts/fit-report.py`
- Test: `backend/tests/test_board_api.py`

**Interfaces:**
- Produces: `POST /api/runs/boards`, `POST /api/boards/refresh`, `boards` entry in `GET /api/sources` with `run_path: "/api/runs/boards"`, and `GET /api/jobs` with comma-separated `source` and `closed` (`""` hides closed, `"include"` shows them).

Update the stale "Eight keyword searches" text only if touched. `exclusive("boards", ...)` for the run, `exclusive("discovery", ...)` for refresh.

- [ ] **Step 1: Write failing tests**

```python
def test_comma_source_returns_each_and_single_source_still_works(client): ...
def test_higheredjobs_view_excludes_board_jobs(client): ...  # for-you isolation
def test_closed_board_jobs_hidden_by_default_and_shown_with_include(client): ...
def test_closed_applied_job_stays_visible(client): ...  # review focus 4
def test_closed_filter_does_not_affect_existing_sources(client):
    # active=0 higheredjobs row behaves exactly as today
def test_undated_board_job_in_window_by_first_seen(client): ...  # review focus 3
def test_undated_higheredjobs_job_stays_hidden_in_window(client): ...  # unchanged behavior
def test_board_pages_reach_every_job(client):  # 61 greenhouse jobs, pages 1 and 2, all titles seen
def test_second_boards_run_returns_409(client): ...
def test_sources_lists_boards_with_summary(client): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_board_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `Database.jobs`: split `source` on commas into `IN (...)`. Add a `closed: str = ""` keyword parameter and a clause: board rows need `j.active=1 OR j.application_status='Applied'` unless `closed == "include"`. Extend the days clause at `database.py:340` with `OR (j.source IN (<boards>) AND j.posted_date IS NULL AND j.first_seen_at >= date('now', ?))`. Point `scripts/fit-report.py` at `",".join(FIT_SOURCES)`.

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app scripts/fit-report.py backend/tests
git commit -m "Expose board runs and multi-source job filters"
```

---

### Task 7: Workday adapter

**Files:**
- Create: `backend/app/sources/workday.py`, `backend/tests/fixtures/boards/workday_list.json`, `workday_detail.json`
- Modify: `backend/app/sources/runner.py` (register adapter)
- Test: `backend/tests/test_workday_adapter.py`

**Interfaces:**
- Consumes: `BoardFetch`, `title_candidate`, `WORKDAY_SEARCH_TERMS`, `BoardClient`.
- Produces: `workday.fetch_board(client, company, known_ids) -> BoardFetch`.

For each term, `POST https://{host}/wday/cxs/{slug}/{site}/jobs` with `{"appliedFacets": {}, "limit": 20, "offset": n, "searchText": term}`. Page until `offset >= total`, reading `total` from the first page only, because later pages may report 0. `source_job_id = f"{slug}/{site}:{externalPath}"`. Request detail at `https://{host}/wday/cxs/{slug}/{site}{externalPath}` only for titles passing `title_candidate` with an ID not in `known_ids`. Map `jobPostingInfo.jobDescription`, `startDate`, `externalUrl`, `location`, and `apply_url = externalUrl`. A failed list page sets `complete=False`. A failed detail keeps the job with `description_status="Failed"` and no description, without changing `complete`.

- [ ] **Step 1: Write failing tests**

```python
async def test_pages_all_terms_and_dedupes_paths(): ...
async def test_later_page_total_zero_does_not_stop_paging(): ...
async def test_details_only_for_title_candidates(): ...  # count detail requests
async def test_known_ids_skip_detail_but_count_as_seen(): ...
async def test_failed_list_page_is_incomplete(): ...
async def test_failed_detail_keeps_job_as_failed(): ...
async def test_same_path_in_two_tenants_gets_distinct_ids(): ...  # review focus 1
async def test_changed_format_raises_parse_error(): ...
async def test_runner_saves_failed_detail_with_failed_status_not_unavailable_wording(db):
    # Failed row saved when title_candidate and location_allowed pass, even though rule 3 can't be checked
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest backend/tests/test_workday_adapter.py -q`
Expected: FAIL on import.

- [ ] **Step 3: Implement the adapter, plus the runner rule for `Failed` drafts**

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "Add Workday board adapter"
```

---

### Task 8: Dashboard views

**Files:**
- Modify: `frontend/src/main.tsx`, `frontend/src/ForYouBoard.tsx`, `frontend/src/forYou.ts`, `frontend/src/types.ts`, `frontend/src/index.css`
- Test: `backend/tests/test_company_boards_dashboard.py`

**Interfaces:**
- Consumes: Task 6 API.
- Produces: `Board` gains `'companyRanked' | 'companyAll'`. `ForYouBoard` gains props `heading: string`, `notice: string`, `dayOptions: string[][]`. Export `boardSources` and `sourceLabel(source: string): string` from `types.ts`.

Follow the `vandan-ui-system` skill. Details:

- Tabs: For you, HigherEdJobs, AIR Career Center, Company boards. A second row in Company boards switches Ranked and All jobs.
- `parameters`: board views send `source=<filters.ats or all boardSources joined>` and never send `ats`.
- Ranked defaults: `{...forYouDefaults}` with `ats: ''`. All defaults: `days: '7'`, `sort: 'newest'`, `application_status: ''`, `closed: ''`, `ats: ''`, `hide: seniorityLabels.join(',')`. Date options include `['1', 'Past 24 hours']`, week, and all. All jobs adds ATS and Closed selects.
- Fix `main.tsx:249` with a map from source ID to run function, and `main.tsx:267` with `sourceLabel`.
- Hide `Non-college employer` in `main.tsx:270` when the job is from a board source.
- Add `runBoards`: posts to `/runs/boards` without awaiting and without setting `activeRun`. Show the run error if the POST fails.
- Poll at `main.tsx:119`: split `running` (any source, reload jobs) from `externalRun` (non-boards only, disables other buttons). Add a status line: `Boards run: {checked} of {total} companies, {kept} jobs kept, {failed} failed`, and after finish, also closed count. Keep the existing pager in both views. Update subtitle at `main.tsx:236`, which still says only HigherEdJobs and AIR. The For you tab's default query stays `source=higheredjobs`.

- [ ] **Step 1: Write failing browser tests**

Follow `test_dashboard_pagination.py` helpers, importing `serve_dashboard` and `browser_page`.

```python
async def test_all_jobs_reaches_job_past_first_page(...):  # 61 jobs, click Next, seen == 61
async def test_ranked_view_reaches_job_past_first_page(...):
async def test_for_you_tab_shows_no_board_jobs(...):
async def test_higheredjobs_tab_shows_no_board_jobs(...):
async def test_ats_filter_narrows_rows(...):  # greenhouse and lever seeded, select Lever, count matches
async def test_past_24_hours_filter(...):
async def test_badge_shows_ats_name_and_no_non_college_badge(...):
async def test_run_source_button_calls_boards_endpoint(...):  # route intercept records POST /api/runs/boards
async def test_long_boards_run_keeps_other_buttons_enabled_and_shows_progress(...):
    # review focus 5: seed open boards scrape_runs row with summary; "Run HigherEdJobs" enabled, status line shown
async def test_failed_description_reads_as_failed(...):
```

- [ ] **Step 2: Build and run to verify failure**

Run: `cd frontend && npm run build && cd .. && .venv/bin/pytest backend/tests/test_company_boards_dashboard.py -q`
Expected: FAIL on missing tab, not skipped.

- [ ] **Step 3: Implement**

- [ ] **Step 4: Build and run all tests**

Run: `cd frontend && npm run build && cd .. && .venv/bin/pytest -q`
Expected: all pass with no browser tests skipped.

- [ ] **Step 5: Commit**

```bash
git add frontend/src backend/tests/test_company_boards_dashboard.py
git commit -m "Add Company boards ranked and all-jobs views"
```

---

### Task 9: SmartRecruiters, if confirmed

**Files:**
- Create: `backend/app/sources/smartrecruiters.py`, `backend/tests/fixtures/boards/smartrecruiters_*.json`
- Modify: `backend/app/sources/runner.py`
- Test: `backend/tests/test_smartrecruiters_adapter.py`

**Interfaces:**
- Produces: `smartrecruiters.fetch_board(client, company, known_ids) -> BoardFetch`.

- [ ] **Step 1: Confirm the API**

Pick 3 slugs from SimplifyJobs `jobs.smartrecruiters.com` URLs. Run `curl -s "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=5"`, then fetch one posting by ID.
Expected: non-empty `content` and a description in the posting. If not confirmed, remove `smartrecruiters` from `BOARD_SOURCES` and discovery, tell the coordinator, and skip to committing that.

- [ ] **Step 2: Write failing tests**

Same behaviors as Workday: offset paging, details only for `title_candidate` jobs not in `known_ids`, failed list means incomplete, failed detail keeps the job as `Failed`, changed format raises `ParseError`.

- [ ] **Step 3: Run to verify failure, implement, run to verify pass**

Run: `.venv/bin/pytest backend/tests/test_smartrecruiters_adapter.py -q`
Expected: FAIL before implementing, all pass after.

- [ ] **Step 4: Commit**

```bash
git add backend/app backend/tests
git commit -m "Add SmartRecruiters board adapter"
```

---

### Task 10: Scripts, docs and real run

**Files:**
- Modify: `run.sh`, `AGENTS.md`, `README.md`, `HigherEdJobs_PRD.md` (one line pointing to the spec for the expanded scope)

- [ ] **Step 1: Add the boards step to `run.sh`**

In the subshell at `run.sh:64-71`, add `curl -s -X POST "$URL/api/runs/boards" >/dev/null &` as `BOARDS=$!` and include it in `wait`. Update the header comment and the `say` line. Say that boards can take hours, and that the dashboard stays usable. Ctrl+C keeps its existing cleanup.

- [ ] **Step 2: Update docs**

`AGENTS.md`:
- Replace "specification-only" with the real layout.
- Replace "Modify only the Keyword search field and the Category (`JobCat`) filter in V1" with: that rule applies to HigherEdJobs, and Company boards use public ATS job data.
- Add: back off on `403`, `429` or a challenge page, and never bypass it.
- Keep the remaining data rules.

`README.md`: Company boards section covering what it does, sources, run time, `HEJ_BOARD_DELAY`, `scripts/add-company.py`, `scripts/run-boards.py`, wipes keeping board jobs, and the limit that companies on no list are missed.

- [ ] **Step 3: Real run**

Run against a scratch copy of the database, not the user's: `cp data/jobs.sqlite3` to the scratchpad and set `HEJ_DATABASE` to a repo-relative path or build `Database` directly. Run `scripts/run-boards.py --limit 5`.
Expected: each ATS has `companies_succeeded > 0`, with kept jobs. Note any adapter failure and fix through a new failing test. A real response that disagrees with a fixture means updating the fixture.

- [ ] **Step 4: Use the dashboard like a user**

Serve the scratch database. In the browser: apply each filter, scroll to the end, confirm rows match the count, open a posting link, confirm the link resolves (especially built Greenhouse URLs), and confirm sponsorship evidence appears in the description. Take a screenshot for the PR.

- [ ] **Step 5: Final verification**

Run: `cd frontend && npm run build && cd .. && .venv/bin/pytest -q`
Expected: all pass, at least 370 plus the new tests, with no browser test skipped.

- [ ] **Step 6: Commit**

```bash
git add run.sh AGENTS.md README.md HigherEdJobs_PRD.md
git commit -m "Run Company boards from run.sh and document them"
```
