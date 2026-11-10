"""Company boards through the API: runs, sources and the job filters the new views use."""
import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft
from backend.app.sources.refs import BoardRef

BOARDS = "greenhouse,lever,ashby,workday,smartrecruiters"


@pytest.fixture
def db(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    main.database.upsert_company(BoardRef("greenhouse", "acme"), None, "manual")
    main.database.upsert_company(BoardRef("lever", "beta"), None, "manual")
    try:
        yield main.database
    finally:
        main.database = original


@pytest.fixture
def client(db):
    return TestClient(main.app)


def save(db, number, source="greenhouse", posted=None, title=None, active=True, status=None):
    company = next(c for c in db.companies() if c["ats"] == source)
    job_id, _ = db.save_board_job(company["id"], JobDraft(
        source=source, source_job_id=f"{company['slug']}:{number}", source_url=f"https://{source}.example/{number}",
        title=title or f"Software Engineer I {number:02d}", institution="Acme",
        posted_date=date.today().isoformat() if posted is None else (posted or None),
        normalized_description="Open to new grads.", description_status="Complete",
    ))
    if not active:
        db.connection.execute("UPDATE jobs SET active=0 WHERE id=?", (job_id,))
        db.connection.commit()
    if status:
        db.update_job(job_id, {"application_status": status})
    return job_id


def titles(client, query):
    return {item["title"] for item in client.get(f"/api/jobs?{query}").json()["items"]}


def test_comma_source_returns_each_and_single_source_still_works(db, client):
    save(db, 1, "greenhouse")
    save(db, 2, "lever")
    assert len(titles(client, f"source={BOARDS}&days=all")) == 2
    assert titles(client, "source=lever&days=all") == {"Software Engineer I 02"}


def test_higheredjobs_view_excludes_board_jobs(db, client):
    save(db, 1)
    db.upsert(JobDraft(higheredjobs_url="https://www.higheredjobs.com/details.cfm?JobCode=1", title="Web Developer",
                       posted_date=date.today().isoformat(), description_status="Pending"))
    assert titles(client, "source=higheredjobs&days=all") == {"Web Developer"}


def test_closed_board_jobs_hidden_by_default_and_shown_with_include(db, client):
    save(db, 1)
    save(db, 2, active=False)
    assert titles(client, f"source={BOARDS}&days=all") == {"Software Engineer I 01"}
    assert len(titles(client, f"source={BOARDS}&days=all&closed=include")) == 2


def test_closed_applied_job_stays_visible(db, client):
    # Review focus 4: a job the user applied to must not vanish when the company takes it down.
    save(db, 1, active=False, status="Applied")
    assert titles(client, f"source={BOARDS}&days=all") == {"Software Engineer I 01"}


def test_closed_filter_does_not_affect_existing_sources(db, client):
    db.upsert(JobDraft(higheredjobs_url="https://www.higheredjobs.com/details.cfm?JobCode=2", title="Web Developer",
                       posted_date=date.today().isoformat(), description_status="Pending"))
    db.connection.execute("UPDATE jobs SET active=0")
    db.connection.commit()
    assert titles(client, "source=higheredjobs&days=all") == {"Web Developer"}


def test_undated_board_job_in_window_by_first_seen(db, client):
    # Review focus 3: an ATS job with no posting date shows in date windows by when it was first seen.
    save(db, 1, posted="")
    save(db, 2, posted=(date.today() - timedelta(days=20)).isoformat())
    assert titles(client, f"source={BOARDS}&days=1") == {"Software Engineer I 01"}


def test_undated_higheredjobs_job_stays_hidden_in_window(db, client):
    db.upsert(JobDraft(higheredjobs_url="https://www.higheredjobs.com/details.cfm?JobCode=3", title="Web Developer",
                       description_status="Pending"))
    assert titles(client, "source=higheredjobs&days=7") == set()


def test_board_pages_reach_every_job(db, client):
    for number in range(1, 62):
        save(db, number)
    seen = []
    for page in (1, 2):
        data = client.get(f"/api/jobs?source={BOARDS}&days=all&page={page}").json()
        assert data["total"] == 61
        seen += [item["title"] for item in data["items"]]
    assert len(set(seen)) == 61


def test_second_boards_run_returns_409(db, client, monkeypatch):
    main.RUNNING.add("boards")
    try:
        assert client.post("/api/runs/boards").status_code == 409
    finally:
        main.RUNNING.discard("boards")


def test_boards_run_returns_its_summary(db, client, monkeypatch):
    class Fake:
        def __init__(self, database, settings):
            self.database = database

        async def run(self):
            run_id = self.database.start_run([], source="boards")
            self.database.finish_run(run_id, 3, 1, 0, [], summary={"companies_checked": 2})
            return self.database.latest_run("boards")

    monkeypatch.setattr(main, "BoardsRunner", Fake)
    body = client.post("/api/runs/boards").json()
    assert body["summary"] == {"companies_checked": 2}


def test_refresh_endpoint_reports_counts(db, client, monkeypatch):
    async def refresh(database, client):
        return {"found": 4, "new": 2, "errors": []}

    monkeypatch.setattr(main, "refresh_companies", refresh)
    assert client.post("/api/boards/refresh").json() == {"found": 4, "new": 2, "errors": []}


def test_sources_lists_boards_with_summary(db, client):
    run_id = db.start_run([], source="boards")
    db.update_run_progress(run_id, 5, 2, 0, {"companies_checked": 1, "companies_total": 2})
    boards = next(source for source in client.get("/api/sources").json() if source["id"] == "boards")
    assert boards["run_path"] == "/api/runs/boards"
    assert boards["last_run"]["summary"]["companies_total"] == 2
    assert boards["last_run"]["completed_at"] is None
