import pytest

from backend.app.early_career import (
    WORKDAY_SEARCH_TERMS,
    early_career,
    keep_job,
    location_allowed,
    title_candidate,
)


@pytest.mark.parametrize("title", [
    "Software Engineer I", "Software Engineer 1", "Associate Software Engineer",
    "Software Developer I", "Junior Software Engineer", "Software Engineer, New Grad",
    "New Grad Software Engineering", "Backend Engineer, Entry Level",
    "Full Stack Developer - Early Career", "Frontend Software Engineer I",
])
def test_kept_on_title(title):
    assert keep_job(title, "Remote", None)


@pytest.mark.parametrize("title", [
    "Software Engineer II", "Software Engineer III", "Senior Software Engineer",
    "Sr. Software Engineer", "Staff Software Engineer", "Principal Software Engineer",
    "Lead Software Developer", "Software Engineering Manager", "Software Engineer Intern",
    "Software Engineering Internship", "Associate Product Manager", "Mobile Engineer I",
    "Data Engineer I", "Help Desk Technician",
])
def test_dropped_on_title(title):
    assert not keep_job(title, "Remote", "new grad")


@pytest.mark.parametrize("description", [
    "open to new grads", "New Graduate role", "2026 graduate", "2027 graduate",
    "0-2 years of experience", "0 to 2 years", "0 years of experience",
])
def test_plain_title_kept_on_description(description):
    assert keep_job("Software Engineer", "New York, NY", description)


@pytest.mark.parametrize("description", ["10-20 years", "20 years of experience", "5 years", None])
def test_plain_title_dropped_without_signal(description):
    assert not keep_job("Software Engineer", "New York, NY", description)


@pytest.mark.parametrize("location", [
    None, "", "Remote", "United States", "Seattle, San Francisco, New York City",
    "Toronto, Canada or New York, NY", "Austin, TX", "Remote - USA",
])
def test_location_allowed(location):
    assert location_allowed(location)


@pytest.mark.parametrize("location", ["Israel, Yokneam", "London, United Kingdom", "Remote - Canada", "Bengaluru, India"])
def test_location_rejected(location):
    assert not location_allowed(location)


def test_sponsorship_wording_never_removes_a_job():
    assert keep_job("Software Engineer I", "Remote", "We are unable to sponsor visas.")


def test_title_candidate_ignores_early_career_wording():
    # Workday fetches details for any software title that is not excluded; rule 3 runs after.
    assert title_candidate("Software Engineer")
    assert not title_candidate("Senior Software Engineer")
    assert not title_candidate(None)


def test_early_career_needs_title_or_description_signal():
    assert early_career("Software Engineer I", None)
    assert early_career("Software Engineer", "new grad")
    assert not early_career("Software Engineer", "")


def test_workday_terms_cover_each_role_family():
    assert set(WORKDAY_SEARCH_TERMS) == {"software engineer", "software developer", "backend engineer", "full stack developer"}
