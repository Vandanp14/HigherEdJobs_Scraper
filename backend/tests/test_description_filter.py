from backend.app.database import Database
from backend.app.parser import JobDraft


def make_draft(description: str | None, status: str | None = None) -> JobDraft:
    return JobDraft(
        higheredjobs_id="123",
        higheredjobs_url="https://www.higheredjobs.com/search/details.cfm?JobCode=123",
        title="Test role",
        normalized_description=description,
        description_status=status,
    )


def test_complete_description_is_not_downgraded_by_a_failed_refresh(tmp_path):
    database = Database(tmp_path / "jobs.sqlite3")
    database.upsert(make_draft("A complete job description."))
    database.upsert(make_draft(None, "Failed"))

    complete = database.jobs(days="all", description="complete")["items"]

    assert len(complete) == 1
    assert complete[0]["description_status"] == "Complete"
    assert database.jobs(days="all", description="missing")["items"] == []
    assert database.jobs(days="all", description="failed")["items"] == []
