# RSS discovery for HigherEdJobs category groups

> **Status (2026-10-28): shelved, not implemented.** Tasks 1-2 were built and passed tests, but a live
> check showed the feeds are not reachable from the scraper: Python `urllib` failed with
> `CERTIFICATE_VERIFY_FAILED` (python.org build without a CA bundle), and with certificates fixed both
> `urllib` and Playwright's `context.request` received the Incapsula bot page instead of RSS, while `curl`
> with a browser User-Agent still got the feed. Reading feeds through the browser would cost more page
> loads than search. Browser search stays the discovery path. Revisit only with HigherEdJobs' permission
> or an official data feed.

## Intent

Category-only search groups currently find listings by loading HigherEdJobs search result pages
in the Playwright browser. HigherEdJobs publishes an official RSS feed per category
(`/rss/categoryFeed.cfm?catID=<JobCat>`). Reading those feeds over plain HTTP removes the search
page loads for those groups, which makes runs faster and means fewer pages pass through the bot
check. Detail pages, and therefore descriptions and classification, are unchanged.

## Findings (2026-10-28)

- Feeds are RSS 2.0. Each `<item>` has `title`, `description` = `Institution (City, ST)`,
  `link`/`guid` = `https://www.higheredjobs.com/details.cfm?JobCode=N`, and `pubDate`
  (e.g. `Thu, 08 Oct 2026 10:32:31 EDT`). No job description.
- Feeds cover the last 30 days of postings in the category (catID 159: 139 items from
  2026-09-28 to 2026-10-27; its search showed 371 because search also lists older open jobs).
- Feeds stayed reachable over plain HTTP while search and detail pages returned the
  "Pardon Our Interruption" bot page.
- `HEJ_MAX_AGE_DAYS` defaults to 14, inside the 30-day feed window.

## Goals

- Category-only groups (empty `query`, non-empty `categories`) discover listings from RSS.
- Same results as today for those groups within the age cutoff: same title filters
  (`is_teaching_title`, `is_cs_title` for untrusted groups), same age cutoff, same cross-group
  matching via `add_match`, same "open each detail page at most once" rule.

## Non-goals

- Keyword groups: unchanged, still browser search.
- Detail fetching, parsing, classification, AIR, dashboard: unchanged.
- No new runtime dependency.

## Anti-goals

- Silently missing jobs. If RSS cannot cover a group, that group uses browser search.

## Approaches

- **A. RSS for category groups, browser search for keyword groups (chosen).** Smallest change;
  group labels and matching unchanged.
- B. RSS for all 237 categories and drop browser search. Removes search entirely, but keyword
  groups match description text RSS lacks, so group assignment would change. Rejected for now.
- Fetching feeds through Playwright. Costs a browser load per feed and loses the benefit. Rejected.

## Decided design

1. **Parser** (`backend/app/parser.py`): `parse_feed(xml: str, now: datetime) -> list[JobDraft]`.
   Maps each item to a `JobDraft` with `title`, `higheredjobs_url` = `canonical_url(link)`,
   `higheredjobs_id`, `posted_date` (`YYYY-MM-DD` from `pubDate`), and `institution`/`location`
   split from `Institution (City, ST)` (city/state filled when the pattern matches). A response
   that is not RSS (bot page, HTML, malformed XML) raises `ParseError`. Uses stdlib
   `xml.etree.ElementTree`.
2. **Fetch** (`backend/app/scraper.py`): plain HTTP GET with stdlib `urllib`, a browser
   User-Agent, `settings.timeout_ms`, and `settings.request_delay` between feeds. Run off the
   event loop (`asyncio.to_thread`). Injectable so tests use saved fixtures.
3. **Routing** in `_run_group`: a group uses RSS when `query` is empty, `categories` is non-empty,
   and `1 <= max_age_days <= 30`. Otherwise the current search path runs.
4. **Fallback:** if any feed of a group fails to fetch or parse, the group discards its RSS
   listings and runs the current browser search, and a note is reported. No partial coverage.
5. **Shared processing:** the per-listing body of `_run_group` (age cutoff, dedupe, title filters,
   `add_match` for saved jobs, detail fetch, failure recording) moves into one helper used by both
   the RSS and search paths, so behaviour cannot drift.
6. Listings from all of a group's feeds are combined and deduplicated by canonical URL before
   processing (a job can sit in several categories).

## Testing

- Saved RSS fixture under `backend/tests/fixtures/`; parser test for fields, date, split, and
  `ParseError` on the bot page.
- Scraper tests with a fake feed fetcher: category group uses RSS and never calls search;
  keyword group still searches; feed failure falls back to search; `max_age_days` of 0 or 31
  uses search; duplicates across feeds open one detail page; saved jobs get `add_match`.
- Existing suite stays green.

## Left to the builder

- Exact helper names and where the fetcher is injected.
- Report wording.
