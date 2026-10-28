from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.database import Database
from backend.app.parser import JobDraft


def draft(number: int, title: str, description: str | None = None) -> JobDraft:
    return JobDraft(
        source="higheredjobs",
        higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={800000 + number}",
        title=title,
        institution="Example University",
        posted_date=date.today().isoformat(),
        normalized_description=description,
        description_status="Complete" if description else "Pending",
    )


@pytest.fixture
def database(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    try:
        yield main.database
    finally:
        main.database = original


def titles(response) -> list[str]:
    return sorted(item["title"] for item in response.json()["items"])


def test_saved_jobs_carry_their_seniority_flags(database):
    database.upsert(draft(1, "Senior Data Analyst"))
    item = TestClient(main.app).get("/api/jobs?source=higheredjobs").json()["items"][0]
    assert item["seniority_flags"] == [{"label": "Senior / Lead", "evidence": "Senior"}]


def test_hide_excludes_only_the_named_labels(database):
    database.upsert(draft(1, "Senior Data Analyst"))
    database.upsert(draft(2, "Data Analyst"))
    database.upsert(draft(3, "Director of IT"))
    client = TestClient(main.app)
    base = "/api/jobs?source=higheredjobs"
    assert titles(client.get(base + "&hide=Senior / Lead")) == ["Data Analyst", "Director of IT"]
    assert titles(client.get(base + "&hide=Senior / Lead,Director")) == ["Data Analyst"]
    assert titles(client.get(base + "&hide=")) == ["Data Analyst", "Director of IT", "Senior Data Analyst"]
    assert titles(client.get(base + "&hide=Bogus")) == ["Data Analyst", "Director of IT", "Senior Data Analyst"]
    assert client.get(base + "&hide=Senior / Lead").json()["total"] == 2


def test_relabel_labels_rows_saved_before_seniority_existed(database):
    database.upsert(draft(1, "IT Manager"))
    database.connection.execute("UPDATE jobs SET seniority_flags='[]', seniority_version=NULL")
    database.connection.commit()
    assert database.relabel_seniority(only_outdated=True) == 1
    assert database.relabel_seniority(only_outdated=True) == 0
    item = TestClient(main.app).get("/api/jobs?source=higheredjobs").json()["items"][0]
    assert [flag["label"] for flag in item["seniority_flags"]] == ["Leadership"]


def test_description_flags_follow_reanalysis(database):
    database.upsert(draft(1, "Data Analyst", "Minimum of 5 years of experience required."))
    assert database.reanalyze() == 1
    item = TestClient(main.app).get("/api/jobs?source=higheredjobs").json()["items"][0]
    assert item["seniority_flags"] == [{"label": "5+ years", "evidence": "5 years"}]


def test_startup_relabels_outdated_rows(database):
    database.upsert(draft(1, "Postdoctoral Fellow in Data Science"))
    database.connection.execute("UPDATE jobs SET seniority_flags='[]', seniority_version='old'")
    database.connection.commit()
    main.relabel_on_startup(database)
    item = TestClient(main.app).get("/api/jobs?source=higheredjobs").json()["items"][0]
    assert [flag["label"] for flag in item["seniority_flags"]] == ["Postdoc / PhD"]
