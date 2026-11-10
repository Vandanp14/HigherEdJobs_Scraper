from backend.app.database import Database
from backend.app.parser import JobDraft


def seed(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    ids = {}
    for source, key in (("higheredjobs", "h1"), ("higheredjobs", "h2"), ("greenhouse", "g1")):
        job_id, _ = db.upsert_job(
            JobDraft(source=source, source_job_id=key, source_url=f"https://x/{key}", title=key,
                     normalized_description="We sponsor H-1B visas."),
            "data",
        )
        db.add_match(job_id, "software")
        ids[key] = job_id
    db.start_run(["data"], source="higheredjobs")
    db.start_run([], source="greenhouse")
    return db, ids


def count(db, table):
    return db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_source_counts_report_applied_and_notes(tmp_path):
    db, ids = seed(tmp_path)
    db.update_job(ids["h1"], {"application_status": "Applied"})
    db.update_job(ids["h2"], {"notes": "x"})
    db.update_job(ids["g1"], {"notes": "   "})
    assert db.source_counts() == [
        {"source": "higheredjobs", "jobs": 2, "applied": 1, "with_notes": 1},
        {"source": "greenhouse", "jobs": 1, "applied": 0, "with_notes": 0},
    ]


def test_delete_source_removes_only_that_source_and_its_children(tmp_path):
    db, ids = seed(tmp_path)
    assert db.delete_source("greenhouse") == {"jobs": 1, "runs": 1}
    for table in ("job_search_matches", "sponsorship_analysis"):
        orphans = db.connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE job_id NOT IN (SELECT id FROM jobs)"
        ).fetchone()[0]
        assert orphans == 0
    assert count(db, "jobs") == 2
    assert count(db, "job_search_matches") == 4  # 2 jobs x (data, software)
    assert count(db, "sponsorship_analysis") == 2
    assert [row["source"] for row in db.connection.execute("SELECT source FROM scrape_runs")] == ["higheredjobs"]


def test_delete_source_unknown_returns_zero(tmp_path):
    db, _ = seed(tmp_path)
    assert db.delete_source("nope") == {"jobs": 0, "runs": 0}
    assert count(db, "jobs") == 3


def test_source_counts_ignores_run_only_sources(tmp_path):
    db, _ = seed(tmp_path)
    db.start_run([], source="lever")
    assert "lever" not in [row["source"] for row in db.source_counts()]
    assert db.delete_source("lever") == {"jobs": 0, "runs": 1}
    db.start_run([], source="lever")
    assert db.clear_jobs()["runs"] >= 1
    assert count(db, "scrape_runs") == 0


def test_clear_jobs_returns_counts(tmp_path):
    db, _ = seed(tmp_path)
    assert db.clear_jobs() == {"jobs": 3, "runs": 2}
    assert count(db, "jobs") == 0
    assert db.clear_jobs() == {"jobs": 0, "runs": 0}
