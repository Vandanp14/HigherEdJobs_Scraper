import asyncio
import sqlite3

from backend.app import scraper
from backend.app.config import SEARCH_GROUPS, Settings
from backend.app.database import Database
from backend.tests.test_scraper_dedupe import FakeContext, FakeLocator, FakePage


def by_id(db):
    return {group["id"]: group for group in db.groups()}


def test_category_groups_are_seeded_with_hej_job_categories(tmp_path):
    groups = by_id(Database(tmp_path / "jobs.sqlite3"))
    # Franklin & Marshall's "Digital Content Specialist" is filed under Web Developer (JobCat 160)
    # but its text never says "web developer", so only a category search finds it.
    assert groups["cat_web"]["categories"] == "160"
    assert groups["cat_web"]["query"] == ""
    assert groups["cat_web"]["enabled"] is True
    assert groups["web"]["categories"] == ""


def test_keyword_groups_include_near_match_variants():
    queries = {identifier: query for identifier, _, query, _ in SEARCH_GROUPS}
    for phrase in ('"web developer"', '"web development"', '"front-end developer"', '"website developer"'):
        assert phrase in queries["web"]
    for phrase in ('"software engineer"', '"software development"', '"applications developer"'):
        assert phrase in queries["software"]
    assert '"data analysis"' in queries["data"]


def test_config_changes_reach_saved_groups_and_keep_enabled_choice(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    db = Database(path)
    db.set_group_enabled("web", False)
    db.connection.execute("UPDATE search_groups SET query='\"web developer\"', name='Old' WHERE id='web'")
    db.connection.commit()
    web = by_id(Database(path))["web"]
    assert web["query"] == dict((g[0], g[2]) for g in SEARCH_GROUPS)["web"]
    assert web["name"] == "Web Development"
    assert web["enabled"] is False


def test_database_without_categories_column_is_migrated(tmp_path):
    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE search_groups (id TEXT PRIMARY KEY, name TEXT NOT NULL, query TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL)"
    )
    old.execute("INSERT INTO search_groups VALUES ('web','Web','\"web developer\"',1,2)")
    old.commit(); old.close()
    groups = by_id(Database(path))
    assert groups["web"]["categories"] == ""
    assert groups["cat_web"]["categories"] == "160"


class RecordingLocator(FakeLocator):
    def __init__(self, page): self.page = page
    async def select_option(self, values): self.page.selected = values
    async def fill(self, value): self.page.keyword = value


class RecordingPage(FakePage):
    selected = keyword = None
    def get_by_role(self, role, name=None): return RecordingLocator(self) if role == "textbox" else FakeLocator()
    def locator(self, selector):
        assert selector == "select[name=JobCat]"
        return RecordingLocator(self)


class RecordingContext(FakeContext):
    pages: list
    async def new_page(self):
        self.pages_opened += 1
        page = RecordingPage(self)
        self.pages = getattr(self, "pages", []) + [page]
        return page


def run_group(tmp_path, monkeypatch, group):
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [])
    job_scraper = scraper.HigherEdJobsScraper(Database(tmp_path / "jobs.sqlite3"), Settings(request_delay=0))
    async def no_check(page): pass
    job_scraper._ensure_access = no_check
    context = RecordingContext()
    asyncio.run(job_scraper._run_group(context, group, {}, []))
    return context


def test_category_group_selects_job_categories_with_empty_keyword(tmp_path, monkeypatch):
    context = run_group(tmp_path, monkeypatch, {"id": "cat_it", "name": "IT", "query": "", "categories": "160,159"})
    assert any(page.selected == ["160", "159"] and page.keyword == "" for page in context.pages)


def test_keyword_group_leaves_categories_unselected(tmp_path, monkeypatch):
    context = run_group(tmp_path, monkeypatch, {"id": "web", "name": "Web", "query": "q", "categories": ""})
    assert all(page.selected is None for page in context.pages)
