"""Board HTTP client and free company discovery, against fake responses (no network)."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.app.database import Database
from backend.app.sources import discovery
from backend.app.sources.client import USER_AGENT, BoardBlocked, BoardClient, BoardError, BoardMissing
from backend.app.sources.refs import BoardRef


def client_for(handler) -> BoardClient:
    return BoardClient(delay=0, transport=httpx.MockTransport(handler))


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "jobs.sqlite3")


async def test_404_raises_missing():
    async with client_for(lambda request: httpx.Response(404)) as client:
        with pytest.raises(BoardMissing):
            await client.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs", key="greenhouse")


async def test_429_raises_blocked_with_retry_after():
    async with client_for(lambda request: httpx.Response(429, headers={"Retry-After": "120"})) as client:
        with pytest.raises(BoardBlocked) as blocked:
            await client.get_json("https://api.lever.co/v0/postings/x", key="lever")
    assert blocked.value.host == "api.lever.co"
    assert blocked.value.retry_after == "120"


async def test_403_raises_blocked():
    async with client_for(lambda request: httpx.Response(403)) as client:
        with pytest.raises(BoardBlocked):
            await client.post_json("https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Site/jobs", {}, key="workday")


async def test_html_on_200_raises_blocked():
    # A challenge page answers 200 with HTML; it is a block, never an empty board.
    page = httpx.Response(200, headers={"content-type": "text/html"}, text="<html>Verify you are human</html>")
    async with client_for(lambda request: page) as client:
        with pytest.raises(BoardBlocked):
            await client.get_json("https://api.ashbyhq.com/posting-api/job-board/x", key="ashby")


async def test_500_raises_board_error():
    async with client_for(lambda request: httpx.Response(500)) as client:
        with pytest.raises(BoardError):
            await client.get_json("https://api.ashbyhq.com/posting-api/job-board/x", key="ashby")


async def test_network_failure_raises_board_error():
    def fail(request):
        raise httpx.ConnectError("offline")
    async with client_for(fail) as client:
        with pytest.raises(BoardError):
            await client.get_json("https://api.ashbyhq.com/posting-api/job-board/x", key="ashby")


async def test_user_agent_is_generic():
    seen = []
    async with client_for(lambda request: seen.append(request.headers["user-agent"]) or httpx.Response(200, json={})) as client:
        await client.get_json("https://api.lever.co/v0/postings/x", key="lever")
    assert seen == [USER_AGENT] == ["job-board-reader/1.0"]


async def test_json_sent_as_plain_text_still_parses():
    # raw.githubusercontent.com serves JSON as text/plain.
    response = httpx.Response(200, headers={"content-type": "text/plain"}, text='[{"url": "x"}]')
    async with client_for(lambda request: response) as client:
        assert await client.get_json("https://raw.githubusercontent.com/x", key="github") == [{"url": "x"}]


CDX_ROWS = {
    "job-boards.greenhouse.io/*": ["https://job-boards.greenhouse.io/stripe/jobs/1", "https://job-boards.greenhouse.io/"],
    "jobs.lever.co/*": ["https://jobs.lever.co/spotify/abc", "https://jobs.lever.co/spotify/def"],
}
SIMPLIFY = [
    {"company_name": "Ramp", "url": "https://jobs.ashbyhq.com/ramp/1", "active": False},
    {"company_name": "Stripe", "url": "https://boards.greenhouse.io/stripe/jobs/9", "active": True},
    {"company_name": "Elsewhere", "url": "https://example.com/careers", "active": True},
]


def fake_web(cdx_status=200, simplify_status=200):
    def handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith("collinfo.json"):
            return httpx.Response(200, json=[{"id": "CC-MAIN-2026-43"}, {"id": "CC-MAIN-2026-38"}])
        if "index.commoncrawl.org/CC-MAIN-2026-43-index" in url:
            if cdx_status != 200:
                return httpx.Response(cdx_status)
            pattern = request.url.params["url"]
            rows = CDX_ROWS.get(pattern)
            if rows is None:
                return httpx.Response(404, text="No Captures found")
            if request.url.params.get("showNumPages"):
                return httpx.Response(200, json={"pages": 1})
            return httpx.Response(200, text="\n".join(json.dumps({"url": row}) for row in rows))
        if "raw.githubusercontent.com" in url:
            return httpx.Response(simplify_status, json=SIMPLIFY) if simplify_status == 200 else httpx.Response(simplify_status)
        return httpx.Response(599)
    return handler


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(discovery, "CDX_RETRY_WAITS", (0, 0, 0))


async def test_refresh_merges_both_sources_and_names_from_simplify(db):
    async with client_for(fake_web()) as client:
        result = await discovery.refresh_companies(db, client)
    companies = {(c["ats"], c["slug"]): c for c in db.companies()}
    assert set(companies) == {("greenhouse", "stripe"), ("lever", "spotify"), ("ashby", "ramp")}
    assert companies[("greenhouse", "stripe")]["name"] == "Stripe"
    assert companies[("greenhouse", "stripe")]["discovered_via"] == "commoncrawl"
    assert result["new"] == 3
    assert result["errors"] == []
    run = db.latest_run("discovery")
    assert run["completed_at"] is not None and run["new_jobs"] == 3


async def test_cdx_504_retries_then_keeps_existing_list_and_reports(db):
    db.upsert_company(BoardRef("lever", "existing"), None, "manual")
    calls = []
    web = fake_web(cdx_status=504)
    def counting(request):
        calls.append(str(request.url))
        return web(request)
    async with client_for(counting) as client:
        result = await discovery.refresh_companies(db, client)
    slugs = {c["slug"] for c in db.companies()}
    assert {"existing", "ramp", "stripe"} <= slugs
    assert result["errors"]
    assert any("commoncrawl" in error["source"] for error in result["errors"])
    # First pattern: one try plus three retries before giving up on it.
    first = [url for url in calls if "job-boards.greenhouse.io" in url]
    assert len(first) == 4


async def test_simplify_failure_is_reported_and_common_crawl_still_saved(db):
    async with client_for(fake_web(simplify_status=500)) as client:
        result = await discovery.refresh_companies(db, client)
    assert {c["slug"] for c in db.companies()} == {"stripe", "spotify"}
    assert [error["source"] for error in result["errors"]] == ["simplify"]


def test_stale_when_empty_or_over_seven_days(db):
    assert discovery.companies_stale(db)
    db.upsert_company(BoardRef("lever", "acme"), None, "manual")
    assert discovery.companies_stale(db)  # no refresh has ever finished
    run_id = db.start_run([], source="discovery")
    db.finish_run(run_id, 1, 1, 0, [])
    assert not discovery.companies_stale(db)
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")
    db.connection.execute("UPDATE scrape_runs SET completed_at=? WHERE id=?", (old, run_id))
    assert discovery.companies_stale(db)
