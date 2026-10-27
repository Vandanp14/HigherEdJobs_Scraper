from backend.app.config import SEARCH_GROUPS
from backend.app.database import Database
from backend.app.parser import JobDraft


def test_clear_jobs_removes_matches_and_analysis(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/1", normalized_description="We sponsor H-1B visas."), "data")
    db.start_run(["data"])
    db.clear_jobs()
    for table in ("jobs", "job_search_matches", "sponsorship_analysis", "scrape_runs"):
        assert db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert len(db.groups()) == len(SEARCH_GROUPS)


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


def test_saved_jobs_lists_only_complete_jobs_for_source(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    done, _ = db.upsert_job(JobDraft(higheredjobs_url="https://x/1", normalized_description="Text"), "data")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/2", description_status="Failed"), "data")
    db.upsert_job(JobDraft(source="air", source_url="https://air/3", normalized_description="Text"))
    assert db.saved_jobs("higheredjobs") == {"https://x/1": done}


def test_close_interrupted_runs_marks_unfinished_runs(tmp_path):
    # A run cut off by Ctrl+C never reaches finish_run; left open, the dashboard shows it as running forever.
    db = Database(tmp_path / "jobs.sqlite3")
    run_id = db.start_run(["data"])
    db.close_interrupted_runs()
    run = db.latest_run("higheredjobs")
    assert run["id"] == run_id
    assert run["completed_at"] is not None
    assert run["errors"] == [{"error": "Run was interrupted before it finished."}]
