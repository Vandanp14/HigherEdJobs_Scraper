# RSS Discovery Implementation Plan

> **Status (2026-10-28): shelved, not implemented.** Tasks 1-2 were built and passed tests, but a live
> check showed the feeds are not reachable from the scraper: Python `urllib` failed with
> `CERTIFICATE_VERIFY_FAILED` (python.org build without a CA bundle), and with certificates fixed both
> `urllib` and Playwright's `context.request` received the Incapsula bot page instead of RSS, while `curl`
> with a browser User-Agent still got the feed. Reading feeds through the browser would cost more page
> loads than search. Browser search stays the discovery path. Revisit only with HigherEdJobs' permission
> or an official data feed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Category-only HigherEdJobs search groups discover listings from the per-category RSS feeds over plain HTTP instead of browser search pages.

**Architecture:** A stdlib RSS parser in `parser.py` turns a feed into `JobDraft` listings. `HigherEdJobsScraper._run_group` routes category-only groups to an RSS path (fetch every feed, combine, dedupe) and keeps browser search for keyword groups and as a whole-group fallback. Both paths feed one shared per-listing helper, so filters, matching and detail fetching stay identical.

**Tech Stack:** Python 3.11, stdlib `urllib.request`, `xml.etree.ElementTree`, `email.utils`; Playwright (unchanged); pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-rss-discovery-design.md`

## Global Constraints

- No new runtime dependency (`pyproject.toml` `dependencies` unchanged).
- Feed URL: `https://www.higheredjobs.com/rss/categoryFeed.cfm?catID=<JobCat>`.
- RSS path only when `query` is empty, `categories` non-empty, and `1 <= settings.max_age_days <= 30`.
- Any feed fetch or parse failure in a group: discard that group's RSS listings, run the current browser search, report a note.
- Keyword groups, detail parsing, classifier, AIR, dashboard: unchanged.
- Python style: four-space indent, `snake_case`; match the compact style of `scraper.py`.

## Review Focus

- A category with no postings in 30 days returns a valid feed with zero items: that is success (zero listings), not a failure that triggers fallback.
- The bot page ("Pardon Our Interruption") arrives with HTTP 200: must raise `ParseError` and trigger fallback, not parse as an empty feed.
- An item with no `pubDate` is kept with `posted_date=None` (undated listings are kept, per `scraper.py:80`).
- An item whose `description` has no `(City, ST)` part: `institution` = whole string, `location`/`city`/`state` = `None`.
- Titles with entities (`&amp;`) come out unescaped (`R&D Programmer`).

Each is pinned by a test in Task 1 or Task 3.

---

### Task 1: `parse_feed`

**Files:**
- Create: `backend/tests/fixtures/hej_feed.xml`
- Modify: `backend/app/parser.py` (add `FEED` constant near `ADVANCED`, add `parse_feed`)
- Test: `backend/tests/test_rss_feed.py`

**Interfaces:**
- Produces: `FEED: str = f"{BASE}/rss/categoryFeed.cfm?catID={{}}"` (use with `.format(cat_id)`); `parse_feed(xml: str, now: datetime) -> list[JobDraft]`, raising `ParseError` on non-RSS input.

- [ ] **Step 1: Write the fixture** `backend/tests/fixtures/hej_feed.xml`: an RSS 2.0 channel in the live format (see spec Findings) with four items:
  1. title `Senior Software Engineer`, description `Hamdan Bin Mohammed Smart University (Dubai, AE)`, link `https://www.higheredjobs.com/details.cfm?JobCode=179590001`, pubDate `Thu, 22 Oct 2026 14:36:02 EDT`
  2. title `R&amp;D Programmer`, description `Marshall University (Huntington, WV)`, link `https://www.higheredjobs.com/details.cfm?JobCode=179590002`, pubDate `Mon, 02 Nov 2026 23:30:00 EST`
  3. title `Web Developer`, description `Online University`, link `https://www.higheredjobs.com/details.cfm?JobCode=179590003`, no pubDate
  4. duplicate of item 1 (same link)

- [ ] **Step 2: Write the failing tests** in `backend/tests/test_rss_feed.py`:

