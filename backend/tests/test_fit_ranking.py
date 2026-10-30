"""Age-weighted fit ranking: within 14 days fit decides, after that age takes charge."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.database import Database
from backend.app.fit import rank_value
from backend.app.parser import JobDraft


@pytest.mark.parametrize("better, worse", [
    ((90, 1), (60, 0)),    # ideal yesterday beats average today
    ((90, 13), (60, 0)),   # a much better match wins inside two weeks
    ((70, 0), (70, 3)),    # newer wins a tie
    ((60, 0), (90, 30)),   # past two weeks, age takes charge
    ((20, 29), (95, 45)),  # anything older than 30 days sits below the last 30 days
    ((90, 20), (30, 2)),   # an older job still beats a poor recent match
])
def test_rank_value_acceptance_table(better, worse):
    assert rank_value(*better) > rank_value(*worse)


def test_null_score_and_undated_sort_last():
    assert rank_value(None, 0) < rank_value(0, 200)
    assert rank_value(100, None) < rank_value(0, 30)


@pytest.fixture
def database(tmp_path):
    original = main.database
    main.database = Database(tmp_path / "jobs.sqlite3")
    try:
        yield main.database
    finally:
        main.database = original


def seed(db, number: int, fit: int | None, age: int, status: str = "New") -> int:
    job_id, _ = db.upsert_job(JobDraft(
        source="higheredjobs",
        higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={500000 + number}",
        title=f"Software Developer {number:02d}",
        institution="Example University",
        posted_date=(date.today() - timedelta(days=age)).isoformat(),
        description_status="Pending",
    ))
    db.connection.execute(
        "UPDATE jobs SET fit_score=?, fit_details=?, application_status=? WHERE id=?",
        (fit, '{"matched": ["Python"]}' if fit is not None else "{}", status, job_id),
    )
    db.connection.commit()
    return job_id


def get(query: str) -> dict:
    return TestClient(main.app).get("/api/jobs?source=higheredjobs&days=all&application_status=any&" + query).json()


def titles(data: dict) -> list[str]:
    return [item["title"] for item in data["items"]]


def test_api_sort_fit_orders_by_rank(database):
    seed(database, 1, 60, 0)
    seed(database, 2, 90, 13)
    seed(database, 3, 95, 45)
    seed(database, 4, None, 0)
    assert titles(get("sort=fit")) == ["Software Developer 02", "Software Developer 01", "Software Developer 03", "Software Developer 04"]


def test_api_sort_fit_only_ignores_age(database):
    seed(database, 1, 60, 0)
    seed(database, 2, 95, 45)
    assert titles(get("sort=fit_only")) == ["Software Developer 02", "Software Developer 01"]


def test_api_min_fit_filters(database):
    seed(database, 1, 40, 0)
    seed(database, 2, 70, 0)
    data = get("sort=fit&min_fit=50")
    assert titles(data) == ["Software Developer 02"] and data["total"] == 1


def test_api_status_open_excludes_skipped_with_days_all(database):
    seed(database, 1, 50, 0, status="Skipped")
    seed(database, 2, 50, 0, status="New")
    data = TestClient(main.app).get("/api/jobs?source=higheredjobs&days=all&application_status=open").json()
    assert titles(data) == ["Software Developer 02"]


def test_api_status_unapplied_excludes_applied_and_skipped(database):
    seed(database, 1, 50, 0, status="Skipped")
    seed(database, 2, 50, 0, status="Applied")
    seed(database, 3, 50, 0, status="Opened")
    assert titles(get("application_status=unapplied")) == ["Software Developer 03"]


def test_api_fit_paging_reaches_every_job(database):
    for number in range(1, 62):
        seed(database, number, 50, 0)
    seen = []
    for page in (1, 2):
        data = get(f"sort=fit&page={page}")
        assert data["total"] == 61
        seen += [item["id"] for item in data["items"]]
    assert len(seen) == len(set(seen)) == 61


def test_api_items_carry_fit_fields(database):
    seed(database, 1, 80, 2)
    item = get("sort=fit")["items"][0]
    assert item["fit_score"] == 80
    assert item["fit_details"] == {"matched": ["Python"]}
    assert item["age_days"] == 2
    assert item["rank_value"] == pytest.approx(rank_value(80, 2), abs=0.05)
