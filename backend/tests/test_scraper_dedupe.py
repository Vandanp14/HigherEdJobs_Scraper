import asyncio
from dataclasses import replace

from backend.app import scraper
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.parser import JobDraft

LISTING = "https://www.higheredjobs.com/details.cfm?JobCode=1"


class FakeLocator:
    async def fill(self, value): pass
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

    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=SLOW, title="Slow job"), JobDraft(higheredjobs_url=LISTING)])
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
    assert "↺ Data Analyst — already fetched; added to Software Development" in out


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
