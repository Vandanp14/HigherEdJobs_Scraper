"""The For you tab in the built dashboard: ranked by fit, every job reachable, other tabs unchanged.

Run `npm run build` in frontend/ first, or these tests are skipped.
"""
import json
from datetime import date

import pytest

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft
from backend.tests.test_dashboard_pagination import browser_page, serve_dashboard

PER_PAGE = 50
RESUME = {"skills": [{"name": "All", "keywords": ["Python", "SQL"]}], "projects": [{"technologies": ["Python", "SQL"]}]}


def job(number: int, title: str, description: str | None = None) -> JobDraft:
    return JobDraft(
        source="higheredjobs",
        higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={400000 + number}",
        title=title,
        institution="Example University",
        posted_date=date.today().isoformat(),
        normalized_description=description,
        description_status="Complete" if description else "Pending",
    )


@pytest.fixture
def ranked_database(tmp_path):
    resume = tmp_path / "resume.json"
    resume.write_text(json.dumps(RESUME))
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3", resume)
    main.database.upsert(job(1, "Python SQL Developer", "Required Qualifications\nPython and SQL, Java, C, Go."))
    main.database.upsert(job(2, "Director of IT"))
    for number in range(3, PER_PAGE + 12):
        main.database.upsert(job(number, f"Software Engineer {number:02d}", "Required Qualifications\nJava, Ruby, PHP, Rust, Perl."))
    try:
        yield main.database
    finally:
        main.database = original


async def test_for_you_ranks_and_pages(ranked_database):
    total = PER_PAGE + 11
    with serve_dashboard() as url:
        async with browser_page() as page:
            await page.goto(url)
            await page.get_by_role("tab", name="For you", selected=True).wait_for()
            await page.get_by_text(f"{total} roles ranked").wait_for()
            first = page.locator(".fit-table tbody tr").first
            await first.locator(".role strong", has_text="Python SQL Developer").wait_for()

            seen = set(await page.locator(".fit-table tbody tr .role strong").all_inner_texts())
            await page.get_by_role("button", name="Next").click()
            await page.get_by_text("Page 2 of 2").wait_for()
            await page.wait_for_function(f"document.querySelectorAll('.fit-table tbody tr').length === {total - PER_PAGE}")
            seen |= set(await page.locator(".fit-table tbody tr .role strong").all_inner_texts())
            assert len(seen) == total and "Director of IT" in seen

            # The HigherEdJobs tab keeps hiding senior roles by default.
            await page.get_by_role("tab", name="HigherEdJobs").click()
            await page.get_by_text(f"{total - 1} roles in this view").wait_for()


async def test_for_you_explains_missing_resume(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3", tmp_path / "missing.json")
    main.database.upsert(job(1, "Software Engineer"))
    try:
        with serve_dashboard() as url:
            async with browser_page() as page:
                await page.goto(url)
                await page.get_by_text("Add your resume at data/resume.json to rank jobs.").wait_for()
    finally:
        main.database = original


async def test_for_you_panel_keyboard_and_collapse(ranked_database):
    with serve_dashboard() as url:
        async with browser_page() as page:
            await page.goto(url)
            panel = page.get_by_role("complementary", name="Fit details")
            await panel.get_by_role("heading", name="Python SQL Developer").wait_for()
            await panel.get_by_text("Python").first.wait_for()

            second = await page.locator(".fit-table tbody tr .role strong").nth(1).inner_text()
            await page.keyboard.press("j")
            await panel.get_by_role("heading", name=second).wait_for()
            await page.keyboard.press("k")
            await panel.get_by_role("heading", name="Python SQL Developer").wait_for()

            await page.keyboard.press("Escape")
            await panel.wait_for(state="hidden")
            await page.reload()
            await page.get_by_text("61 roles ranked").wait_for()
            assert not await panel.is_visible()

            await page.locator(".fit-table tbody tr").nth(1).click()
            await panel.get_by_role("heading", name=second).wait_for()


async def test_for_you_mark_applied_from_keyboard(ranked_database):
    with serve_dashboard() as url:
        async with browser_page() as page:
            await page.goto(url)
            panel = page.get_by_role("complementary", name="Fit details")
            await panel.get_by_role("heading", name="Python SQL Developer").wait_for()
            await page.keyboard.press("a")
            await panel.get_by_text("Applied", exact=True).wait_for()
    status = ranked_database.connection.execute("SELECT application_status FROM jobs WHERE title='Python SQL Developer'").fetchone()[0]
    assert status == "Applied"
