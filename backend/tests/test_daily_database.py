from backend.app.database import Database
from backend.app.parser import JobDraft


def test_clear_jobs_removes_matches_and_analysis(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/1", normalized_description="We sponsor H-1B visas."), "data")
    db.start_run(["data"])
    db.clear_jobs()
    for table in ("jobs", "job_search_matches", "sponsorship_analysis", "scrape_runs"):
        assert db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert len(db.groups()) == 8


def test_clear_jobs_on_fresh_database(tmp_path):
    Database(tmp_path / "new.sqlite3").clear_jobs()


def test_add_match_records_second_group(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, is_new = db.upsert_job(JobDraft(higheredjobs_url="https://x/1"), "data")
    db.add_match(job_id, "software")
    rows = db.connection.execute(
        "SELECT search_group_id FROM job_search_matches WHERE job_id=? ORDER BY 1", (job_id,)
    ).fetchall()
    assert is_new
    assert [row[0] for row in rows] == ["data", "software"]


def test_it_group_disable_runs_once(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    db = Database(path)
    assert {group["id"]: group["enabled"] for group in db.groups()}["it"] is False
    db.set_group_enabled("it", True)
    assert {group["id"]: group["enabled"] for group in Database(path).groups()}["it"] is True
