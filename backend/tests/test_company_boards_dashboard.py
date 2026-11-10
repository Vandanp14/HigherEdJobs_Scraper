"""Company boards views in the built dashboard, driven in a real browser.

Run `npm run build` in frontend/ first, or these tests are skipped.
"""
from contextlib import contextmanager
from datetime import date, timedelta

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft
from backend.app.sources.refs import BoardRef
from backend.tests.test_dashboard_pagination import browser_page, serve_dashboard

PER_PAGE = 50


@contextmanager
def seeded(tmp_path, count=0, sources=("greenhouse",)):
    original = main.database
    main.database = db = Database(tmp_path / "boards.sqlite3")
    for ats in ("greenhouse", "lever"):
        db.upsert_company(BoardRef(ats, f"{ats}-co"), f"{ats.title()} Co", "manual")
    for number in range(1, count + 1):
        save(db, number, sources[number % len(sources)])
    try:
        yield db
    finally:
        main.database = original


def save(db, number, source="greenhouse", posted=None, failed=False, title=None):
    company = next(c for c in db.companies() if c["ats"] == source)
    description = None if failed else "Open to new grads. Python and SQL."
    job_id, _ = db.save_board_job(company["id"], JobDraft(
        source=source, source_job_id=f"{company['slug']}:{number}", source_url=f"https://{source}.example/{number}",
        title=title or f"Software Engineer I {number:02d}", institution=company["name"], location="Remote",
        posted_date=(posted or date.today()).isoformat(), raw_description=description,
        normalized_description=description, description_status="Failed" if failed else "Complete",
    ))
    return job_id


def save_hej(db, title="Web Developer"):
    db.upsert(JobDraft(higheredjobs_url="https://www.higheredjobs.com/details.cfm?JobCode=1", title=title,
                       institution="Example University", posted_date=date.today().isoformat(), description_status="Pending"))


async def open_view(page, url, view="All jobs"):
    await page.goto(url)
    await page.get_by_role("tab", name="Company boards").click()
    await page.get_by_role("tab", name=view, exact=True).click()


ROWS = "tbody tr:not(.detail) .role strong"


def select(page, label):
    # By the visible label only: option text such as "Newest posted" would also match a label search.
    return page.locator(f'.filters label:has(> span:text-is("{label}")) select')


async def walk_two_pages(page, count, text):
    await page.get_by_text(text).wait_for()
    await page.wait_for_function(f"document.querySelectorAll('tbody tr:not(.detail)').length === {PER_PAGE}")
    seen = set(await page.locator(ROWS).all_inner_texts())
    await page.get_by_role("button", name="Next").click()
    await page.get_by_text("Page 2 of 2").wait_for()
    await page.wait_for_function(f"document.querySelectorAll('tbody tr:not(.detail)').length === {count - PER_PAGE}")
    return seen | set(await page.locator(ROWS).all_inner_texts())


async def test_all_jobs_reaches_job_past_first_page(tmp_path):
    with seeded(tmp_path, 61), serve_dashboard() as url:
        async with browser_page() as page:
            await open_view(page, url)
            assert len(await walk_two_pages(page, 61, "61 roles in this view")) == 61


async def test_ranked_view_reaches_job_past_first_page(tmp_path):
    with seeded(tmp_path, 61), serve_dashboard() as url:
        async with browser_page() as page:
            await open_view(page, url, "Ranked")
            assert len(await walk_two_pages(page, 61, "61 roles ranked")) == 61


async def test_for_you_tab_shows_no_board_jobs(tmp_path):
    with seeded(tmp_path, 2) as db, serve_dashboard() as url:
        save_hej(db)
        async with browser_page() as page:
            await page.goto(url)
            await page.get_by_text("1 roles ranked").wait_for()
            assert await page.locator(ROWS).all_inner_texts() == ["Web Developer"]


async def test_higheredjobs_tab_shows_no_board_jobs(tmp_path):
    with seeded(tmp_path, 2) as db, serve_dashboard() as url:
        save_hej(db)
        async with browser_page() as page:
            await page.goto(url)
            await page.get_by_role("tab", name="HigherEdJobs").click()
            await page.get_by_text("1 roles in this view").wait_for()


async def test_ats_filter_narrows_rows(tmp_path):
    with seeded(tmp_path, 4, sources=("greenhouse", "lever")), serve_dashboard() as url:
        async with browser_page() as page:
            await open_view(page, url)
            await page.get_by_text("4 roles in this view").wait_for()
            await select(page, "ATS").select_option("lever")
            await page.get_by_text("2 roles in this view").wait_for()
            assert set(await page.locator(".source-badge").all_inner_texts()) == {"Lever"}


async def test_past_24_hours_filter(tmp_path):
    with seeded(tmp_path) as db, serve_dashboard() as url:
        save(db, 1)
        save(db, 2, posted=date.today() - timedelta(days=5))
        async with browser_page() as page:
            await open_view(page, url)
            await page.get_by_text("2 roles in this view").wait_for()
            await select(page, "Posted").select_option("1")
            await page.get_by_text("1 roles in this view").wait_for()


async def test_badge_shows_ats_name_and_no_non_college_badge(tmp_path):
    with seeded(tmp_path, 1), serve_dashboard() as url:
        async with browser_page() as page:
            await open_view(page, url)
            await page.locator(".source-badge", has_text="Greenhouse").wait_for()
            assert await page.get_by_text("Non-college employer").count() == 0


async def test_run_source_button_calls_boards_endpoint(tmp_path):
    with seeded(tmp_path), serve_dashboard() as url:
        async with browser_page() as page:
            posted = []

            async def fake_run(route):
                posted.append(route.request.method)
                await route.fulfill(json={"source": "boards", "completed_at": "x", "jobs_discovered": 0, "new_jobs": 0, "updated_jobs": 0, "errors": [], "summary": {}})

            await page.route("**/api/runs/boards", fake_run)
            await page.goto(url)
            await page.get_by_role("button", name="Search sources").click()
            card = page.locator(".source-info", has_text="Company boards")
            await card.get_by_role("button", name="Run source").click()
            await page.get_by_text("Company boards run started").wait_for()
            assert posted == ["POST"]


async def test_long_boards_run_keeps_other_buttons_enabled_and_shows_progress(tmp_path):
    # Review focus 5: an hours-long boards run must not lock the HigherEdJobs and AIR runs.
    with seeded(tmp_path) as db, serve_dashboard() as url:
        run_id = db.start_run([], source="boards")
        db.update_run_progress(run_id, 10, 3, 0, {"companies_total": 2, "companies_checked": 1, "companies_failed": 0,
                                                 "jobs_kept": 3, "jobs_closed": 0})
        async with browser_page() as page:
            await page.goto(url)
            await page.get_by_text("Boards run: 1 of 2 companies, 3 jobs kept, 0 failed").wait_for()
            assert await page.get_by_role("button", name="Run HigherEdJobs").is_enabled()
            assert await page.get_by_role("button", name="Run AIR Career Center").is_enabled()


async def test_failed_description_reads_as_failed(tmp_path):
    with seeded(tmp_path) as db, serve_dashboard() as url:
        save(db, 1, failed=True, title="Software Engineer")
        async with browser_page() as page:
            await open_view(page, url)
            await page.get_by_role("button", name="Description failed").wait_for()
