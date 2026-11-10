"""SmartRecruiters adapter against fake responses built from real LLNL responses saved on 2026-11-10."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from backend.app.parser import ParseError
from backend.app.sources import smartrecruiters
from backend.app.sources.client import BoardClient

FIXTURES = Path(__file__).parent / "fixtures" / "boards"
LIST = json.loads((FIXTURES / "smartrecruiters_list.json").read_text())
DETAIL = json.loads((FIXTURES / "smartrecruiters_detail.json").read_text())
COMPANY = {"id": 1, "ats": "smartrecruiters", "slug": "Acme", "host": "", "site": "", "name": None}


def posting(number, title, city="Austin, TX, United States"):
    item = copy.deepcopy(LIST["content"][0])
    item.update(id=str(number), name=title)
    item["location"] = {"fullLocation": city}
    return item


class FakeSmartRecruiters:
    def __init__(self, postings, fail_offsets=(), fail_details=(), list_body=None):
        self.postings, self.fail_offsets, self.fail_details = postings, set(fail_offsets), set(fail_details)
        self.list_body, self.details, self.offsets = list_body, [], []

    def __call__(self, request: httpx.Request):
        path = request.url.path
        if path == "/v1/companies/Acme/postings":
            if self.list_body is not None:
                return httpx.Response(200, json=self.list_body)
            offset, limit = int(request.url.params["offset"]), int(request.url.params["limit"])
            self.offsets.append(offset)
            if offset in self.fail_offsets:
                return httpx.Response(500)
            return httpx.Response(200, json={"offset": offset, "limit": limit, "totalFound": len(self.postings),
                                             "content": self.postings[offset:offset + limit]})
        if path.startswith("/v1/companies/Acme/postings/"):
            number = path.rsplit("/", 1)[-1]
            self.details.append(number)
            if number in self.fail_details:
                return httpx.Response(500)
            detail = copy.deepcopy(DETAIL)
            detail.update(id=number, postingUrl=f"https://jobs.smartrecruiters.com/Acme/{number}-role")
            return httpx.Response(200, json=detail)
        return httpx.Response(404)


async def fetch(fake, known=frozenset()):
    async with BoardClient(delay=0, transport=httpx.MockTransport(fake)) as client:
        return await smartrecruiters.fetch_board(client, COMPANY, set(known))


async def test_parses_real_detail_fields():
    result = await fetch(FakeSmartRecruiters([posting(1, "Software Engineer I")]))
    draft = result.drafts[0]
    assert draft.source == "smartrecruiters" and draft.source_job_id == "Acme:1"
    assert draft.source_url == "https://jobs.smartrecruiters.com/Acme/1-role"
    assert draft.apply_url.startswith("https://jobs.smartrecruiters.com/")
    assert draft.posted_date == "2026-11-10"
    assert draft.institution == "LLNL"
    assert draft.location == "Livermore, CA, United States"
    assert draft.description_status == "Complete" and "<" not in draft.normalized_description
    assert result.complete


async def test_pages_by_offset_until_total():
    postings = [posting(n, f"Account Executive {n}") for n in range(230)]
    fake = FakeSmartRecruiters(postings)
    result = await fetch(fake)
    assert fake.offsets == [0, 100, 200]
    assert len(result.seen_ids) == 230


async def test_details_only_for_title_candidates_in_the_us():
    fake = FakeSmartRecruiters([posting(1, "Software Engineer"), posting(2, "Senior Software Engineer"),
                                posting(3, "Software Engineer I", "London, United Kingdom")])
    result = await fetch(fake)
    assert fake.details == ["1"]
    assert len(result.seen_ids) == 3


async def test_known_ids_skip_detail_but_count_as_seen():
    fake = FakeSmartRecruiters([posting(1, "Software Engineer I")])
    result = await fetch(fake, known={"Acme:1"})
    assert fake.details == [] and result.drafts == [] and result.seen_ids == {"Acme:1"}


async def test_failed_list_page_is_incomplete():
    fake = FakeSmartRecruiters([posting(n, f"Account Executive {n}") for n in range(150)], fail_offsets={100})
    result = await fetch(fake)
    assert not result.complete and len(result.seen_ids) == 100


async def test_first_page_failure_fails_the_board():
    with pytest.raises(Exception):
        await fetch(FakeSmartRecruiters([], fail_offsets={0}))


async def test_failed_detail_keeps_job_as_failed():
    fake = FakeSmartRecruiters([posting(1, "Software Engineer")], fail_details={"1"})
    draft = (await fetch(fake)).drafts[0]
    assert draft.description_status == "Failed" and draft.normalized_description is None
    assert draft.title == "Software Engineer"


async def test_changed_format_raises_parse_error():
    with pytest.raises(ParseError):
        await fetch(FakeSmartRecruiters([], list_body={"results": []}))


async def test_real_list_fixture_parses():
    fake = FakeSmartRecruiters([], list_body=LIST)
    result = await fetch(fake)
    # The saved postings are internships, so none is fetched in detail.
    assert len(result.seen_ids) == 3 and fake.details == []


async def test_old_postings_skip_the_detail_request():
    from datetime import date, timedelta
    old, new = posting(1, "Software Engineer I"), posting(2, "Software Engineer I")
    old["releasedDate"] = (date.today() - timedelta(days=20)).isoformat() + "T10:00:00.000Z"
    new["releasedDate"] = date.today().isoformat() + "T10:00:00.000Z"
    fake = FakeSmartRecruiters([old, new])
    async with BoardClient(delay=0, transport=httpx.MockTransport(fake)) as client:
        result = await smartrecruiters.fetch_board(client, COMPANY, set(), max_age_days=7)
    assert fake.details == ["2"]
    assert len(result.seen_ids) == 2
