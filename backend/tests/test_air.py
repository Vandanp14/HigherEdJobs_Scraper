from datetime import datetime
from pathlib import Path

import pytest

from backend.app.database import Database
from backend.app.parser import ParseError, parse_air_job, parse_air_results


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 28, 12, 0)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_air_listing_parser_uses_semantic_cells_and_deduplicates_links():
    jobs = parse_air_results(
        fixture("air_listing.html"),
        "https://www.airweb.org/community/Career-Center/",
        NOW,
    )

    assert [job.source_job_id for job in jobs] == ["21096", "21087", "21076"]
    assert jobs[0].source_url == "https://www.airweb.org/community/Career-Center/21096"
    assert jobs[0].salary == "$85000 - $85000"
    assert jobs[1].salary is None
    assert jobs[1].application_due_date == "2020-09-02"
    assert jobs[1].description_status == "Pending"
    assert jobs[2].application_due_date == "2026-10-16"


def test_air_empty_result_is_successful():
    assert parse_air_results(
        fixture("air_empty.html"),
        "https://www.airweb.org/community/Career-Center/",
        NOW,
    ) == []


def test_air_markup_change_fails_loudly():
    with pytest.raises(ParseError, match="listing table"):
        parse_air_results(
            fixture("air_changed.html"),
            "https://www.airweb.org/community/Career-Center/",
            NOW,
        )


def test_air_detail_parser_captures_description_metadata_and_application_link():
    job = parse_air_job(
        fixture("air_detail.html"),
        "https://www.airweb.org/community/Career-Center/21096",
        NOW,
    )

    assert job.title == "Data Governance Manager"
    assert job.institution == "University of Idaho"
    assert job.location == "Moscow, Idaho"
    assert job.salary == "$85000 - $85000"
    assert job.application_due_date == "2026-11-23"
    assert "visa sponsorship is available" in job.normalized_description.lower()
    assert job.apply_url == "https://apptrkr.com/9816040"


def test_source_identity_and_status_are_preserved_on_air_rerun(tmp_path):
    database = Database(tmp_path / "jobs.sqlite3")
    first = parse_air_results(
        fixture("air_listing.html"),
        "https://www.airweb.org/community/Career-Center/",
        NOW,
    )[0]
    assert database.upsert(first)
    database.update_job(1, {"application_status": "Applied", "notes": "Follow up"})

    first.description_status = "Failed"
    first.salary = "$90000 - $95000"
    assert not database.upsert(first)

    item = database.jobs(source="air")["items"][0]
    assert item["salary"] == "$90000 - $95000"
    assert item["application_status"] == "Applied"
    assert item["notes"] == "Follow up"
    assert item["description_status"] == "Failed"
