"""Fit scores are stored with each HigherEdJobs job and refreshed when the rules or resume change."""
import json
from datetime import date

from backend.app.database import Database
from backend.app.fit import load_resume, version_for
from backend.app.parser import JobDraft

RESUME = {
    "skills": [{"name": "All", "keywords": ["Python", "SQL"]}],
    "projects": [{"technologies": ["Python"]}],
}


def write_resume(tmp_path, data=RESUME):
    path = tmp_path / "resume.json"
    path.write_text(json.dumps(data))
    return path


def draft(number: int, source: str = "higheredjobs") -> JobDraft:
    return JobDraft(
        source=source,
        higheredjobs_url=f"https://www.higheredjobs.com/details.cfm?JobCode={600000 + number}",
        source_url=f"https://example.org/{source}/{number}",
        title="Software Developer",
        institution="Example University",
        posted_date=date.today().isoformat(),
        normalized_description="Required Qualifications\nPython and SQL.",
        description_status="Complete",
    )


def stored(db, column="fit_score"):
    return db.connection.execute(f"SELECT {column} FROM jobs").fetchone()[0]


def test_upsert_scores_higheredjobs_jobs(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3", write_resume(tmp_path))
    db.upsert(draft(1))
    assert isinstance(stored(db), int)
    assert json.loads(stored(db, "fit_details"))["matched"] == ["Python", "SQL"]
    assert stored(db, "fit_version") == version_for(db.resume)


def test_air_jobs_are_not_scored(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3", write_resume(tmp_path))
    db.upsert(draft(1, source="air"))
    assert stored(db) is None


def test_no_resume_leaves_scores_null(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3", tmp_path / "missing.json")
    db.upsert(draft(1))
    assert db.resume is None and stored(db) is None
    assert db.rescore_fit(only_outdated=True) == 0


def test_resume_change_rescores_on_startup(tmp_path):
    path = write_resume(tmp_path)
    db = Database(tmp_path / "jobs.sqlite3", path)
    db.upsert(draft(1))
    assert db.rescore_fit(only_outdated=True) == 0
    write_resume(tmp_path, {"skills": [{"keywords": ["Python"]}]})
    reopened = Database(tmp_path / "jobs.sqlite3", path)
    assert reopened.rescore_fit(only_outdated=True) == 1
    assert json.loads(stored(reopened, "fit_details"))["matched"] == ["Python"]
    assert stored(reopened, "fit_version") == version_for(load_resume(path))


def test_reanalyze_refreshes_fit(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3", write_resume(tmp_path))
    db.upsert(draft(1))
    db.connection.execute("UPDATE jobs SET fit_version=NULL, fit_score=NULL")
    db.reanalyze()
    assert stored(db, "fit_version") == version_for(db.resume) and stored(db) is not None


def test_startup_rescores_saved_jobs(tmp_path):
    from backend.app import main

    db = Database(tmp_path / "jobs.sqlite3", write_resume(tmp_path))
    db.upsert(draft(1))
    db.connection.execute("UPDATE jobs SET fit_version=NULL, fit_score=NULL")
    db.connection.commit()
    main.relabel_on_startup(db)
    assert stored(db) is not None
