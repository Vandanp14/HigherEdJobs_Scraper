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
        "VALUES ('123','Legacy role','2026-09-01','2026-09-01',"
        "'https://www.higheredjobs.com/search/details.cfm?JobCode=123','2026-09-01','2026-09-01')"
    )
    connection.commit()
    connection.close()

    database = Database(path)
    item = database.jobs(days="all")["items"][0]
    assert item["source"] == "higheredjobs"
    assert item["source_job_id"] == "123"
    assert item["source_url"].endswith("JobCode=123")
