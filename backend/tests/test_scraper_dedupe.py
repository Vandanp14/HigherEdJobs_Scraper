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
    def __init__(self): self.detail_loads = 0
    async def new_page(self): return FakePage(self)


def test_listing_in_two_groups_is_fetched_once_and_matched_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=LISTING)])
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    database = Database(tmp_path / "jobs.sqlite3")
    settings = replace(Settings(), request_delay=0, headless=True)
    job_scraper = scraper.HigherEdJobsScraper(database, settings)
    context, fetched = FakeContext(), {}

    async def run_both():
        first = await job_scraper._run_group(context, {"id": "data", "query": "q"}, fetched)
        second = await job_scraper._run_group(context, {"id": "software", "query": "q"}, fetched)
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
