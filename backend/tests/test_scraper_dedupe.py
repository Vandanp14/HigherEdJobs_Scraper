import asyncio
from dataclasses import replace

from backend.app import scraper
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.parser import JobDraft

LISTING = "https://www.higheredjobs.com/details.cfm?JobCode=1"


class FakeLocator:
    async def fill(self, value): pass
    async def select_option(self, values): pass
    async def click(self): pass
    async def count(self): return 0
    async def is_visible(self): return False


class FakePage:
    def __init__(self, context): self.context, self.url = context, ""
    def set_default_timeout(self, value): pass
    async def goto(self, url, wait_until=None):
        self.url = url
        if url == LISTING: self.context.detail_loads += 1
    async def content(self): return "<p>Job</p>"
    def get_by_role(self, role, name=None): return FakeLocator()
    def locator(self, selector): return FakeLocator()
    async def wait_for_load_state(self, state=None): pass
    async def close(self): pass


class FakeContext:
    def __init__(self): self.detail_loads = self.pages_opened = 0
    async def new_page(self):
        self.pages_opened += 1
        return FakePage(self)


def test_listing_in_two_groups_is_fetched_once_and_matched_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=LISTING)])
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    database = Database(tmp_path / "jobs.sqlite3")
    settings = replace(Settings(), request_delay=0, headless=True)
    job_scraper = scraper.HigherEdJobsScraper(database, settings)
    context, fetched = FakeContext(), {}

    async def run_both():
        first = await job_scraper._run_group(context, {"id": "data", "name": "Data", "query": "q"}, fetched, [])
        second = await job_scraper._run_group(context, {"id": "software", "name": "Software", "query": "q"}, fetched, [])
        return first, second

    first, second = asyncio.run(run_both())
    groups = [row[0] for row in database.connection.execute("SELECT search_group_id FROM job_search_matches ORDER BY 1")]
    assert context.detail_loads == 1
    assert groups == ["data", "software"]
    assert first == (1, 1, 0)
    assert second == (1, 0, 0)


def test_verification_timeout_fails_fast_for_rest_of_run(tmp_path, monkeypatch):
    waits = []

    async def never_solved(page, **options):
        waits.append(page)
        raise scraper.AccessBlocked("blocked")

    monkeypatch.setattr(scraper, "wait_for_access", never_solved)
    settings = replace(Settings(), headless=False)
    job_scraper = scraper.HigherEdJobsScraper(Database(tmp_path / "jobs.sqlite3"), settings)

    async def ensure_twice():
        for _ in range(2):
            try:
                await job_scraper._ensure_access(FakePage(FakeContext()))
            except scraper.AccessBlocked:
                pass

    asyncio.run(ensure_twice())
    assert len(waits) == 1


SLOW = "https://www.higheredjobs.com/details.cfm?JobCode=2"


def test_detail_page_timeout_is_recorded_and_group_continues(tmp_path, monkeypatch):
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=SLOW, title="Slow Software Developer"), JobDraft(higheredjobs_url=LISTING)])
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    original_goto = FakePage.goto

    async def goto(self, url, wait_until=None):
        if url == SLOW:
            raise PlaywrightTimeout("Timeout 30000ms exceeded.")
        await original_goto(self, url, wait_until)

    monkeypatch.setattr(FakePage, "goto", goto)
    database = Database(tmp_path / "jobs.sqlite3")
    job_scraper = scraper.HigherEdJobsScraper(database, replace(Settings(), request_delay=0, headless=True))
    errors = []
    counts = asyncio.run(job_scraper._run_group(FakeContext(), {"id": "data", "name": "Data", "query": "q"}, {}, errors))
    statuses = dict(database.connection.execute("SELECT higheredjobs_url, description_status FROM jobs").fetchall())
    assert counts == (2, 1, 1)
    assert statuses == {SLOW: "Failed", LISTING: "Complete"}
    assert errors == [{"group": "Data", "listing_url": SLOW, "error": "Timeout 30000ms exceeded."}]


def test_progress_messages_show_group_and_job_outcomes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=LISTING, title="Data Analyst", institution="State U")])
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    database = Database(tmp_path / "jobs.sqlite3")
    job_scraper = scraper.HigherEdJobsScraper(database, replace(Settings(), request_delay=0, headless=True))
    fetched = {}

    async def run_both():
        await job_scraper._run_group(FakeContext(), {"id": "data", "name": "Data & Analytics", "query": "q"}, fetched, [])
        await job_scraper._run_group(FakeContext(), {"id": "software", "name": "Software Development", "query": "q"}, fetched, [])

    asyncio.run(run_both())
    out = capsys.readouterr().out
    assert "[HigherEdJobs] Data & Analytics: searching" in out
    assert "[HigherEdJobs] Data & Analytics page 1: 1 listings" in out
    assert "✓ Data Analyst — State U" in out
    assert "↺ Data Analyst — already saved; added to Software Development" in out


