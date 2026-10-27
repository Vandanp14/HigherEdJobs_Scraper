import sqlite3

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft


def test_jobs_api_exposes_source_fields_and_filters_air_jobs(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    try:
        main.database.upsert(
            JobDraft(
                source="air",
                source_job_id="21096",
                source_url="https://www.airweb.org/community/Career-Center/21096",
                title="Data Governance Manager",
                institution="University of Idaho",
                salary="$85000 - $85000",
                application_due_date="2026-11-23",
                description_status="Pending",
            )
        )
        response = TestClient(main.app).get("/api/jobs?source=air&days=all")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["source"] == "air"
        assert item["salary"] == "$85000 - $85000"
        assert item["application_due_date"] == "2026-11-23"
        assert item["source_url"].endswith("/21096")
        assert item["description_status"] == "Pending"

        sources = TestClient(main.app).get("/api/sources")
        assert {source["id"] for source in sources.json()} == {"higheredjobs", "air"}
    finally:
        main.database = original


def test_legacy_database_gets_source_columns_without_losing_identity(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE jobs (
          id INTEGER PRIMARY KEY, higheredjobs_id TEXT UNIQUE, title TEXT, institution TEXT,
          location TEXT, city TEXT, state TEXT, salary TEXT, posted_date TEXT,
          first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
          higheredjobs_url TEXT UNIQUE NOT NULL, apply_url TEXT, raw_description TEXT,
          normalized_description TEXT, description_status TEXT NOT NULL DEFAULT 'Pending',
          active INTEGER NOT NULL DEFAULT 1, application_status TEXT NOT NULL DEFAULT 'New',
          notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO jobs(higheredjobs_id,title,first_seen_at,last_seen_at,higheredjobs_url,created_at,updated_at) "
        "VALUES ('123','Legacy Software Developer','2026-09-01','2026-09-01',"
        "'https://www.higheredjobs.com/search/details.cfm?JobCode=123','2026-09-01','2026-09-01')"
    )
    connection.commit()
    connection.close()

    database = Database(path)
    item = database.jobs(days="all")["items"][0]
    assert item["source"] == "higheredjobs"
    assert item["source_job_id"] == "123"
    assert item["source_url"].endswith("JobCode=123")


def test_second_run_for_same_source_is_rejected(tmp_path):
    main.RUNNING.add("higheredjobs")
    try:
        response = TestClient(main.app).post("/api/runs", json={})
        assert response.status_code == 409
    finally:
        main.RUNNING.discard("higheredjobs")


def test_every_endpoint_runs_on_the_event_loop():
    # The app shares one sqlite3 connection. Sync endpoints run in a threadpool and used it
    # concurrently with the scraper ("bad parameter or other API misuse"); async endpoints
    # all run on the single event-loop thread, so database access never overlaps.
    import inspect
    from fastapi.routing import APIRoute

    sync = [route.path for route in main.app.routes if isinstance(route, APIRoute) and not inspect.iscoroutinefunction(route.endpoint)]
    assert sync == []


def test_health_identifies_this_app():
    # Scripts use this to tell this dashboard apart from another project on the same port.
    assert TestClient(main.app).get("/api/health").json() == {"ok": True, "app": "higheredjobs-review"}


def test_sponsorship_filter_accepts_list_and_single(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    try:
        for code, date, text in [
            ("1", "2026-10-20", "Visa sponsorship is not available."),
            ("2", "2026-10-21", "Visa status questions go to HR."),
            ("3", "2026-10-22", "Visa sponsorship is available."),
        ]:
            main.database.upsert(JobDraft(higheredjobs_url=f"https://h/{code}", posted_date=date, normalized_description=text))
        client = TestClient(main.app)
        both = client.get("/api/jobs?days=all&sponsorship=Unsure%20-%20Review,Sponsorship%20Possible").json()["items"]
        assert [item["posted_date"] for item in both] == ["2026-10-22", "2026-10-21"]
        assert client.get("/api/jobs?days=all&sponsorship=Not%20Worth%20It").json()["total"] == 1
        assert client.get("/api/jobs?days=all&sponsorship=").json()["total"] == 3
    finally:
        main.database = original


def _air_job(database, job_id: str, due: str | None):
    database.upsert(
        JobDraft(
            source="air",
            source_job_id=job_id,
            source_url=f"https://www.airweb.org/community/Career-Center/{job_id}",
            title=f"AIR {job_id}",
            application_due_date=due,
            description_status="Pending",
        )
    )


def test_air_jobs_sort_and_filter_by_due_date(tmp_path):
    from datetime import date, timedelta

    database = Database(tmp_path / "jobs.sqlite3")
    today = date.today()
    _air_job(database, "soon", (today + timedelta(days=3)).isoformat())
    _air_job(database, "later", (today + timedelta(days=20)).isoformat())
    _air_job(database, "expired", (today - timedelta(days=2)).isoformat())
    _air_job(database, "undated", None)

    titles = lambda **kw: [item["title"] for item in database.jobs(source="air", days="", **kw)["items"]]
    assert titles(due="upcoming", sort="due_soon") == ["AIR soon", "AIR later", "AIR undated"]
    assert titles(due="upcoming", sort="due_late") == ["AIR later", "AIR soon", "AIR undated"]
    assert titles(due="7", sort="due_soon") == ["AIR soon"]
    assert titles(due="30", sort="due_soon") == ["AIR soon", "AIR later"]
    assert titles(due="expired", sort="due_soon") == ["AIR expired"]
    assert len(titles(due="all", sort="due_soon")) == 4


def test_skipped_air_jobs_show_only_in_all_due_view(tmp_path):
    database = Database(tmp_path / "jobs.sqlite3")
    _air_job(database, "skip", None)
    job_id = database.jobs(source="air", days="all")["items"][0]["id"]
    database.update_job(job_id, {"application_status": "Skipped"})
    assert database.jobs(source="air", days="", due="upcoming")["total"] == 0
    assert database.jobs(source="air", days="", due="all")["total"] == 1
