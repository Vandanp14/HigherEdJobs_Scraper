# Company Boards: free early-career job discovery across ATS boards

## Context

The dashboard scrapes two fixed sources, HigherEdJobs and AIR. The user wants early-career software roles from any company, using 18 Google-style queries focused on Greenhouse, Lever, Ashby and Workday, and including titles such as "Software Engineer I", "Associate Software Engineer" and "Software Developer I" that generic new-grad searches miss.

The user cannot pay for search APIs and chose to skip Google entirely. Google's Custom Search API is closed to new customers and shuts down January 1, 2027. Automating Google results breaks its terms and gets blocked.

Instead, the queries become local rules. The scraper finds companies from free public data, reads each company's public job board, and applies the rules to what it gets back.

## Goals

- Find early-career software roles at companies the user has never heard of, at no cost.
- Run as a step in `./run.sh`, with no account, API key or CAPTCHA.
- Check every enabled company on every run, so a job posted today appears after the next run.
- Label kept jobs with the existing sponsorship, seniority and fit logic.
- Show them in dedicated views, separate from existing tabs.

## Non-goals

- Google, Bing or any paid search API.
- Merging the same role across HigherEdJobs and an ATS. Overlap should be low.
- Parsing arbitrary company career sites, including the 6,484 non-ATS SimplifyJobs links.
- A full source plugin system. HigherEdJobs and AIR keep their current scrapers.

## Anti-goals (failure even if it works)

- CAPTCHA solving, fingerprint spoofing, proxy rotation, or retrying through a block. On `403`, `429` or a challenge, back off and stop requests to that host for the run.
- Treating missing sponsorship language as eligibility.
- Treating a failed board fetch as "no jobs" or as closed jobs.
- Deleting history, or losing application status and notes on reruns.
- Changing what the existing For you tab shows.

## Approaches considered

| Approach | Trade-off | Outcome |
|---|---|---|
| Paid Google results API (Serper) or Brave API | Simple and close to the queries, but ongoing cost | Rejected: user can't pay |
| Google in a visible Chrome window, user solves CAPTCHAs | Exact queries, but breaks Google's terms, needs the user present, risks the account | Rejected by user |
| **Public company lists plus direct ATS data, rules applied locally** | Free and unattended with full job data, but misses companies on no list | **Chosen by user** |

## Probe results (2026-11-05, one company per ATS)

