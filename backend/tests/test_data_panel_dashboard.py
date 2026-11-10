"""Browser tests for the Data panel: per-board delete, clear all, and the fresh run guard.

Each test seeds a temp database, serves the built dashboard and drives it like a user.
Run `npm run build` in frontend/ first, or these tests are skipped.
"""

from datetime import date

import pytest

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft
from backend.tests.test_dashboard_pagination import PER_PAGE, browser_page, open_higheredjobs, serve_dashboard


def seed(database: Database, source: str, count: int, start: int = 1) -> list[int]:
    ids = []
    for number in range(start, start + count):
        job_id, _ = database.upsert_job(
            JobDraft(
                source=source,
                source_url=f"https://example.test/{source}/{number}",
                source_job_id=str(number),
                # HigherEdJobs listings only show with a computing title.
                title=f"Software Engineer {number:02d} ({source})",
                institution="Example University",
                posted_date=date.today().isoformat(),
                description_status="Pending",
            )
        )
        ids.append(job_id)
    return ids


@pytest.fixture
def database(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    try:
        yield main.database
    finally:
        main.database = original


async def open_data_panel(page, url: str):
    await open_higheredjobs(page, url)
    await page.get_by_role("button", name="Data", exact=True).click()
    panel = page.get_by_role("region", name="Data", exact=True)
    await panel.wait_for()
    return panel


async def test_data_panel_lists_sources_including_leftover_boards(database):
    seed(database, "higheredjobs", 2)
    seed(database, "greenhouse", 1)
    with serve_dashboard() as url:
        async with browser_page() as page:
            panel = await open_data_panel(page, url)
            await panel.get_by_text("HigherEdJobs", exact=True).wait_for()
            await panel.get_by_text("Greenhouse", exact=True).wait_for()
            await panel.get_by_text("2 jobs", exact=True).wait_for()
            await panel.get_by_text("1 job", exact=True).wait_for()


async def test_deleting_a_source_refreshes_counts_and_jobs(database):
    seed(database, "higheredjobs", 2)
    seed(database, "greenhouse", 1)
    with serve_dashboard() as url:
        async with browser_page() as page:
            panel = await open_data_panel(page, url)
            await panel.get_by_text("Greenhouse", exact=True).wait_for()

            await panel.get_by_role("button", name="Delete Greenhouse", exact=True).click()
            await panel.get_by_text("Delete 1 Greenhouse job").wait_for()
            await panel.get_by_role("button", name="Cancel", exact=True).click()
            await panel.get_by_text("Greenhouse", exact=True).wait_for()
            assert await panel.get_by_role("button", name="Confirm delete", exact=True).count() == 0

            await panel.get_by_role("button", name="Delete Greenhouse", exact=True).click()
            await panel.get_by_role("button", name="Confirm delete", exact=True).click()
            await page.get_by_role("status").filter(has_text="Deleted 1 Greenhouse job").wait_for()
            await panel.get_by_text("Greenhouse", exact=True).wait_for(state="detached")
            await panel.get_by_text("HigherEdJobs", exact=True).wait_for()
    assert database.source_counts() and [row["source"] for row in database.source_counts()] == ["higheredjobs"]


async def test_deleting_the_shown_board_from_page_two_empties_the_view(database):
    seed(database, "higheredjobs", PER_PAGE + 1)
    with serve_dashboard() as url:
        async with browser_page() as page:
            await open_higheredjobs(page, url)
            await page.get_by_role("button", name="Next").click()
            await page.get_by_text("Page 2 of 2").wait_for()
            await page.get_by_role("button", name="Data", exact=True).click()
            panel = page.get_by_role("region", name="Data", exact=True)
            await panel.get_by_role("button", name="Delete HigherEdJobs", exact=True).click()
            await panel.get_by_role("button", name="Confirm delete", exact=True).click()
            await page.get_by_text("0 roles in this view").wait_for()
            await panel.get_by_text("No saved data").wait_for()
            assert await page.get_by_text("Page 2 of").count() == 0


async def test_clear_all_shows_applied_and_notes_counts(database):
    applied_id, noted_id = seed(database, "higheredjobs", 2)
    seed(database, "greenhouse", 1)
    database.update_job(applied_id, {"application_status": "Applied"})
    database.update_job(noted_id, {"notes": "ask about visa"})
    with serve_dashboard() as url:
        async with browser_page() as page:
            panel = await open_data_panel(page, url)
            await panel.get_by_role("button", name="Clear all data", exact=True).click()
            confirm = panel.get_by_role("group", name="Confirm", exact=True)
            await confirm.get_by_text("1 Applied").wait_for()
            await confirm.get_by_text("1 with notes").wait_for()
            await panel.get_by_role("button", name="Confirm clear", exact=True).click()
            await panel.get_by_text("No saved data").wait_for()
            await page.get_by_text("0 roles in this view").wait_for()
    assert database.source_counts() == []


async def test_fresh_run_does_not_scrape_when_clear_is_refused(database, monkeypatch):
    seed(database, "higheredjobs", 2)
    calls = {"higheredjobs": 0, "air": 0}

    async def fake_higheredjobs(self, *args, **kwargs):
        calls["higheredjobs"] += 1
        return {}

    async def fake_air(self, *args, **kwargs):
        calls["air"] += 1
        return {}

    monkeypatch.setattr(main.HigherEdJobsScraper, "run", fake_higheredjobs)
    monkeypatch.setattr(main.AIRScraper, "run", fake_air)
    main.RUNNING.add("air")
    try:
        with serve_dashboard() as url:
            async with browser_page() as page:
                panel = await open_data_panel(page, url)
                await panel.get_by_role("button", name="Fresh run", exact=True).click()
                await panel.get_by_text("Then run AIR and HigherEdJobs.").wait_for()
                await panel.get_by_role("button", name="Confirm fresh run", exact=True).click()
                await page.get_by_role("status").filter(has_text="Stop running scrapes before clearing data").wait_for()
                await panel.get_by_text("2 jobs", exact=True).wait_for()
    finally:
        main.RUNNING.discard("air")
    assert calls == {"higheredjobs": 0, "air": 0}
    assert [row["jobs"] for row in database.source_counts()] == [2]


async def test_fresh_run_clears_then_runs_both_scrapers(database, monkeypatch):
    seed(database, "higheredjobs", 2)
    seen_when_run = {}

    def fake_run(source):
        async def run(self, *args, **kwargs):
            seen_when_run[source] = database.source_counts()
            return {"source": source, "jobs_discovered": 3, "new_jobs": 3, "updated_jobs": 0, "errors": []}
        return run

    monkeypatch.setattr(main.HigherEdJobsScraper, "run", fake_run("higheredjobs"))
    monkeypatch.setattr(main.AIRScraper, "run", fake_run("air"))
    with serve_dashboard() as url:
        async with browser_page() as page:
            panel = await open_data_panel(page, url)
            await panel.get_by_role("button", name="Fresh run", exact=True).click()
            await panel.get_by_role("button", name="Confirm fresh run", exact=True).click()
            await page.get_by_role("status").filter(has_text="Fresh run complete.").wait_for()
    assert seen_when_run == {"higheredjobs": [], "air": []}