```python
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)

def test_feed_items_become_listings():
    jobs = parse_feed((FIXTURES / "hej_feed.xml").read_text(), NOW)
    assert [j.higheredjobs_id for j in jobs] == ["179590001", "179590002", "179590003"]
    first = jobs[0]
    assert first.title == "Senior Software Engineer"
    assert first.higheredjobs_url == "https://www.higheredjobs.com/search/details.cfm?JobCode=179590001"
    assert first.posted_date == "2026-10-22"
    assert (first.institution, first.location, first.city, first.state) == (
        "Hamdan Bin Mohammed Smart University", "Dubai, AE", "Dubai", "AE")

def test_feed_unescapes_titles_and_keeps_feed_local_date():
    second = parse_feed((FIXTURES / "hej_feed.xml").read_text(), NOW)[1]
    assert second.title == "R&D Programmer"
    assert second.posted_date == "2026-11-02"  # date as published, not shifted to UTC

def test_feed_item_without_location_or_date():
    third = parse_feed((FIXTURES / "hej_feed.xml").read_text(), NOW)[2]
    assert (third.institution, third.location, third.city, third.state, third.posted_date) == (
        "Online University", None, None, None, None)

def test_empty_feed_is_valid():
    xml = '<?xml version="1.0"?><rss version="2.0"><channel><title>HigherEdJobs - X</title></channel></rss>'
    assert parse_feed(xml, NOW) == []

@pytest.mark.parametrize("body", [
    "<html><head><title>Pardon Our Interruption</title></head><body>bot</body></html>",
    "<rss><channel><item>",  # truncated
    "",
])
def test_non_rss_raises(body):
    with pytest.raises(ParseError):
        parse_feed(body, NOW)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_rss_feed.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_feed'`

- [ ] **Step 4: Implement `parse_feed(xml: str, now: datetime) -> list[JobDraft]`** in `backend/app/parser.py`. `ElementTree.fromstring`; `ParseError` if XML is malformed or root tag is not `rss`. Per `channel/item`: URL from `link` (fall back to `guid`) through `canonical_url`, id from `job_id`; skip items without a job id and duplicate URLs (first wins). Date: `email.utils.parsedate_to_datetime(pubDate).date().isoformat()`, `None` if missing or unparseable. Location split with `re.fullmatch(r"(.+?)\s*\(([^()]+)\)", description)`; city/state from splitting the parenthesised part on the last comma. `now` is unused today but kept for parity with `parse_results`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_rss_feed.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/parser.py backend/tests/test_rss_feed.py backend/tests/fixtures/hej_feed.xml
git commit -m "Parse HigherEdJobs category RSS feeds into listings"
```

---

### Task 2: Extract the per-listing helper

Pure refactor: no behaviour change.

**Files:**
- Modify: `backend/app/scraper.py:65-122` (`_run_group`)

**Interfaces:**
- Produces: `async def _process_listing(self, detail, group: dict, listing: JobDraft, now: datetime, fetched: dict[str, int], seen: set[str], errors: list[dict], counts: dict[str, int]) -> None` on `HigherEdJobsScraper`. It holds the current body of the `for listing in listings:` loop from the `seen` check through the `finally: await asyncio.sleep(...)` (lines 85-111). `counts` keys: `discovered`, `new`, `updated`, `failed`, `off_field`. Age-cutoff filtering stays in the caller (the search path needs `too_old` for its stop rule).

- [ ] **Step 1: Run the existing scraper tests as the baseline**

Run: `pytest backend/tests/test_scraper_dedupe.py backend/tests/test_search_groups.py -v`
Expected: all pass

- [ ] **Step 2: Move the loop body into `_process_listing`** and call it from the search loop; `_run_group` keeps its return value `(discovered, new, updated)` and its report lines.

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: same pass count as before the change, 0 failures

- [ ] **Step 4: Commit**

```bash
git add backend/app/scraper.py
git commit -m "Extract per-listing processing from HigherEdJobs group search"
```

---

### Task 3: RSS routing, fetch, and fallback

**Files:**
- Modify: `backend/app/scraper.py`
- Test: `backend/tests/test_rss_discovery.py`

**Interfaces:**
- Consumes: `FEED`, `parse_feed` (Task 1); `_process_listing` (Task 2).
- Produces:
  - module function `fetch_feed(url: str, timeout_s: float) -> str` — `urllib.request` GET with a desktop Chrome `User-Agent`, returns the decoded body; raises on non-200.
  - `HigherEdJobsScraper._fetch_feed: Callable[[str], Awaitable[str]]`, set in `__init__` to `lambda url: asyncio.to_thread(fetch_feed, url, settings.timeout_ms / 1000)`. Tests replace this attribute.
  - `HigherEdJobsScraper._uses_feeds(group: dict) -> bool` — the Global Constraints routing rule.
  - `async def _feed_listings(self, group: dict, now: datetime) -> list[JobDraft]` — fetches each category feed in order with `settings.request_delay` between fetches, parses, returns combined listings deduped by `higheredjobs_url`; any exception propagates.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_rss_discovery.py`. Reuse `FakeContext`/`FakePage` from `test_scraper_dedupe.py` (import them). Build the scraper with `replace(Settings(), request_delay=0, headless=True, max_age_days=14)`; monkeypatch `scraper.parse_job` to return `JobDraft(higheredjobs_url=url, normalized_description="Text")`; record searches by monkeypatching `job_scraper._search` with an async fake that appends to a list. Feed fake: `async def feeds(url)` returning per-catID XML built from one `<item>` per given JobCode (CS title `Software Engineer`, pubDate today), or raising.