| Source | Result | Fields to use |
|---|---|---|
| Greenhouse `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | 200, 762 jobs | `id, title, content, first_published, updated_at, absolute_url, location.name, company_name` |
| Lever `api.lever.co/v0/postings/{slug}?mode=json` | 200, 86 jobs | `id, text, createdAt` (ms), `hostedUrl, applyUrl, categories.location, description, lists, additional` |
| Ashby `api.ashbyhq.com/posting-api/job-board/{slug}` | 200, 171 jobs | `id, title, publishedAt, jobUrl, applyUrl, location, descriptionHtml, isListed` |
| Workday `POST {tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | 200, unofficial endpoint | List: `title, externalPath, locationsText`, relative `postedOn`. Detail `GET .../{externalPath}`: `jobDescription, startDate, externalUrl, id` |
| SmartRecruiters `api.smartrecruiters.com/v1/companies/{slug}/postings` | 200, but empty for the slug tried | Not verified. Reported to need a second request per job for descriptions |
| Common Crawl CDX `index.commoncrawl.org/CC-MAIN-2026-43-index` | Greenhouse, Lever 200. Ashby, Workday `504` | `url, timestamp` |
| SimplifyJobs `New-Grad-Positions/dev/.github/scripts/listings.json` | 200, 19,063 listings | `url, company_name, active, date_posted`. By host: Workday 8,886, Greenhouse 1,656, Ashby 854, SmartRecruiters 618, Lever 565, other 6,484 |

The total number of companies is not measured yet. Build step 2 measures it and reports the expected run time. The user accepted runs that may take hours.

## Design

### Query rules (`backend/app/early_career.py`)

One editable rule set replaces the user's 18 queries, which are the source of truth for the rules and tests:

```text
site:job-boards.greenhouse.io ("software engineer" OR "software developer") ("new grad" OR "entry level" OR "junior")
site:jobs.lever.co "software engineer" ("new grad" OR "junior" OR "entry level")
site:jobs.ashbyhq.com "software engineer" ("new grad" OR "early career")
site:myworkdayjobs.com ("software engineer I" OR "associate software engineer")
site:jobs.smartrecruiters.com ("junior software engineer" OR "associate software engineer")
"software engineer" "new grad" "2027" (apply OR careers)
"software engineer I" ("0-2 years" OR "new grad") -senior -staff
"software engineer" ("2026 graduate" OR "2027 graduate" OR "new graduate")
"associate software engineer" "United States" apply
"backend engineer" ("junior" OR "new grad" OR "entry level")
"full stack developer" ("entry level" OR "0-2 years")
"software engineer" "bachelor's degree" "0 years" -internship
"software engineer" "H-1B sponsorship" ("entry level" OR "new grad")
"software engineer" ("OPT" OR "STEM OPT") ("new grad" OR "entry level")
"software engineer" "visa sponsorship available" careers
"software engineer" "international students" "2027" careers
"software engineer" "new grad" -senior -"no sponsorship" -"unable to sponsor"
("software engineer I" OR "associate software engineer" OR "new grad software engineer") ("2026" OR "2027") -senior -staff -principal
```

The user also named "Software Developer I" as a target title. A job is kept only if all of these pass:

1. **Software role:** title matches software engineer or developer, backend engineer, or full stack developer terms. Frontend, mobile, data, ML, SRE, DevOps and help desk titles are out unless the title says software engineer. Do not reuse `relevance.py` as is, because it accepts these.
2. **Not excluded:** title has no senior, staff, principal, lead, manager, or intern terms. Roman numerals II and above count as excluded.
3. **Early career, by either test:**
   - Title has new grad, junior, entry level, early career, associate, or "Engineer I" / "Developer I".
   - Or the description has "new grad", "new graduate", "2026 graduate", "2027 graduate", "0-2 years", or "0 years".
4. **Location (builder's default, flagged for user):** United States, remote, or unknown. Unknown is kept so parsing gaps don't lose jobs.
5. **Age:** not filtered at save time. Views filter by date, so past-24-hours and past-week are view filters.

Sponsorship terms from the queries (H-1B, OPT, STEM OPT, "unable to sponsor") never remove a job. The classifier labels them and the user filters on the labels.

### Company list (`ats_companies` table, `backend/app/sources/discovery.py`)

- Columns: `id, ats, slug, host, site, name, discovered_via, enabled, last_checked_at, last_success_at, consecutive_failures, last_error`. Unique on `(ats, slug, site)`. `host` and `site` are Workday-only.
- Wipes do not touch this table.
- Refresh runs before the fetch when the list is empty or over 7 days old. It parses board identifiers from Common Crawl URLs and SimplifyJobs URLs with one URL parser per ATS.
- Common Crawl gets retries with backoff for `504`. If it still fails, keep the existing list and report the failure.
- `scripts/add-company.py <board-url>` adds a company by hand using the same parser.
- After 5 consecutive `404`s a company is disabled. Other errors are recorded and retried.

### Board fetching (`backend/app/sources/{greenhouse,lever,ashby,workday,smartrecruiters}.py`, `sources/runner.py`)

- Each adapter has one job: board identifier in, `JobDraft` list out. Unrecognized response shapes raise `ParseError`, so a format change fails loudly.
- Add `httpx` as a runtime dependency. It's free, and it's already a dev dependency.
- Generic `User-Agent` with no personal contact details.
- `source` is the ATS name, such as `greenhouse`. `source_job_id` is the ATS job ID. `source_url` is the public posting URL.
- Rate limits are per ATS host: sequential, with a configurable delay defaulting to 1 second. Different ATSes can run concurrently. Workday counts as one ATS across tenants.
- Each run checks every enabled company, with no run cap, starting with the oldest `last_checked_at` so an interrupted run resumes fairly.
- `429`, `403`, or a challenge page stops that host for the run, honoring `Retry-After`, and marks its remaining companies as not checked. Greenhouse, Lever, Ashby and SmartRecruiters each use one host. Workday tenants have separate hosts, so one blocked tenant is skipped and the others continue. Three blocked Workday tenants in a row stop Workday for the run.
- **Workday:** use `searchText` for title terms, page through results, and request details only for titles that pass rules 1 and 2. This avoids a reported 2,000-job listing limit. `posted_date` comes from `startDate`.
- **SmartRecruiters:** build last, after confirming with a working company slug. If it can't be confirmed, ship without it and say so.

### Saving and labels

- Kept jobs go through `Database.upsert_job`, so they get sponsorship and seniority labels and keep `application_status` and notes on reruns.
- `raw_description` stores the ATS HTML. Add a normalizer for ATS HTML and route these sources to it in both the save path and `reanalyze` (`database.py:409,416`). Otherwise they fall through to `normalize_hej_description`.
- Fit scoring: replace the `source` checks at `database.py:440,460` and `scripts/fit-report.py:30` with a shared `FIT_SOURCES` constant, HigherEdJobs plus the ATS names. AIR stays out.
- **Closed jobs:** after a board fetch that fully succeeds, set `active=0` on saved jobs from that company missing from the response, and set it back to `1` if they return. Partial or failed fetches never change `active`. Rows are never deleted. This needs a company link on jobs: add `ats_company_id` to `jobs`. Workday's closure check must use search results for the same terms, and only applies to jobs that match those terms.
- Schema changes follow the existing `migrate()` pattern in `database.py`.

### API

- `POST /api/runs/boards` runs the fetch under `exclusive("boards", ...)`. `scrape_runs.source` is `boards`.
- `POST /api/boards/refresh` refreshes the company list.
- Add a `boards` entry to `GET /api/sources`.
- `GET /api/jobs` `source` accepts a comma-separated list, like `sponsorship` already does. Add an `ats` filter value through the same param, and hide inactive jobs by default for these sources.
- Run summaries include companies checked, succeeded, failed and skipped, and jobs seen, kept and closed, so a fetch failure stays visible.

### Dashboard: dedicated views

New top-level **Company boards** area, separate from HigherEdJobs, AIR and For you. The existing For you stays HigherEdJobs-only (`main.tsx:63`).

- **Ranked view:** fit-ordered, reusing `ForYouBoard` with a source parameter instead of a second copy. Builder's call: includes fit ranking, because scoring already exists.
- **All jobs view:** table with sponsorship, evidence, progress and links, plus filters for ATS, date (24 hours, week, all), sponsorship and application status.
- Pager or "load more" so every job in the total is reachable.
- Fix traps: `main.tsx:249` (non-AIR "Run source" runs HigherEdJobs) and `main.tsx:267` (non-AIR badged "HigherEdJobs"). Handle null `search_groups` and show the ATS name as the badge.
- Show last run summary, including failed companies. Follow the `vandan-ui-system` skill.
- "Non-college employer" badge (`classifier.py:123-124`) is noise on these rows, so hide it in these views.

### Scheduling and repo rules

- `run.sh` gains a `POST /api/runs/boards` step, sent in the background so a long run doesn't hold up the dashboard or the other sources. There is no launchd or other system schedule.
- `clear_jobs` (used by `./clear.sh` and `./daily.sh`) keeps Company boards jobs, their labels and their statuses and notes. It deletes only rows from other sources, plus their related labels, matches and run records. Update its tests and `README.md`.
- Update `AGENTS.md`: replace the V1 HigherEdJobs-only scope with these sources, and fix the stale "specification-only" text. Keep the rules on access restrictions and data integrity. Update `README.md`.

## Build order

1. Save the spec to `docs/superpowers/specs/2026-11-05-company-boards-design.md`, then run `superpowers:writing-plans`.
2. Company list, URL parsers and discovery. Report the real company counts.
3. Rule set with tests built from the 18 queries.
4. Greenhouse, Lever and Ashby adapters, runner, normalizer, schema.
5. Fit gate and API.
6. Dashboard views.
7. Workday.
8. SmartRecruiters, if confirmed.
9. `run.sh`, `AGENTS.md`, `README.md`.

Use subagents per the global instructions and TDD throughout (`superpowers:test-driven-development`, `ecc:python-testing`). Review with `ecc:python-review`, `ecc:fastapi-review` and `ecc:react-review`.

## Verification

Run `.venv/bin/pytest`, plus `npm run build` in `frontend/` first so browser tests aren't skipped.

- **Adapters:** saved JSON fixtures per ATS, including an empty board and a changed format that must fail loudly. Follow `backend/tests/test_air.py`.
- **Rules:** one case per query type, including "Software Engineer I" kept, "Software Engineer II" dropped, and interns dropped.
- **Wipes:** `clear_jobs` removes HigherEdJobs and AIR rows, and keeps Company boards jobs, statuses and notes.
- **Failure handling:** a `500` board keeps its jobs active and is recorded as failed. A `429` stops only that host. A missing job on a successful fetch becomes inactive, and comes back if it reappears.
- **Status preservation:** application status and notes survive a rerun.
- **Isolation:** the existing For you tab shows no ATS jobs, and `SEARCH_GROUPS` runs are unchanged.
- **Pagination:** seed 51+ jobs and assert the last one is reachable in the new view, like `backend/tests/test_dashboard_pagination.py`.
- **Real run:** run against 5 real companies per ATS. Then use the dashboard like a user: apply filters, scroll to the end, confirm rows match the count, open a posting link, and check sponsorship evidence appears in the description.

## Calls made by the builder, for user review

- US, remote or unknown locations only.
- Ranked view included in Company boards, using resume fit.
- No HigherEdJobs-to-ATS duplicate merging.
- Company list refreshes when empty or over 7 days old. 1-second delay per ATS.
- SmartRecruiters is last and can be dropped.
- Software role rule covers only titles in the user's queries. Frontend, mobile, data and similar titles are out unless the title says software engineer.
- A block stops one host. Three blocked Workday tenants in a row stop Workday for that run.
- `run.sh` sends the boards run in the background.
