from dataclasses import replace

from fastapi.testclient import TestClient

from backend.app import main
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
    db.connection.execute("PRAGMA foreign_keys = OFF")  # explicit child deletes must not rely on cascades
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
    db.connection.execute("PRAGMA foreign_keys = OFF")
    assert db.clear_jobs() == {"jobs": 3, "runs": 2}
    for table in ("job_search_matches", "sponsorship_analysis"):
        assert count(db, table) == 0
    assert count(db, "jobs") == 0
    assert db.clear_jobs() == {"jobs": 0, "runs": 0}


def fat_db(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    for source in ("higheredjobs", "greenhouse"):
        for i in range(40):
            db.upsert_job(
                JobDraft(source=source, source_job_id=f"{source}{i}", source_url=f"https://x/{source}{i}",
                         title=f"t{i}", raw_description="x" * 20000),
                "data",
            )
    return db


def test_delete_source_shrinks_storage(tmp_path):
    db = fat_db(tmp_path)
    before = db.storage_bytes()
    db.delete_source("greenhouse")
    assert db.storage_bytes() < before


def test_clear_jobs_shrinks_storage(tmp_path):
    db = fat_db(tmp_path)
    before = db.storage_bytes()
    db.clear_jobs()
    assert db.storage_bytes() < before / 2


def test_vacuum_failure_warns_but_keeps_delete(tmp_path, capsys):
    import sqlite3

    db = fat_db(tmp_path)

    class Conn:
        def __init__(self, real):
            self.real = real

        def execute(self, sql, *args):
            if sql.strip().upper() == "VACUUM":
                raise sqlite3.OperationalError("database is locked")
            return self.real.execute(sql, *args)

        def __enter__(self):
            return self.real.__enter__()

        def __exit__(self, *exc):
            return self.real.__exit__(*exc)

    db.connection = Conn(db.connection)
    assert db.clear_jobs()["jobs"] == 80
    assert "VACUUM" in capsys.readouterr().err


def api(tmp_path, extra_source=None):
    db, ids = seed(tmp_path)
    if extra_source:
        db.upsert_job(JobDraft(source=extra_source, source_job_id="z1", source_url="https://x/z1", title="z1"), "data")
    original = main.database
    main.database = db
    return db, original


def test_data_sources_lists_every_source_with_names(tmp_path):
    db, original = api(tmp_path, "foo")
    try:
        rows = TestClient(main.app).get("/api/data/sources").json()
        names = {row["source"]: row["name"] for row in rows}
        assert names == {"higheredjobs": "HigherEdJobs", "greenhouse": "Greenhouse", "foo": "foo"}
        assert {"jobs", "applied", "with_notes"} <= set(rows[0])
    finally:
        main.database = original


def test_delete_source_endpoint_deletes_and_404s_after(tmp_path):
    db, original = api(tmp_path)
    try:
        client = TestClient(main.app)
        response = client.delete("/api/data/sources/higheredjobs")
        assert response.status_code == 200
        assert response.json() == {"deleted": {"jobs": 2, "runs": 1}}
        assert client.delete("/api/data/sources/higheredjobs").status_code == 404
    finally:
        main.database = original


def test_delete_source_blocked_while_that_source_runs(tmp_path):
    db, original = api(tmp_path)
    main.RUNNING.add("higheredjobs")
    try:
        response = TestClient(main.app).delete("/api/data/sources/higheredjobs")
        assert response.status_code == 409
        assert count(db, "jobs") == 3
    finally:
        main.RUNNING.discard("higheredjobs")
        main.database = original


def test_delete_source_allowed_while_other_source_runs(tmp_path):
    db, original = api(tmp_path)
    main.RUNNING.add("higheredjobs")
    try:
        response = TestClient(main.app).delete("/api/data/sources/greenhouse")
        assert response.status_code == 200
        assert count(db, "jobs") == 2
    finally:
        main.RUNNING.discard("higheredjobs")
        main.database = original


def test_clear_all_blocked_while_any_run_active(tmp_path):
    db, original = api(tmp_path)
    main.RUNNING.add("air")
    try:
        client = TestClient(main.app)
        assert client.delete("/api/data").status_code == 409
        assert count(db, "jobs") == 3
        main.RUNNING.discard("air")
        response = client.delete("/api/data")
        assert response.status_code == 200
        assert response.json()["deleted"]["jobs"] == 3
        assert client.get("/api/data/sources").json() == []
    finally:
        main.RUNNING.discard("air")
        main.database = original


def test_runs_record_storage_before_and_after(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    run_id = db.start_run(["data"], source="higheredjobs")
    for number in range(20):
        db.upsert_job(
            JobDraft(source="higheredjobs", source_job_id=str(number), source_url=f"https://x/{number}",
                     title=f"t{number}", normalized_description="We sponsor H-1B visas. " * 200),
            "data",
        )
    db.finish_run(run_id, 20, 20, 0, [])
    run = db.latest_run()
    assert run["db_bytes_before"] > 0
    assert run["db_bytes_after"] >= run["db_bytes_before"]


def test_interrupted_runs_leave_storage_after_empty(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.start_run([], source="air")
    db.close_interrupted_runs()
    assert db.latest_run()["db_bytes_after"] is None


def test_legacy_runs_have_null_storage(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE scrape_runs (
          id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
          groups_run TEXT NOT NULL DEFAULT '[]', jobs_discovered INTEGER NOT NULL DEFAULT 0,
          new_jobs INTEGER NOT NULL DEFAULT 0, updated_jobs INTEGER NOT NULL DEFAULT 0,
          errors TEXT NOT NULL DEFAULT '[]'
        );
        INSERT INTO scrape_runs(started_at,completed_at) VALUES ('2026-09-01','2026-09-01');
        """
    )
    connection.commit()
    connection.close()
    run = Database(path).latest_run()
    assert run["db_bytes_before"] is None
    assert run["db_bytes_after"] is None


def test_storage_endpoint_reports_sizes(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "database", Database(tmp_path / "jobs.sqlite3"))
    monkeypatch.setattr(main, "settings", replace(main.settings, state_path=tmp_path / "missing-state.json"))
    client = TestClient(main.app)
    body = client.get("/api/data/storage").json()
    assert isinstance(body["database_bytes"], int) and body["database_bytes"] > 0
    assert body["browser_session_bytes"] == 0

    state = tmp_path / "state.json"
    state.write_text('{"cookies": []}')
    before = state.stat().st_mtime_ns
    monkeypatch.setattr(main, "settings", replace(main.settings, state_path=state))
    body = client.get("/api/data/storage").json()
    assert body["browser_session_bytes"] == len('{"cookies": []}')
    assert state.stat().st_mtime_ns == before
    assert state.read_text() == '{"cookies": []}'
