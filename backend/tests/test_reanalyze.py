import json

from backend.app.classifier import VERSION
from backend.app.database import Database
from backend.app.parser import JobDraft

ESCAPED = "&lt;p&gt;Duties.&lt;/p&gt;&lt;p&gt;Visa sponsorship is not available.&lt;/p&gt;"


def analysis(db, job_id):
    return db.connection.execute("SELECT * FROM sponsorship_analysis WHERE job_id=?", (job_id,)).fetchone()


def test_reanalyze_renormalizes_from_raw(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", raw_description=ESCAPED,
                                       normalized_description="<p>Duties.</p><p>Visa sponsorship is not available.</p>"))
    db.reanalyze()
    row = db.connection.execute("SELECT raw_description, normalized_description FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert row["normalized_description"] == "Duties.\nVisa sponsorship is not available."
    assert row["raw_description"] == ESCAPED
    assert analysis(db, job_id)["status"] == "Not Worth It"
    assert analysis(db, job_id)["evidence"] == "Visa sponsorship is not available."


def test_reanalyze_without_raw_strips_tags(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", normalized_description="<p>Visa sponsorship is not available.</p>"))
    db.reanalyze()
    assert analysis(db, job_id)["status"] == "Not Worth It"
    assert "<" not in analysis(db, job_id)["evidence"]


def test_signals_column_round_trips(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.upsert_job(JobDraft(higheredjobs_url="https://h/1", institution="State University",
                           normalized_description="We participate in E-Verify."))
    item = db.jobs(days="all")["items"][0]
    assert json.loads(item["signals"]) == ["E-Verify"]


def test_startup_relabel_only_touches_old_versions(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    old, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", normalized_description="Visa sponsorship is not available."))
    current, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/2", normalized_description="Plain text."))
    db.connection.execute("UPDATE sponsorship_analysis SET classifier_version='1.1.0', analyzed_at='2000-01-01' WHERE job_id=?", (old,))
    db.connection.execute("UPDATE sponsorship_analysis SET analyzed_at='2000-01-02' WHERE job_id=?", (current,))
    assert db.reanalyze(only_outdated=True) == 1
    assert analysis(db, old)["classifier_version"] == VERSION
    assert analysis(db, current)["analyzed_at"] == "2000-01-02"


def test_html_entities_in_title_and_institution_are_decoded(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", title="Systems R&amp;D Engineer", institution="William &amp; Mary"))
    row = db.connection.execute("SELECT title, institution FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert (row["title"], row["institution"]) == ("Systems R&D Engineer", "William & Mary")


def test_reanalyze_decodes_titles_saved_before_the_fix(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", normalized_description="Text."))
    db.connection.execute("UPDATE jobs SET title='BI &amp; Data' WHERE id=?", (job_id,))
    db.reanalyze()
    assert db.connection.execute("SELECT title FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "BI & Data"


def test_double_escaped_title_is_fully_decoded(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", title="Earth &amp;amp; Environment"))
    assert db.connection.execute("SELECT title FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "Earth & Environment"


def test_reanalyze_keeps_angle_bracket_text_in_compacted_rows(tmp_path):
    # Compacted rows have no raw HTML to rebuild from, so plain text must not be reparsed as HTML.
    db = Database(tmp_path / "jobs.sqlite3")
    job_id, _ = db.upsert_job(JobDraft(higheredjobs_url="https://h/1", normalized_description="Send CV to <jobs@x.edu> by Friday."))
    db.reanalyze()
    assert db.connection.execute("SELECT normalized_description FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "Send CV to <jobs@x.edu> by Friday."


def test_startup_relabel_failure_does_not_stop_the_server(capsys):
    from backend.app import main

    class Broken:
        def reanalyze(self, only_outdated=False):
            raise ValueError("bad row")

    main.relabel_on_startup(Broken())
    assert "bad row" in capsys.readouterr().err