class FakeBrowser:
    def __init__(self, context): self.context = context
    async def new_context(self, **options): return self.context
    async def close(self): pass


class FakePlaywright:
    def __init__(self, context):
        browser = FakeBrowser(context)
        self.chromium = type("Chromium", (), {"launch": staticmethod(lambda **options: _value(browser))})()
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


async def _value(value): return value


def test_air_progress_messages_count_listings(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(FakeContext, "close", lambda self: _value(None), raising=False)
    listings = [JobDraft(source="air", source_url=f"https://www.airweb.org/community/Career-Center/{n}", title=f"Analyst {n}", institution="AIR U") for n in (1, 2)]
    monkeypatch.setattr(scraper, "async_playwright", lambda: FakePlaywright(FakeContext()))
    monkeypatch.setattr(scraper, "parse_air_results", lambda html, url, now: listings)
    monkeypatch.setattr(scraper, "parse_air_job", lambda html, url, now: JobDraft(source="air", source_url=url, normalized_description="Text"))
    database = Database(tmp_path / "jobs.sqlite3")
    asyncio.run(scraper.AIRScraper(database, replace(Settings(), request_delay=0, headless=True)).run())
    out = capsys.readouterr().out
    assert "[AIR] Loading AIR Career Center board" in out
    assert "[AIR] Found 2 listings" in out
    assert "(2/2) ✓ Analyst 2 — AIR U" in out
    assert "[AIR] Finished in" in out


def test_run_reuses_two_tabs_instead_of_opening_one_per_job(tmp_path, monkeypatch):
    # Every new tab activates the browser and pulls the user to its desktop.
    listings = [JobDraft(higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={n}") for n in range(3)]
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: listings)
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    job_scraper = scraper.HigherEdJobsScraper(Database(tmp_path / "jobs.sqlite3"), replace(Settings(), request_delay=0, headless=True))
    context = FakeContext()

    async def two_groups():
        await job_scraper._run_group(context, {"id": "data", "name": "Data", "query": "q"}, {}, [])
        await job_scraper._run_group(context, {"id": "web", "name": "Web", "query": "q"}, {}, [])

    asyncio.run(two_groups())
    assert context.pages_opened == 2


def test_air_reuses_one_detail_tab(tmp_path, monkeypatch):
    monkeypatch.setattr(FakeContext, "close", lambda self: _value(None), raising=False)
    context = FakeContext()
    listings = [JobDraft(source="air", source_url=f"https://www.airweb.org/community/Career-Center/{n}") for n in range(3)]
    monkeypatch.setattr(scraper, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(scraper, "parse_air_results", lambda html, url, now: listings)
    monkeypatch.setattr(scraper, "parse_air_job", lambda html, url, now: JobDraft(source="air", source_url=url, normalized_description="Text"))
    asyncio.run(scraper.AIRScraper(Database(tmp_path / "jobs.sqlite3"), replace(Settings(), request_delay=0, headless=True)).run())
    assert context.pages_opened == 2


def test_air_runs_headless_so_it_opens_no_window(tmp_path, monkeypatch):
    # AIR has no human verification, so a visible window would only steal focus.
    launches = []
    monkeypatch.setattr(FakeContext, "close", lambda self: _value(None), raising=False)
    playwright = FakePlaywright(FakeContext())
    browser = FakeBrowser(FakeContext())
    playwright.chromium = type("Chromium", (), {"launch": staticmethod(lambda **options: launches.append(options) or _value(browser))})()
    monkeypatch.setattr(scraper, "async_playwright", lambda: playwright)
    monkeypatch.setattr(scraper, "parse_air_results", lambda html, url, now: [])
    asyncio.run(scraper.AIRScraper(Database(tmp_path / "jobs.sqlite3"), replace(Settings(), headless=False)).run())
    assert launches[0]["headless"] is True


def test_rerun_skips_job_pages_already_saved(tmp_path, monkeypatch):
    database = Database(tmp_path / "jobs.sqlite3")
    saved, _ = database.upsert_job(JobDraft(higheredjobs_url=LISTING, normalized_description="Text"), "data")
    monkeypatch.setattr(FakeContext, "close", lambda self: _value(None), raising=False)
    context = FakeContext()
    monkeypatch.setattr(scraper, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=LISTING)])
    database.set_group_enabled("data", True)
    for group in database.groups():
        if group["id"] not in ("data", "web"): database.set_group_enabled(group["id"], False)
    asyncio.run(scraper.HigherEdJobsScraper(database, replace(Settings(), request_delay=0, headless=True)).run())
    groups = [row[0] for row in database.connection.execute("SELECT search_group_id FROM job_search_matches WHERE job_id=? ORDER BY 1", (saved,))]
    assert context.detail_loads == 0
    assert groups == ["data", "web"]


def test_air_rerun_skips_listings_already_saved(tmp_path, monkeypatch, capsys):
    database = Database(tmp_path / "jobs.sqlite3")
    url = "https://www.airweb.org/community/Career-Center/1"
    database.upsert_job(JobDraft(source="air", source_url=url, normalized_description="Text"))
    database.update_job(1, {"application_status": "Applied"})
    monkeypatch.setattr(FakeContext, "close", lambda self: _value(None), raising=False)
    loads = []
    original_goto = FakePage.goto

    async def goto(self, target, wait_until=None):
        loads.append(target)
        await original_goto(self, target, wait_until)

    monkeypatch.setattr(FakePage, "goto", goto)
    monkeypatch.setattr(scraper, "async_playwright", lambda: FakePlaywright(FakeContext()))
    monkeypatch.setattr(scraper, "parse_air_results", lambda html, url_, now: [JobDraft(source="air", source_url=url, title="Analyst")])
    asyncio.run(scraper.AIRScraper(database, replace(Settings(), request_delay=0, headless=True)).run())
    status = database.connection.execute("SELECT description_status, application_status FROM jobs").fetchone()
    assert url not in loads
    assert tuple(status) == ("Complete", "Applied")
    assert "(1/1) ↺ Analyst — already saved" in capsys.readouterr().out


class NextLink(FakeLocator):
    def __init__(self, clicks, visible=True): self.clicks, self.visible = clicks, visible
    async def count(self): return int(self.visible)
    async def is_visible(self): return self.visible
    async def click(self): self.clicks.append(1)


def _run_paged(tmp_path, monkeypatch, pages, max_age_days, next_on_pages=None):
    pages = list(pages); clicks = []
    shown = []

    def parse(html, url, now):
        shown.append(1); return pages.pop(0)

    monkeypatch.setattr(scraper, "parse_results", parse)
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    visible_pages = next_on_pages if next_on_pages is not None else {1, 2, 3}
    monkeypatch.setattr(FakePage, "get_by_role", lambda self, role, name=None: NextLink(clicks, len(shown) in visible_pages) if name == "Next page" else FakeLocator())
    database = Database(tmp_path / "jobs.sqlite3")
    job_scraper = scraper.HigherEdJobsScraper(database, replace(Settings(), request_delay=0, headless=True, max_age_days=max_age_days))
    asyncio.run(job_scraper._run_group(FakeContext(), {"id": "data", "name": "Data", "query": "q"}, {}, []))
    saved = {row[0] for row in database.connection.execute("SELECT higheredjobs_url FROM jobs")}
    return saved, clicks


def test_undated_after_old_listing_is_skipped_and_paging_stops(tmp_path, monkeypatch, capsys):
    from datetime import date, timedelta

    today = date.today()
    undated_first = JobDraft(higheredjobs_url="https://h/undated-first")
    recent = JobDraft(higheredjobs_url="https://h/recent", posted_date=(today - timedelta(days=3)).isoformat())
    old = JobDraft(higheredjobs_url="https://h/old", posted_date=(today - timedelta(days=20)).isoformat())
    undated_tail = JobDraft(higheredjobs_url="https://h/undated-tail")
    never = JobDraft(higheredjobs_url="https://h/never", posted_date=today.isoformat())
    saved, clicks = _run_paged(tmp_path, monkeypatch, [[undated_first, recent, old, undated_tail], [never]], 14)
    assert saved == {"https://h/undated-first", "https://h/recent"}
    assert len(clicks) == 0
    assert "older than 14 days" in capsys.readouterr().out


def test_no_age_limit_keeps_paging_and_undated(tmp_path, monkeypatch):
    from datetime import date, timedelta

    today = date.today()
    recent = JobDraft(higheredjobs_url="https://h/recent", posted_date=(today - timedelta(days=3)).isoformat())
    old = JobDraft(higheredjobs_url="https://h/old", posted_date=(today - timedelta(days=200)).isoformat())
    undated = JobDraft(higheredjobs_url="https://h/undated")
    older = JobDraft(higheredjobs_url="https://h/older", posted_date=(today - timedelta(days=300)).isoformat())
    saved, clicks = _run_paged(tmp_path, monkeypatch, [[recent, old, undated], [older]], 0, next_on_pages={1})
    assert saved == {"https://h/recent", "https://h/old", "https://h/undated", "https://h/older"}
    assert len(clicks) == 1


def _search_gotos(tmp_path, final_url):
    gotos = []

    class SearchPage(FakePage):
        async def goto(self, url, wait_until=None):
            gotos.append(url); self.url = url

        def get_by_role(self, role, name=None):
            page = self

            class Click(FakeLocator):
                async def click(self): page.url = final_url

            return Click()

    job_scraper = scraper.HigherEdJobsScraper(Database(tmp_path / "jobs.sqlite3"), replace(Settings(), request_delay=0, headless=True))
    asyncio.run(job_scraper._search(SearchPage(FakeContext()), "x", []))
    return gotos


def test_search_url_requests_date_sort_and_100_per_page(tmp_path):
    gotos = _search_gotos(tmp_path, "https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x")
    assert len(gotos) == 2
    assert gotos[-1].count("NumJobs=100") == 1 and gotos[-1].count("SortBy=1") == 1


def test_search_url_with_both_params_is_not_reloaded(tmp_path):
    gotos = _search_gotos(tmp_path, "https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x&NumJobs=100&SortBy=1")
    assert len(gotos) == 1


def test_search_url_adds_only_missing_param(tmp_path):
    gotos = _search_gotos(tmp_path, "https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x&NumJobs=100")
    assert gotos[-1].count("NumJobs=") == 1 and gotos[-1].count("SortBy=1") == 1


def test_search_url_replaces_wrong_sort_and_page_size(tmp_path):
    gotos = _search_gotos(tmp_path, "https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x&SortBy=4&NumJobs=25")
    query = gotos[-1].split("?", 1)[1].split("&")
    assert query.count("SortBy=1") == 1 and query.count("NumJobs=100") == 1
    assert not any(part in ("SortBy=4", "NumJobs=25") for part in query)


def test_search_url_with_sortby_10_is_not_treated_as_date_sorted(tmp_path):
    gotos = _search_gotos(tmp_path, "https://www.higheredjobs.com/search/advanced_action.cfm?NumJobs=100&SortBy=10")
    assert len(gotos) == 2
    assert gotos[-1].split("?", 1)[1].split("&").count("SortBy=1") == 1 and "SortBy=10" not in gotos[-1]


def test_date_sorted_url_preserves_repeated_params():
    fixed = scraper._date_sorted_url("https://h/s.cfm?PosType=1&PosType=2&Keyword=&SortBy=4")
    query = fixed.split("?", 1)[1].split("&")
    assert query.count("PosType=1") == 1 and query.count("PosType=2") == 1 and "Keyword=" in query
    assert query.count("SortBy=1") == 1 and query.count("NumJobs=100") == 1
    assert scraper._date_sorted_url(fixed) == fixed


def test_next_page_landing_without_sort_is_redirected_before_parsing(tmp_path, monkeypatch):
    events = []
    sorted_url = "https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x&NumJobs=100&SortBy=1"

    class Next(FakeLocator):
        def __init__(self, page): self.page = page
        async def count(self): return int("page2" not in events)
        async def is_visible(self): return "page2" not in events
        async def click(self):
            events.append("page2"); self.page.url = "https://www.higheredjobs.com/search/advanced_action.cfm?Keyword=x&NumJobs=100&StartRow=101"

    class Page(FakePage):
        async def goto(self, url, wait_until=None):
            events.append(("goto", url)); self.url = url
        def get_by_role(self, role, name=None):
            return Next(self) if name == "Next page" else (_Click(self))

    class _Click(FakeLocator):
        def __init__(self, page): self.page = page
        async def click(self): self.page.url = sorted_url

    class Context(FakeContext):
        async def new_page(self): return Page(self)

    def parse(html, url, now):
        events.append(("parse", url)); return []

    monkeypatch.setattr(scraper, "parse_results", parse)
    job_scraper = scraper.HigherEdJobsScraper(Database(tmp_path / "jobs.sqlite3"), replace(Settings(), request_delay=0, headless=True, max_age_days=14))
    asyncio.run(job_scraper._run_group(Context(), {"id": "data", "name": "Data", "query": "q"}, {}, []))
    after_click = events[events.index("page2") + 1:]
    assert after_click[0][0] == "goto" and "SortBy=1" in after_click[0][1] and "StartRow=101" in after_click[0][1]
    assert after_click[1][0] == "parse" and "SortBy=1" in after_click[1][1]


def test_run_result_is_for_its_own_source(tmp_path, monkeypatch):
    # A fresh run runs both scrapers at once; the other source's newer run must not be returned.
    monkeypatch.setattr(FakeContext, "close", lambda self: _value(None), raising=False)
    database = Database(tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(scraper, "async_playwright", lambda: FakePlaywright(FakeContext()))

    def parse_and_start_other_run(html, url, now):
        database.start_run([], source="higheredjobs")
        return []

    monkeypatch.setattr(scraper, "parse_air_results", parse_and_start_other_run)
    result = asyncio.run(scraper.AIRScraper(database, replace(Settings(), request_delay=0, headless=True)).run())
    assert result["source"] == "air"
