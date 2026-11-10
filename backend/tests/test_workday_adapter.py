"""Workday adapter against fake responses built from real NVIDIA responses saved on 2026-11-09."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.app.database import Database
from backend.app.early_career import WORKDAY_SEARCH_TERMS
from backend.app.parser import ParseError
from backend.app.sources import workday
from backend.app.sources.client import BoardClient
from backend.app.sources.refs import BoardRef
from backend.app.sources.runner import BoardsRunner

FIXTURES = Path(__file__).parent / "fixtures" / "boards"
HOST = "acme.wd5.myworkdayjobs.com"
COMPANY = {"id": 1, "ats": "workday", "slug": "acme", "host": HOST, "site": "External", "name": "Acme"}
DETAIL = json.loads((FIXTURES / "workday_detail.json").read_text())
LIST = json.loads((FIXTURES / "workday_list.json").read_text())


def posting(title, path, location="Austin, TX"):
    return {"title": title, "externalPath": path, "locationsText": location, "postedOn": "Posted Today"}


class FakeWorkday:
    """Serves list pages per search term and details per path; records what was asked for."""

    def __init__(self, postings_by_term, page_size=20, fail_pages=(), fail_details=(), later_total=0):
        self.postings_by_term, self.page_size = postings_by_term, page_size
        self.fail_pages, self.fail_details, self.later_total = set(fail_pages), set(fail_details), later_total
        self.details, self.pages = [], []

    def __call__(self, request: httpx.Request):
        path = request.url.path
        prefix = "/wday/cxs/acme/External"
        if request.method == "POST" and path == prefix + "/jobs":
            body = json.loads(request.content)
            term, offset = body["searchText"], body["offset"]
            self.pages.append((term, offset))
            if (term, offset) in self.fail_pages:
                return httpx.Response(500)
            postings = self.postings_by_term.get(term, [])
            page = postings[offset:offset + body["limit"]]
            total = len(postings) if offset == 0 else self.later_total  # Workday reports 0 after page 1
            return httpx.Response(200, json={"total": total, "jobPostings": page})
        if request.method == "GET" and path.startswith(prefix + "/job/"):
            job_path = path[len(prefix):]
            self.details.append(job_path)
            if job_path in self.fail_details:
                return httpx.Response(500)
            detail = copy.deepcopy(DETAIL)
            info = detail["jobPostingInfo"]
            info["title"] = job_path.rsplit("/", 1)[-1].replace("-", " ")
            info["externalUrl"] = f"https://{HOST}/External{job_path}"
            info["location"] = "Austin, TX"
            return httpx.Response(200, json=detail)
        return httpx.Response(404)


async def fetch(fake, known=frozenset(), company=COMPANY):
    async with BoardClient(delay=0, transport=httpx.MockTransport(fake)) as client:
        return await workday.fetch_board(client, company, set(known))


def sid(path, company=COMPANY):
    return f"{company['slug']}/{company['site']}:{path}"


async def test_parses_real_detail_fields():
    fake = FakeWorkday({"software engineer": [posting("Software Engineer I", "/job/Austin/Software-Engineer-I_R1")]})
    result = await fetch(fake)
    draft = result.drafts[0]
    assert draft.source == "workday"
    assert draft.source_job_id == sid("/job/Austin/Software-Engineer-I_R1")
    assert draft.source_url == f"https://{HOST}/External/job/Austin/Software-Engineer-I_R1"
    assert draft.apply_url == draft.source_url
    assert draft.posted_date == DETAIL["jobPostingInfo"]["startDate"]
    assert draft.description_status == "Complete" and "<" not in draft.normalized_description
    assert draft.institution == "Acme"
    assert result.complete


async def test_pages_all_terms_and_dedupes_paths():
    shared = posting("Software Engineer I", "/job/A/Shared_R1")
    many = [posting(f"Account Executive {n}", f"/job/A/AE_{n}") for n in range(45)]
    fake = FakeWorkday({"software engineer": [shared, *many], "software developer": [shared]})
    result = await fetch(fake)
    assert {term for term, _ in fake.pages} == set(WORKDAY_SEARCH_TERMS)
    assert [offset for term, offset in fake.pages if term == "software engineer"] == [0, 20, 40]
    assert len(result.seen_ids) == 46
    assert fake.details.count("/job/A/Shared_R1") == 1


async def test_later_page_total_zero_does_not_stop_paging():
    many = [posting(f"Account Executive {n}", f"/job/A/AE_{n}") for n in range(25)]
    fake = FakeWorkday({"software engineer": many})
    result = await fetch(fake)
    assert len(result.seen_ids) == 25


async def test_details_only_for_title_candidates():
    fake = FakeWorkday({"software engineer": [
        posting("Software Engineer", "/job/A/SE_R1"),
        posting("Senior Software Engineer", "/job/A/SSE_R2"),
        posting("Account Executive", "/job/A/AE_R3"),
    ]})
    result = await fetch(fake)
    assert fake.details == ["/job/A/SE_R1"]
    assert len(result.seen_ids) == 3
    assert [draft.source_job_id for draft in result.drafts] == [sid("/job/A/SE_R1")]


async def test_details_skipped_outside_the_us():
    fake = FakeWorkday({"software engineer": [posting("Software Engineer I", "/job/IL/SE_R1", "Israel, Yokneam")]})
    result = await fetch(fake)
    assert fake.details == [] and result.drafts == []
    assert result.seen_ids == {sid("/job/IL/SE_R1")}


async def test_known_ids_skip_detail_but_count_as_seen():
    fake = FakeWorkday({"software engineer": [posting("Software Engineer I", "/job/A/SE_R1")]})
    result = await fetch(fake, known={sid("/job/A/SE_R1")})
    assert fake.details == [] and result.drafts == []
    assert result.seen_ids == {sid("/job/A/SE_R1")}


async def test_failed_list_page_is_incomplete():
    many = [posting(f"Account Executive {n}", f"/job/A/AE_{n}") for n in range(25)]
    fake = FakeWorkday({"software engineer": many}, fail_pages={("software engineer", 20)})
    result = await fetch(fake)
    assert not result.complete
    assert len(result.seen_ids) == 20


async def test_first_page_failure_fails_the_board():
    fake = FakeWorkday({}, fail_pages={("software engineer", 0)})
    with pytest.raises(Exception):
        await fetch(fake)


async def test_failed_detail_keeps_job_as_failed():
    fake = FakeWorkday({"software engineer": [posting("Software Engineer", "/job/A/SE_R1")]}, fail_details={"/job/A/SE_R1"})
    result = await fetch(fake)
    draft = result.drafts[0]
    assert draft.description_status == "Failed" and draft.normalized_description is None
    assert draft.title == "Software Engineer" and draft.location == "Austin, TX"
    assert result.complete


async def test_same_path_in_two_tenants_gets_distinct_ids():
    other = {**COMPANY, "id": 2, "slug": "beta", "host": "beta.wd1.myworkdayjobs.com"}
    assert sid("/job/A/SE_R1") != sid("/job/A/SE_R1", other)


async def test_changed_format_raises_parse_error():
    def changed(request):
        return httpx.Response(200, json={"total": 1, "results": []})
    with pytest.raises(ParseError):
        await fetch(changed)


async def test_real_list_fixture_parses():
    fake = FakeWorkday({"software engineer": LIST["jobPostings"]})
    result = await fetch(fake)
    # The saved postings are in Israel, so they are seen but never fetched in detail.
    assert len(result.seen_ids) == len(LIST["jobPostings"]) and fake.details == []


async def test_runner_saves_failed_detail_with_failed_status(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.finish_run(db.start_run([], source="discovery"), 0, 0, 0, [])
    db.upsert_company(BoardRef("workday", "acme", HOST, "External"), "Acme", "manual")
    fake = FakeWorkday({"software engineer": [posting("Software Engineer", "/job/A/SE_R1")]}, fail_details={"/job/A/SE_R1"})
    async with BoardClient(delay=0, transport=httpx.MockTransport(fake)) as client:
        await BoardsRunner(db, SimpleNamespace(board_delay=0), client=client, adapters={"workday": workday.fetch_board}).run()
    row = db.connection.execute("SELECT description_status, title FROM jobs").fetchone()
    assert tuple(row) == ("Failed", "Software Engineer")
    status = db.jobs(source="workday", days="all")["items"][0]["sponsorship_status"]
    assert status == "Unavailable"


async def test_non_http_external_url_falls_back_to_built_url():
    fake = FakeWorkday({"software engineer": [posting("Software Engineer I", "/job/A/SE_R1")]})
    original = fake.__call__

    def evil(request):
        response = original(request)
        if request.method == "GET":
            body = response.json()
            body["jobPostingInfo"]["externalUrl"] = "javascript:alert(1)"
            return httpx.Response(200, json=body)
        return response

    draft = (await fetch(evil)).drafts[0]
    assert draft.source_url == draft.apply_url == f"https://{HOST}/External/job/A/SE_R1"


async def test_entries_without_a_path_are_skipped_not_a_format_change():
    # Seen live (Leidos, 2026-11-10): a page can list {"bulletFields": ["R-00195910"]} with no path or title.
    fake = FakeWorkday({"software engineer": [{"bulletFields": ["R-00195910"]}, posting("Software Engineer I", "/job/A/SE_R1")]})
    result = await fetch(fake)
    assert result.seen_ids == {sid("/job/A/SE_R1")}
    assert result.complete


async def test_page_of_only_unusable_entries_is_a_format_change():
    with pytest.raises(ParseError):
        await fetch(FakeWorkday({"software engineer": [{"bulletFields": ["R-1"]}, {"bulletFields": ["R-2"]}]}))


@pytest.mark.parametrize("posted_on,days", [("Posted Today", 0), ("Posted Yesterday", 1), ("Posted 5 Days Ago", 5),
                                            ("Posted 30+ Days Ago", 30), ("", None), ("Recently", None)])
def test_posted_on_is_read_as_days(posted_on, days):
    assert workday.posted_days(posted_on) == days


async def test_old_postings_skip_the_detail_request():
    old = posting("Software Engineer I", "/job/A/Old_R1"); old["postedOn"] = "Posted 30+ Days Ago"
    new = posting("Software Engineer I", "/job/A/New_R2"); new["postedOn"] = "Posted 3 Days Ago"
    unknown = posting("Software Engineer I", "/job/A/Unknown_R3"); unknown["postedOn"] = ""
    fake = FakeWorkday({"software engineer": [old, new, unknown]})
    async with BoardClient(delay=0, transport=httpx.MockTransport(fake)) as client:
        result = await workday.fetch_board(client, COMPANY, set(), max_age_days=7)
    assert fake.details == ["/job/A/New_R2", "/job/A/Unknown_R3"]
    assert len(result.seen_ids) == 3
