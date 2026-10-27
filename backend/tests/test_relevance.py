import pytest

from backend.app.relevance import is_cs_title, is_teaching_title

CS_TITLES = [
    "Software Developer 1",
    "Research Engineer III - Software Developer",
    "Programmer Analyst",
    "IT Applications Developer",
    "IT Data Analyst - Level 1",
    "Senior Data Analyst",
    "Data Analytics Engineer",
    "Data Engineer Lead",
    "Part-Time Data Scientist",
    "Web Developer, Intermediate",
    "Full-Stack Engineer",
    "Front End Developer",
    "Enterprise Systems Administrator",
    "Windows System Administrator I",
    "Ca Tower Business Systems Analyst",
    "Workday Systems Analyst, Finance",
    "Database Administrator",
    "AI Solutions Engineer",
    "Machine Learning Engineer - Secure AI Lab",
    "Cloud Engineer",
    "DevOps Engineer",
    "Network Engineer II",
    "Cybersecurity Analyst",
    "Information Security Analyst",
    "Research Lab IT Manager",
    "HPC Engineer, IT High Performance Computing Engineer (# JR105258)",
    "Bioinformatician II Cancer Center",
    "Business Intelligence Developer",
    "Digital Accessibility Analyst Ii",
    "UX Designer",
    "Applications Support Analyst I",
    "Application Architect - DARPA SciFy Project - Penn Engineering",
    "Senior Application & Infrastructure Engineer",
    "Linux Server Engineer Senior",
    "Senior .NET Engineer, DMAHS Grant (Hamilton, NJ)",
    "Salesforce Administrator",
    "Servicenow Architect",
    "HRIS Administrator",
    "Desktop Support Specialist Intermediate/Associate",
    "Digital Transformation Officer/Chief Information Officer (CIO)",
    "Computational Scientist (2) - t229903",
    "Endpoint Management Analyst",
    "Release Manager",
    "Systems R&D Engineer",
    "Systems and Applications Development Librarian",
    "Institutional Research Analyst",
    "CRM Analyst",
    "Lead Identity & Access Management Engineer",
    "Application Solutions Analyst",
    "Hardware Asset Management Process Owner",
]

OFF_FIELD_TITLES = [
    "Faculty-Chemistry (Fall 2027)",
    "Assistant Professor in Experimental Electrochemistry",
    "Annual Giving Director",
    "Compensation Analyst",
    "Laboratory Technician",
    "Dean, College of Business",
    "Title III Project Coordinator",
    "Postdoctoral Researcher (Geotechnical Engineering)",
    "Assistant Professor in Accounting",
    "4-H Communications & Marketing Coordinator",
    "Program Associate, Graduate Clinical Placement",
    "Director of Development Research, RPD (10008996)",
    "Procurement Transformation Manager (CEMI)",
    "Area Coordinator for Residence Life and Residential Programming (12 month live-in position)",
    "Programming & Outreach Specialist - Gephardt Institute for Civic and Community Engagement",
    "Job Developer, Gateway to Innovation (Grant-funded)",
    "IB Assessment Content Developer for Finnish B (Diploma Programme)",
    "Part-Time Career and Business Services Developer",
    "Biorepository Supply Coordinator - CTO",
    "Coding Coordinator (Primary - Specialty Care) - Professional Coding Division (PCD)",
    "Assistant Professor, Industrial and Systems Engineering (Advanced Manufacturing Operations)",
]


@pytest.mark.parametrize("title", CS_TITLES)
def test_cs_titles_are_kept(title):
    assert is_cs_title(title)


@pytest.mark.parametrize("title", OFF_FIELD_TITLES)
def test_off_field_titles_are_dropped(title):
    assert not is_cs_title(title)


TEACHING_TITLES = [
    "Dean of the Erik Jonsson School of Engineering and Computer Science",
    "Department Chair - Electrical and Computer Engineering",
    "Remote Grading Assistant - Software Development Life Cycle (SDLC) II (Spring 2027)",
    "Multiple Open Rank Tenured/Tenure-Track Fac in Lifetime Learning Sys, Learning Sci, AI in Education",
    "Tenure-Track Data Science Position",
    "Visiting Assistant Professor of Computer Science",
    "Adjunct Lecturer - Health Informatics",
    "Senior Lecturer of Data Science",
    "Computer Information Technology Instructor",
    "IT - Software Developer Instructor Pool - Adjunct (Part-time)",
    "Faculty - Computer Science Masters Programs (Course Director)",
    "Assistant Teaching Professor,  Industrial and System Engineering Department",
]


