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
    queries = {group[0]: group[2] for group in SEARCH_GROUPS}
    for phrase in ('"web developer"', '"web development"', '"front-end developer"', '"website developer"'):
        assert phrase in queries["web"]
    for phrase in ('"software engineer"', '"software development"', '"applications developer"'):
        assert phrase in queries["software"]
    assert '"data analysis"' in queries["data"]


# Every HigherEdJobs category where a scan of the newest 100 listings found CS titles, plus the CS
# faculty categories (their non-teaching postdoc and research roles).
TRUSTED_IT = {"159", "160", "161", "162", "163", "173", "211"}
TITLE_CHECKED = set("30,31,34,24,37,175,179,217,218,102,116,144,182,259,290,42,14,219,212,17,213,18,22,23,214,25,276,206,279,148,27,29,32,150,220,43,149,28,216,164,207,4,54,49,256,110,113,114,115,117,118,120,124,287,81,204,88,97,90,91,222,137,210,154,99,103,104,106,107".split(","))


def test_all_cs_relevant_categories_are_searched(tmp_path):
    groups = Database(tmp_path / "jobs.sqlite3").groups()
    def ids(trusted): return {c for g in groups if g["categories"] and g["trusted"] is trusted for c in g["categories"].split(",")}
    assert ids(True) == TRUSTED_IT
    assert ids(False) == TITLE_CHECKED
    assert all(g["enabled"] for g in groups if g["categories"])


def test_keyword_groups_are_never_trusted(tmp_path):
    assert all(not g["trusted"] for g in Database(tmp_path / "jobs.sqlite3").groups() if not g["categories"])


def test_config_changes_reach_saved_groups_and_keep_enabled_choice(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    db = Database(path)
    db.set_group_enabled("web", False)
    db.connection.execute("UPDATE search_groups SET query='\"web developer\"', name='Old' WHERE id='web'")
    db.connection.commit()
    web = by_id(Database(path))["web"]
    assert web["query"] == {g[0]: g[2] for g in SEARCH_GROUPS}["web"]
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
    context = run_group(tmp_path, monkeypatch, {"id": "cat_it", "name": "IT", "query": "", "categories": "160,159", "trusted": True})
    assert any(page.selected == ["160", "159"] and page.keyword == "" for page in context.pages)


def test_keyword_group_leaves_categories_unselected(tmp_path, monkeypatch):
    context = run_group(tmp_path, monkeypatch, {"id": "web", "name": "Web", "query": "q", "categories": ""})
    assert all(page.selected is None for page in context.pages)


def test_search_asks_for_100_results_per_page(tmp_path, monkeypatch):
    context = run_group(tmp_path, monkeypatch, {"id": "web", "name": "Web", "query": "q", "categories": ""})
    assert any("NumJobs=100" in page.url for page in context.pages)


def test_more_than_30_categories_are_split_into_separate_searches(tmp_path, monkeypatch):
    # HigherEdJobs rejects a search with more than 30 categories selected.
    selections = []
    class Selecting(RecordingLocator):
        async def select_option(self, values): selections.append(values)
    class Page(RecordingPage):
        def locator(self, selector): return Selecting(self)
    class Context(RecordingContext):
        async def new_page(self):
            self.pages_opened += 1
            return Page(self)
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [])
    job_scraper = scraper.HigherEdJobsScraper(Database(tmp_path / "jobs.sqlite3"), Settings(request_delay=0))
    async def no_check(page): pass
    job_scraper._ensure_access = no_check
    categories = ",".join(str(n) for n in range(1, 34))
    asyncio.run(job_scraper._run_group(Context(), {"id": "cat_x", "name": "X", "query": "", "categories": categories}, {}, []))
    assert [len(values) for values in selections] == [30, 3]
    assert [c for values in selections for c in values] == categories.split(",")
