# Faster HigherEdJobs Paging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** HigherEdJobs searches sort by date and stop paging at the age cutoff, skipping the undated old tail.
**Architecture:** Change `HigherEdJobsScraper._search` (URL params) and the page loop in `_run_group` in `backend/app/scraper.py`. Tests use the existing fakes in `backend/tests/test_scraper_dedupe.py`.
**Tech Stack:** Python, Playwright (async), pytest.
**Spec:** `docs/superpowers/specs/2026-11-10-faster-hej-paging-design.md`

## Global Constraints
- Keep `request_delay` and existing verification handling unchanged.
- `max_age_days == 0` means no limit: no early stop, undated kept.
- Progress lines keep their existing style; the stop line names the page and the cutoff in days.

## Review Focus
1. Cutoff 0 must not stop early or drop undated listings. → test `test_no_age_limit_keeps_paging_and_undated`.
2. An undated listing before any old dated listing on the page is kept. → covered in `test_undated_after_old_listing_is_skipped_and_paging_stops`.
3. URL already containing `NumJobs=`/`SortBy=` is not duplicated. → test `test_search_url_requests_date_sort_and_100_per_page`.

---

### Task 1: Date-sorted search with early stop

**Files:** Modify `backend/app/scraper.py` (`_search` ~line 128-137, page loop in `_run_group` ~line 77-118). Test: `backend/tests/test_scraper_dedupe.py`.

- [ ] **Step 1: Write failing tests** in `backend/tests/test_scraper_dedupe.py`:
  - Rewrite `test_old_listings_are_skipped_and_paging_stops_once_a_page_is_all_old` → `test_undated_after_old_listing_is_skipped_and_paging_stops`: page 1 = `[undated_first, recent, old, undated_tail]`, page 2 = `[never]`, `max_age_days=14`. Assert saved URLs == `{undated_first, recent}`, `len(clicks) == 0`, output contains `"older than 14 days"`.
  - `test_no_age_limit_keeps_paging_and_undated`: `max_age_days=0`, pages `[[recent, old, undated], [older]]` with a Next link visible on page 1 only → all four saved, `len(clicks) == 1`.
  - `test_search_url_requests_date_sort_and_100_per_page`: drive `_search` with a fake page whose `url` after the search click is `https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x`; assert the final `goto` URL contains `NumJobs=100` and `SortBy=1` exactly once each. A URL already containing both triggers no extra `goto`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_scraper_dedupe.py -v` → new tests FAIL.
- [ ] **Step 3: Implement.** `_search`: add any missing of `NumJobs=100`, `SortBy=1` in one extra `goto` (skip the goto if both present). Page loop: walk listings in page order with `old_seen=False`; a dated listing older than cutoff sets `old_seen` and is skipped; an undated listing when `old_seen` is skipped and counted as old; after the page, if `cutoff and old_seen` report `"{name}: page {n} reached listings older than {days} days; stopping this search"` and break. Update the existing comment at the 100-per-page line.
- [ ] **Step 4: Run** `.venv/bin/pytest backend/tests -q` → PASS (currently 397).
- [ ] **Step 5: Update README** HigherEdJobs paragraph (line ~14): searches sort by date posted; paging stops at the first page with a listing older than the limit; undated listings after it are older postings and are skipped.
- [ ] **Step 6: Commit** `Sort HigherEdJobs searches by date and stop at the age limit`.
