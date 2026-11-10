"""Greenhouse, Lever and Ashby adapters against trimmed real responses saved on 2026-11-09."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from backend.app.classifier import classify
from backend.app.database import Database
from backend.app.parser import ParseError
from backend.app.sources import ashby, greenhouse, lever
from backend.app.sources.client import BoardClient
from backend.app.sources.refs import BoardRef

FIXTURES = Path(__file__).parent / "fixtures" / "boards"
COMPANIES = {
    greenhouse: {"id": 1, "ats": "greenhouse", "slug": "stripe", "name": None, "host": "", "site": ""},
    lever: {"id": 2, "ats": "lever", "slug": "spotify", "name": "Spotify", "host": "", "site": ""},
    ashby: {"id": 3, "ats": "ashby", "slug": "ramp", "name": None, "host": "", "site": ""},
}
EXPECTED = {
    greenhouse: dict(
        title="Backend Engineer, Core Technology", source_job_id="stripe:6042172",
        source_url="https://job-boards.greenhouse.io/stripe/jobs/6042172",
        apply_url="https://stripe.com/jobs/search?gh_jid=6042172", posted_date="2024-06-14", institution="Stripe",
    ),
    lever: dict(
        title="Backend Engineer - Data Platform", source_job_id="spotify:186b763a-2a61-4563-8813-ff6b40c9c8a7",
        source_url="https://jobs.lever.co/spotify/186b763a-2a61-4563-8813-ff6b40c9c8a7",
        apply_url="https://jobs.lever.co/spotify/186b763a-2a61-4563-8813-ff6b40c9c8a7/apply",
        posted_date="2026-09-28", institution="Spotify",
    ),
    ashby: dict(
        title="Software Engineer, Android", source_job_id="ramp:f564dcf9-9390-4a3f-896f-8047a5086040",
        source_url="https://jobs.ashbyhq.com/ramp/f564dcf9-9390-4a3f-896f-8047a5086040",
        apply_url="https://jobs.ashbyhq.com/ramp/f564dcf9-9390-4a3f-896f-8047a5086040/application",
        posted_date="2025-07-31", institution="Ramp",
    ),
}
ADAPTERS = [greenhouse, lever, ashby]


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def serving(body) -> BoardClient:
    return BoardClient(delay=0, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))


async def fetch(module, body, company=None):
    async with serving(body) as client:
        return await module.fetch_board(client, company or COMPANIES[module], set())


def ats(module) -> str:
    return COMPANIES[module]["ats"]


@pytest.mark.parametrize("module", ADAPTERS)
async def test_parses_fixture(module):
    result = await fetch(module, fixture(f"{ats(module)}.json"))
    assert result.complete
    assert len(result.drafts) == 3 == len(result.seen_ids)
    draft = result.drafts[0]
    for field, value in EXPECTED[module].items():
        assert getattr(draft, field) == value, field
    assert draft.source == ats(module)
    assert draft.description_status == "Complete"
    assert draft.raw_description and draft.normalized_description
    assert "<" not in draft.normalized_description
    assert {d.source_job_id for d in result.drafts} == result.seen_ids


async def test_greenhouse_escaped_content_becomes_plain_text():
    body = fixture("greenhouse.json")
    body["jobs"][0]["content"] = "&lt;p&gt;We cannot &lt;b&gt;sponsor&lt;/b&gt; visas&lt;/p&gt;"
    draft = (await fetch(greenhouse, body)).drafts[0]
    assert draft.normalized_description == "We cannot sponsor visas"
    evidence = classify(draft.normalized_description, draft.institution).as_dict()["evidence"]
    assert evidence and evidence in draft.normalized_description


@pytest.mark.parametrize("module", ADAPTERS)
async def test_empty_board_is_complete_with_no_jobs(module):
    result = await fetch(module, fixture(f"{ats(module)}_empty.json"))
    assert result.complete and result.drafts == [] and result.seen_ids == set()


@pytest.mark.parametrize("module", ADAPTERS)
async def test_changed_format_raises_parse_error(module):
    with pytest.raises(ParseError):
        await fetch(module, fixture(f"{ats(module)}_changed.json"))


@pytest.mark.parametrize("module", ADAPTERS)
async def test_job_without_id_raises_parse_error(module):
    body = fixture(f"{ats(module)}.json")
    jobs = body if isinstance(body, list) else body["jobs"]
    del jobs[0]["id"]
    with pytest.raises(ParseError):
        await fetch(module, body)


async def test_ashby_skips_unlisted():
    body = fixture("ashby.json")
    body["jobs"][0]["isListed"] = False
    result = await fetch(ashby, body)
    assert len(result.drafts) == 2
    assert EXPECTED[ashby]["source_job_id"] not in result.seen_ids


async def test_ashby_location_includes_secondary_locations():
    draft = (await fetch(ashby, fixture("ashby.json"))).drafts[0]
    assert draft.location.startswith("New York, NY (HQ)")
    assert "Remote (US)" in draft.location


async def test_lever_description_includes_lists_and_additional():
    draft = (await fetch(lever, fixture("lever.json"))).drafts[0]
    assert "What You'll Do" in draft.normalized_description
    assert "Spotify is an equal opportunity" in draft.normalized_description


async def test_lever_location_lists_every_location():
    draft = (await fetch(lever, fixture("lever.json"))).drafts[0]
    assert draft.location == "Stockholm / London"


@pytest.mark.parametrize("module", ADAPTERS)
async def test_missing_dates_give_none_not_crash(module):
    body = fixture(f"{ats(module)}.json")
    job = (body if isinstance(body, list) else body["jobs"])[0]
    for key in ("first_published", "updated_at", "createdAt", "publishedAt"):
        job.pop(key, None)
    assert (await fetch(module, body)).drafts[0].posted_date is None


async def test_same_ats_id_in_two_companies_keeps_distinct_rows(tmp_path):
    # Review focus 1: identical job ids on two boards must not overwrite each other.
    db = Database(tmp_path / "jobs.sqlite3")
    for slug in ("stripe", "stripe-eu"):
        db.upsert_company(BoardRef("greenhouse", slug), None, "manual")
    body = fixture("greenhouse.json")
    for company in db.companies():
        result = await fetch(greenhouse, copy.deepcopy(body), company)
        for draft in result.drafts:
            db.save_board_job(company["id"], draft)
    assert db.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 6


@pytest.mark.parametrize("module,key", [(greenhouse, "absolute_url"), (lever, "hostedUrl"), (lever, "applyUrl"),
                                        (ashby, "jobUrl"), (ashby, "applyUrl")])
async def test_non_http_urls_from_boards_are_never_used(module, key):
    # Board responses are untrusted: a javascript: URL would run in the dashboard when clicked.
    body = fixture(f"{ats(module)}.json")
    (body if isinstance(body, list) else body["jobs"])[0][key] = "javascript:alert(1)"
    draft = (await fetch(module, body)).drafts[0]
    assert draft.source_url.startswith("https://")
    assert draft.apply_url is None or draft.apply_url.startswith("https://")
