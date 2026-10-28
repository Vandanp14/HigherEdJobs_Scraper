"""Volume test: a view holding more jobs than one API page must still reach every job.

The API returns 50 jobs per page with the full total. The dashboard once showed the total but
never asked for page 2, so jobs past the 50th were unreachable. These tests seed more jobs than
one page and walk every page, through the API and through the built dashboard in a browser.
"""

import socket
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date

import pytest
import uvicorn
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft

PER_PAGE = 50
JOB_COUNT = PER_PAGE + 11


@pytest.fixture
def seeded_database(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    today = date.today().isoformat()
    for number in range(1, JOB_COUNT + 1):
        main.database.upsert(
            JobDraft(
                source="higheredjobs",
                higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={900000 + number}",
                title=f"Software Engineer {number:02d}",
                institution="Example University",
                posted_date=today,
                description_status="Pending",
            )
        )
    try:
        yield main.database
    finally:
        main.database = original


def test_jobs_api_pages_reach_every_job(seeded_database):
    client = TestClient(main.app)
    titles = []
    for page in (1, 2):
        data = client.get(f"/api/jobs?source=higheredjobs&days=7&page={page}").json()
        assert data["total"] == JOB_COUNT
        titles += [item["title"] for item in data["items"]]
    assert len(titles) == JOB_COUNT
    assert len(set(titles)) == JOB_COUNT


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def serve_dashboard():
    if not main.frontend.exists():
        pytest.skip("frontend/dist is missing; run `npm run build` in frontend/ first")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("dashboard server did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@asynccontextmanager
async def browser_page():
    playwright_api = pytest.importorskip("playwright.async_api")
    async with playwright_api.async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch()
        except Exception as error:
            pytest.skip(f"Chromium is not installed for Playwright: {error}")
        try:
            yield await browser.new_page()
        finally:
            await browser.close()


@pytest.fixture
def dashboard_url(seeded_database):
    with serve_dashboard() as url:
        yield url


async def test_dashboard_reaches_jobs_past_the_first_page(dashboard_url):
    async with browser_page() as page:
        await page.goto(dashboard_url)
        rows = page.locator("tbody tr:not(.detail) .role strong")
        await page.get_by_text(f"{JOB_COUNT} roles in this view").wait_for()
        await page.wait_for_function(f"document.querySelectorAll('tbody tr:not(.detail)').length === {PER_PAGE}")
        seen = set(await rows.all_inner_texts())

        await page.get_by_role("button", name="Next").click()
        await page.get_by_text("Page 2 of 2").wait_for()
        await page.wait_for_function(f"document.querySelectorAll('tbody tr:not(.detail)').length === {JOB_COUNT - PER_PAGE}")
        seen |= set(await rows.all_inner_texts())

        assert len(seen) == JOB_COUNT
        assert await page.get_by_role("button", name="Next").is_disabled()


async def test_dashboard_hides_flagged_roles_until_toggled(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "flagged.sqlite3")
    today = date.today().isoformat()
    for number, title in enumerate(["Software Engineer", "Director of IT"], start=1):
        main.database.upsert(
            JobDraft(
                source="higheredjobs",
                higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={700000 + number}",
                title=title,
                institution="Example University",
                posted_date=today,
                description_status="Pending",
            )
        )
    try:
        with serve_dashboard() as url:
            async with browser_page() as page:
                await page.goto(url)
                await page.get_by_text("1 roles in this view").wait_for()
                await page.get_by_role("button", name="Director", exact=True).click()
                await page.get_by_text("2 roles in this view").wait_for()
                await page.locator(".seniority-badge", has_text="Director").wait_for()
    finally:
        main.database = original