@pytest.mark.parametrize("title", TEACHING_TITLES)
def test_teaching_titles_are_dropped_even_in_cs(title):
    assert is_teaching_title(title)
    assert not is_cs_title(title)


def test_it_department_names_are_not_teaching():
    assert is_cs_title("Software Developer I, Instructional and Information Technology Services")
    assert is_cs_title("Technical Support Specialist - School of Computer Science")


def test_lowercase_it_word_is_not_information_technology():
    assert not is_cs_title("Make it Happen Coordinator")


import asyncio
from dataclasses import replace

from backend.app import scraper
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.parser import JobDraft
from backend.tests.test_scraper_dedupe import LISTING, FakeContext


def run_group(tmp_path, monkeypatch, title, group):
    monkeypatch.setattr(scraper, "parse_results", lambda html, url, now: [JobDraft(higheredjobs_url=LISTING, title=title)])
    monkeypatch.setattr(scraper, "parse_job", lambda html, url, now: JobDraft(higheredjobs_url=url, normalized_description="Text"))
    database = Database(tmp_path / "jobs.sqlite3")
    job_scraper = scraper.HigherEdJobsScraper(database, replace(Settings(), request_delay=0, headless=True))
    context = FakeContext()
    counts = asyncio.run(job_scraper._run_group(context, group, {}, []))
    return database, context, counts


def test_keyword_group_skips_off_field_title_without_opening_it(tmp_path, monkeypatch, capsys):
    database, context, counts = run_group(tmp_path, monkeypatch, "Faculty-Chemistry (Fall 2027)", {"id": "data", "name": "Data", "query": "q"})
    assert context.detail_loads == 0
    assert counts == (0, 0, 0)
    assert database.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert "1 off-field or teaching titles skipped" in capsys.readouterr().out


def test_keyword_group_keeps_cs_title(tmp_path, monkeypatch):
    _, context, counts = run_group(tmp_path, monkeypatch, "Software Developer", {"id": "data", "name": "Data", "query": "q"})
    assert context.detail_loads == 1 and counts == (1, 1, 0)


def test_category_group_keeps_any_title(tmp_path, monkeypatch):
    _, context, counts = run_group(tmp_path, monkeypatch, "Digital Content Specialist", {"id": "cat_web", "name": "Web", "query": "", "categories": "160", "trusted": True})
    assert context.detail_loads == 1 and counts == (1, 1, 0)


def test_category_group_skips_teaching_title(tmp_path, monkeypatch):
    _, context, counts = run_group(tmp_path, monkeypatch, "Adjunct Faculty - Computer Science", {"id": "cat_web", "name": "Web", "query": "", "categories": "160", "trusted": True})
    assert context.detail_loads == 0 and counts == (0, 0, 0)


def test_dashboard_hides_saved_off_field_keyword_jobs(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/1", title="Faculty-Chemistry (Fall 2027)"), "data")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/2", title="Software Developer"), "software")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/3", title="Digital Content Specialist"), "cat_web")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/5", title="Adjunct Faculty - Web Development"), "cat_web")
    db.upsert_job(JobDraft(source="air", source_url="https://air/4", higheredjobs_url="https://air/4", title="Director of Planning"))
    titles = {job["title"] for job in db.jobs(days="all", per_page=100)["items"]}
    assert titles == {"Software Developer", "Digital Content Specialist", "Director of Planning"}


def test_title_checked_category_group_skips_off_field_title(tmp_path, monkeypatch):
    group = {"id": "cat_cs_related", "name": "Related", "query": "", "categories": "31", "trusted": False}
    _, context, counts = run_group(tmp_path, monkeypatch, "Director of Planning", group)
    assert context.detail_loads == 0 and counts == (0, 0, 0)
    _, context, counts = run_group(tmp_path / "b", monkeypatch, "Institutional Research Data Analyst", group)
    assert context.detail_loads == 1 and counts == (1, 1, 0)


def test_dashboard_needs_cs_title_for_title_checked_category(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/1", title="Assessment Coordinator"), "cat_cs_related")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/2", title="Research Data Analyst"), "cat_cs_related")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/3", title="Help Center Associate"), "cat_it_support")
    titles = {job["title"] for job in db.jobs(days="all", per_page=100)["items"]}
    assert titles == {"Research Data Analyst", "Help Center Associate"}