```python
def test_category_group_reads_feeds_not_search(...):
    # group {"id":"cat_web","name":"Web","query":"","categories":"160,159","trusted":1}
    # feeds: 160 -> JobCodes [1, 2]; 159 -> [2, 3]
    assert searches == []
    assert fetched_urls == [FEED.format("160"), FEED.format("159")]
    assert context.detail_loads == 3          # job 2 opened once
    assert result == (3, 3, 0)

def test_keyword_group_still_searches(...):
    # group {"id":"data","query":"q","categories":""}
    assert fetched_urls == [] and len(searches) == 1

def test_feed_failure_falls_back_to_search(...):
    # 160 ok, 159 raises OSError
    assert len(searches) == 1                 # whole group searched
    assert context.detail_loads == 0          # RSS listings discarded, search fake returns none

def test_bot_page_falls_back_to_search(...):
    # 160 returns "<html><title>Pardon Our Interruption</title></html>"
    assert len(searches) == 1

@pytest.mark.parametrize("days", [0, 31])
def test_age_limit_outside_feed_window_uses_search(days, ...):
    assert fetched_urls == [] and len(searches) == 1

def test_empty_feed_is_not_a_failure(...):
    # 160 returns a channel with no items
    assert searches == [] and result == (0, 0, 0)

def test_feed_listing_already_saved_gets_match_only(...):
    # pre-seed fetched = {canonical url of job 1: <id from database.upsert_job>}
    assert context.detail_loads == 0
    # job_search_matches has (id, "cat_web")

def test_old_and_off_field_feed_items_are_skipped(...):
    # untrusted group; items: pubDate 20 days ago "Software Engineer"; today "History Instructor"; today "Lecturer in Computer Science"
    assert context.detail_loads == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_rss_discovery.py -v`
Expected: FAIL (`fetch_feed`/`FEED` usage missing; searches recorded for category groups)

- [ ] **Step 3: Implement `fetch_feed`, `_fetch_feed`, `_uses_feeds`, `_feed_listings`**, then route in `_run_group`: when `_uses_feeds(group)`, try `_feed_listings`; on success report `"{name}: {n} listings from {k} RSS feeds"`, drop items older than the cutoff (same rule as the search path, undated kept), call `_process_listing` for each, skip `_search` and paging. On exception report `"{name}: RSS failed ({first line of error}); using search"` and run the existing search loop unchanged. The final `"{name} done: ..."` report and return value stay as today.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_rss_discovery.py -v`
Expected: 9 passed

- [ ] **Step 5: Run the full suite and lint**

Run: `pytest -q && ruff check backend`
Expected: 0 failures; `All checks passed!`

- [ ] **Step 6: Live smoke check (one feed, no browser)**

Run: `python -c "from datetime import datetime,timezone; from backend.app.scraper import fetch_feed; from backend.app.parser import FEED, parse_feed; print(len(parse_feed(fetch_feed(FEED.format(160), 30), datetime.now(timezone.utc))))"`
Expected: a positive integer (about 30-50)

- [ ] **Step 7: Commit**

```bash
git add backend/app/scraper.py backend/tests/test_rss_discovery.py
git commit -m "Discover HigherEdJobs category groups from RSS feeds"
```
