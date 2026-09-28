# AIR Career Center integration plan

## Goal

Add the Association for Institutional Research (AIR) Career Center as a second
job source in the existing local review workspace:

<https://www.airweb.org/community/Career-Center/>

AIR is a curated listing page rather than a search portal. The first version
should fetch the table, follow each listing's detail link when needed, and
show the results in the same unified dashboard without creating keyword
searches or applying HigherEdJobs-specific assumptions.

## What the live page currently provides

The page inspected on September 28, 2026 is server-rendered and contains:

- one table with the `job-listing-table` class and a generated
  `jobListing-...` id;
- data rows with the `.job-item` class;
- columns for Job Title, Institution, Location, Salary Range, and Application
  Due Date;
- a title link in each row, currently using URLs such as
  `/community/Career-Center/21096`;
- no search form and no visible pagination on the current result set;
- a visible total of 20 jobs, while the supplied sample contains the first
  nine rows.

Selectors should be validated again with Playwright before production use.
Generated table ids must not be used as the sole selector because the id is not
stable.

## Proposed execution phases

### 1. Establish a portal-neutral job contract

Extend the persisted job model so a row can identify its source without
assuming HigherEdJobs:

- `source` or `portal` (`higheredjobs`, `air`);
- `source_job_id` and `source_url`;
- shared fields: title, institution, location, salary, posted date, and
  application due date;
- existing raw/normalized description, sponsorship analysis, application
  status, notes, and first/last-seen timestamps.

Keep `higheredjobs_id` and `higheredjobs_url` readable during migration, but
move uniqueness and deduplication to `(source, source_job_id)` or a canonical
source URL. This prevents an AIR listing from colliding with a HigherEdJobs
listing and preserves existing local data and application statuses.

### 2. Add an AIR parser with fixture coverage

Create a parser module isolated from browser navigation. It should:

1. locate the table by semantic class and verify the expected headers;
2. iterate only `.job-item` rows;
3. read values using the `data-th` labels/classes rather than column indexes;
4. normalize whitespace and retain empty salary values as `None` rather than
   inventing a value;
5. parse the application due date using the existing date normalization
   conventions, preserving the original value if it cannot be normalized;
6. canonicalize and validate the AIR detail URL;
7. raise a parse/access error when the expected table is absent, instead of
   returning an empty successful run.

Save a sanitized HTML fixture containing the supplied rows plus edge cases:
empty salary, an expired due date, a changed optional column, duplicate links,
and an explicit empty-result page. Add deterministic tests for row extraction,
date parsing, URL canonicalization, and markup-change failure behavior.

### 3. Add a read-only AIR scraper run

Implement a separate AIR scraper using the same Playwright context, timeout,
request-delay, access-check, and run-history patterns where they apply:

- navigate directly to the Career Center URL;
- parse the listing table;
- follow each detail link at a conservative rate;
- parse description and richer detail metadata if available;
- upsert each listing by AIR source identity;
- classify sponsorship wording only when a description was successfully
  captured;
- retain a pending/failed description state when the detail page fails;
- record one portal run with discovered, new, updated, and error counts.

The AIR run must not execute HigherEdJobs searches, modify a keyword field, or
mark a missing sponsorship phrase as sponsorship eligibility.

If the table later gains pagination or a load-more control, add explicit
pagination discovery. Do not silently assume the current 20-row page is the
complete dataset.

### 4. Expose source-aware API operations

Add source/run endpoints or a source parameter to the existing endpoints:

- list enabled sources and their run configuration;
- run AIR independently;
- optionally run all enabled sources;
- filter jobs by source;
- retain existing group filters for HigherEdJobs only;
- return source, salary, application due date, description status, and
  source-specific links in job rows.

Run errors should identify the source and, where applicable, the listing URL.
Existing HigherEdJobs API behavior should remain compatible.

### 5. Update the dashboard table

Keep one unified table, adding:

- a source badge or source column;
- AIR's Salary Range and Application Due Date columns;
- a source-aware listing link;
- a source/run control such as **Run AIR Career Center**;
- source filtering;
- a clear empty, stale, or failed-description state.

AIR does not need query-filter controls. Hide or disable HigherEdJobs search
group controls when the source filter is AIR, while preserving the current
HigherEdJobs workflow. Keep application status actions shared across portals.

### 6. Document operations and validate end to end

Update `README.md` with:

- AIR source configuration and run commands;
- the AIR codegen/discovery command;
- the meaning of source-specific failures and pending descriptions;
- fixture/test commands;
- data migration notes.

Validation should include parser tests, database migration tests, API tests,
frontend build, and one manually verified AIR run against the live page.

## Playwright discovery procedure

Use codegen only to inspect selectors and detail-page behavior; clean the
recording before committing it. A dedicated script is preferable to changing
the existing HigherEdJobs script:

```bash
.venv/bin/playwright codegen \
  --save-storage data/air-browser-state.json \
  --output scripts/air-recording.py \
  https://www.airweb.org/community/Career-Center/
```

During discovery, verify:

1. whether the listing table is complete in the initial HTML;
2. whether a cookie/consent or member gate changes the markup;
3. whether detail pages expose JSON-LD, description, salary, and due-date
   fields;
4. whether any next-page, load-more, or API request appears;
5. whether links remain stable after a refresh.

Do not commit browser storage, credentials, or raw pages containing private
information. Store only a sanitized fixture and stable selectors.

## Data and behavior decisions

- AIR application due date is distinct from HigherEdJobs posted date and must
  not be overloaded into the existing `posted_date` field.
- AIR salary text is displayed verbatim; parsing numeric ranges is optional and
  must not replace the original text.
- A missing AIR salary or sponsorship mention is unknown, not a negative
  classification.
- Re-running AIR updates listing metadata while preserving application status,
  notes, first-seen timestamp, and historical run records.
- Detail-page failure keeps the listing row and marks its description as
  pending/failed so it is distinguishable from a successfully parsed
  description with no sponsorship language.
- Source URLs and exact evidence remain available for manual verification.

## Acceptance criteria

- AIR can be run independently from the dashboard.
- The supplied sample fields render correctly in the unified table.
- At least the current 20 AIR rows are extracted without duplicate records.
- AIR rows are deduplicated independently of HigherEdJobs rows.
- Salary text, empty salary, and application due dates are preserved.
- A rerun does not reset AIR application status or notes.
- AIR detail failures are visible and do not become false
  `No Mention Found` results.
- HigherEdJobs searches and filters continue to work unchanged.
- Parser, migration, API, and frontend build checks pass.
