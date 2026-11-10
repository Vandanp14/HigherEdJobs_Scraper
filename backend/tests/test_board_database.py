"""Company boards storage: the company list, board jobs, closing and reopening, and wipes."""
import json

import pytest

from backend.app.database import FIT_SOURCES, Database
from backend.app.parser import JobDraft, normalize_ats_description
from backend.app.sources.refs import BoardRef

RESUME = {"skills": [{"name": "All", "keywords": ["Python", "SQL"]}], "projects": [{"technologies": ["Python"]}]}


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "jobs.sqlite3")


@pytest.fixture
def db_with_resume(tmp_path):
    path = tmp_path / "resume.json"
    path.write_text(json.dumps(RESUME))
    return Database(tmp_path / "jobs.sqlite3", path)


def company(db, slug="stripe", ats="greenhouse"):
    db.upsert_company(BoardRef(ats, slug), None, "manual")
    return next(c for c in db.companies(enabled_only=False) if c["slug"] == slug)


def board_draft(number: int, source="greenhouse", description="Python and SQL. Open to new grads."):
    return JobDraft(
        source=source,
        source_job_id=f"stripe:{number}",
        source_url=f"https://job-boards.greenhouse.io/stripe/jobs/{number}",
        title="Software Engineer I",
        institution="Stripe",
        raw_description=f"<p>{description}</p>",
        normalized_description=description,
        description_status="Complete",
    )


def active(db, job_id):
    return db.connection.execute("SELECT active FROM jobs WHERE id=?", (job_id,)).fetchone()[0]


def test_company_upsert_is_case_insensitive_and_keeps_first_slug(db):
    assert db.upsert_company(BoardRef("greenhouse", "Stripe"), None, "commoncrawl")
    assert not db.upsert_company(BoardRef("greenhouse", "stripe"), "Stripe", "simplify")
    companies = db.companies()
    assert [c["slug"] for c in companies] == ["Stripe"]
    # A later sighting may supply the name the first one lacked.
    assert companies[0]["name"] == "Stripe"


def test_same_slug_on_another_ats_is_another_company(db):
    db.upsert_company(BoardRef("greenhouse", "ramp"), None, "manual")
    db.upsert_company(BoardRef("ashby", "ramp"), None, "manual")
    assert len(db.companies()) == 2


def test_workday_sites_of_one_tenant_are_separate_companies(db):
    db.upsert_company(BoardRef("workday", "nvidia", "nvidia.wd5.myworkdayjobs.com", "External"), None, "manual")
    db.upsert_company(BoardRef("workday", "nvidia", "nvidia.wd5.myworkdayjobs.com", "University"), None, "manual")
    assert {c["site"] for c in db.companies()} == {"External", "University"}


def test_five_404s_disable_but_other_errors_do_not(db):
    missing, broken = company(db, "gone"), company(db, "flaky")
    for _ in range(5):
        db.record_company_check(missing["id"], error="404 Not Found", missing=True)
        db.record_company_check(broken["id"], error="500 Server Error")
    remaining = db.companies()
    assert [c["slug"] for c in remaining] == ["flaky"]
    assert remaining[0]["last_error"] == "500 Server Error"
    assert remaining[0]["consecutive_failures"] == 5


def test_success_resets_failures(db):
    flaky = company(db, "flaky")
    db.record_company_check(flaky["id"], error="404", missing=True)
    db.record_company_check(flaky["id"])
    row = db.companies()[0]
    assert row["consecutive_failures"] == 0
    assert row["last_error"] is None
    assert row["last_success_at"] is not None


def test_never_checked_companies_come_first(db):
    checked, fresh = company(db, "checked"), company(db, "fresh")
    db.record_company_check(checked["id"])
    assert [c["slug"] for c in db.companies()] == ["fresh", "checked"]


