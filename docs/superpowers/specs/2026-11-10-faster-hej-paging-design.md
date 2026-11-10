# Faster HigherEdJobs paging (short design)

Status: approved by user (option A), 2026-11-10.

## Intent
Daily HigherEdJobs runs load every results page and open old job pages. Make runs stop at the age cutoff.

## Evidence (live checks, 2026-11-10)
- Default results order is "Priority" (`SortBy=4`). On large searches (e.g. `data`, `cat_cs_related`) page 1 mixes dates from 2026-09-11 to 2026-11-10. `SortBy=1` (Date Posted) returns strict newest-first.
- Results only show "Posted ..." for recent jobs. Older listings come last with no date. Two checked detail pages were posted 2026-09-09 and 2026-08-17.
- The current "stop when the whole page is older than the cutoff" rule rarely fires: priority order mixes dates, and trailing undated listings keep a page from being "all old".
- 684 of 2686 saved jobs were already older than 14 days when first saved.

## Goals
1. Every search requests `SortBy=1` alongside the existing `NumJobs=100`.
2. With a cutoff set (`max_age_days > 0`): once a page contains a dated listing older than the cutoff, finish that page and stop paging this search/batch (later pages are older).
3. With a cutoff set: an undated listing that appears after an older-than-cutoff dated listing on the same page is treated as old and skipped (counted in the skipped-old total). Undated listings before any old dated listing are still kept.
4. `max_age_days == 0` (no limit) keeps today's behaviour: no early stop, undated kept.

## Non-goals
- Title-only search (`OnlyTitle`): not verified; left out.
- Blocking images/fonts/media: dropped; may raise bot-check rate.
- Request delay unchanged (2 s politeness).

## Also (data, not code)
- Disable the `it` search group in the user's DB (it repeats `software` and `systems` queries).