def test_save_board_job_links_company(db):
    stripe = company(db)
    job_id, is_new = db.save_board_job(stripe["id"], board_draft(1))
    assert is_new
    linked = db.connection.execute("SELECT ats_company_id FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
    assert linked == stripe["id"]


def test_known_job_ids_lists_complete_jobs_of_that_company(db):
    stripe, other = company(db), company(db, "other")
    db.save_board_job(stripe["id"], board_draft(1))
    failed = board_draft(2)
    failed.normalized_description = failed.raw_description = None
    failed.description_status = "Failed"
    db.save_board_job(stripe["id"], failed)
    assert db.known_job_ids(stripe["id"]) == {"stripe:1"}
    assert db.known_job_ids(other["id"]) == set()


def test_reconcile_closes_missing_and_reopens_seen(db):
    stripe = company(db)
    first, _ = db.save_board_job(stripe["id"], board_draft(1))
    second, _ = db.save_board_job(stripe["id"], board_draft(2))
    assert db.reconcile_board(stripe["id"], {"stripe:1"}, complete=True) == 1
    assert (active(db, first), active(db, second)) == (1, 0)
    before = db.connection.execute("SELECT last_seen_at FROM jobs WHERE id=?", (second,)).fetchone()[0]
    assert db.reconcile_board(stripe["id"], {"stripe:1", "stripe:2"}, complete=True) == 0
    assert active(db, second) == 1
    after = db.connection.execute("SELECT last_seen_at FROM jobs WHERE id=?", (second,)).fetchone()[0]
    assert after >= before


def test_incomplete_fetch_closes_nothing(db):
    stripe = company(db)
    job_id, _ = db.save_board_job(stripe["id"], board_draft(1))
    assert db.reconcile_board(stripe["id"], set(), complete=False) == 0
    assert active(db, job_id) == 1


def test_reconcile_leaves_other_companies_alone(db):
    stripe, other = company(db), company(db, "other")
    job_id, _ = db.save_board_job(stripe["id"], board_draft(1))
    db.reconcile_board(other["id"], set(), complete=True)
    assert active(db, job_id) == 1


def test_rerun_keeps_status_and_notes(db):
    stripe = company(db)
    job_id, _ = db.save_board_job(stripe["id"], board_draft(1))
    db.update_job(job_id, {"application_status": "Applied", "notes": "Referred by Sam"})
    _, is_new = db.save_board_job(stripe["id"], board_draft(1))
    row = db.connection.execute("SELECT application_status, notes FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert not is_new
    assert tuple(row) == ("Applied", "Referred by Sam")


def test_clear_jobs_keeps_board_rows(db):
    stripe = company(db)
    db.upsert_job(JobDraft(higheredjobs_url="https://x/1", normalized_description="We sponsor H-1B visas."), "data")
    db.upsert_job(JobDraft(source="air", source_url="https://air/2", normalized_description="Text"))
    job_id, _ = db.save_board_job(stripe["id"], board_draft(1))
    db.update_job(job_id, {"application_status": "Applied", "notes": "Keep me"})
    for source in ("higheredjobs", "air", "boards", "discovery"):
        db.start_run([], source=source)
    db.clear_jobs()
    rows = db.connection.execute("SELECT source, application_status, notes FROM jobs").fetchall()
    assert [tuple(row) for row in rows] == [("greenhouse", "Applied", "Keep me")]
    assert db.connection.execute("SELECT job_id FROM sponsorship_analysis").fetchall()[0][0] == job_id
    runs = {row[0] for row in db.connection.execute("SELECT source FROM scrape_runs")}
    assert runs == {"boards", "discovery"}
    assert len(db.companies()) == 1


def test_fit_scores_board_jobs_but_not_air(db_with_resume):
    db = db_with_resume
    stripe = company(db)
    board_id, _ = db.save_board_job(stripe["id"], board_draft(1))
    air_id, _ = db.upsert_job(JobDraft(source="air", source_url="https://air/2", title="Software Developer",
                                       normalized_description="Python and SQL."))
    score = lambda job_id: db.connection.execute("SELECT fit_score FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
    assert score(board_id) is not None
    assert score(air_id) is None
    db.connection.execute("UPDATE jobs SET fit_score=NULL, fit_version=NULL")
    db.rescore_fit()
    assert score(board_id) is not None
    assert "greenhouse" in FIT_SOURCES and "air" not in FIT_SOURCES


def test_ats_normalizer_unescapes_html():
    assert normalize_ats_description("&lt;p&gt;We cannot &lt;b&gt;sponsor&lt;/b&gt; visas&lt;/p&gt;") == "We cannot sponsor visas"
    assert normalize_ats_description("<ul><li>Python</li><li>SQL</li></ul>") == "Python\nSQL"


def test_board_reanalyze_uses_ats_normalizer(db, monkeypatch):
    stripe = company(db)
    db.save_board_job(stripe["id"], board_draft(1))
    calls = []
    import backend.app.database as database_module
    monkeypatch.setattr(database_module, "normalize_ats_description", lambda raw: calls.append(raw) or "Cleaned")
    db.reanalyze()
    assert calls == ["<p>Python and SQL. Open to new grads.</p>"]
    assert db.connection.execute("SELECT normalized_description FROM jobs").fetchone()[0] == "Cleaned"


def test_summary_saved_on_finish_and_returned_by_latest_run(db):
    run_id = db.start_run([], source="boards")
    db.update_run_progress(run_id, 3, 2, 1, {"companies_checked": 1})
    assert db.latest_run("boards")["summary"] == {"companies_checked": 1}
    assert db.latest_run("boards")["completed_at"] is None
    db.finish_run(run_id, 5, 3, 2, [], summary={"companies_checked": 2})
    run = db.latest_run("boards")
    assert run["summary"] == {"companies_checked": 2}
    assert (run["jobs_discovered"], run["new_jobs"], run["updated_jobs"]) == (5, 3, 2)


def test_runs_without_summary_still_finish(db):
    run_id = db.start_run(["data"])
    db.finish_run(run_id, 1, 1, 0, [])
    assert db.latest_run("higheredjobs")["summary"] == {}
