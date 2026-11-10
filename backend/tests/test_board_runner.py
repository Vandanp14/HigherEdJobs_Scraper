"""The boards runner with fake adapters and a real temporary database."""
from types import SimpleNamespace

import pytest

from backend.app.database import Database
from backend.app.parser import JobDraft, ParseError
from backend.app.sources import runner as runner_module
from backend.app.sources.adapters import BoardFetch
from backend.app.sources.client import BoardBlocked, BoardError, BoardMissing
from backend.app.sources.refs import BoardRef
from backend.app.sources.runner import BoardsRunner

SETTINGS = SimpleNamespace(board_delay=0)
KEEP = "Software Engineer I"
DROP = "Account Executive"


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "jobs.sqlite3")
    # A finished refresh, so runs do not try to rediscover companies unless a test wants that.
    database.finish_run(database.start_run([], source="discovery"), 0, 0, 0, [])
    return database


def add(db, ats, *slugs):
    for slug in slugs:
        host = f"{slug}.wd1.myworkdayjobs.com" if ats == "workday" else ""
        db.upsert_company(BoardRef(ats, slug, host, "Site" if ats == "workday" else ""), None, "manual")


def job(company, number, title=KEEP, location="Remote", description="Open to new grads."):
    return JobDraft(
        source=company["ats"], source_job_id=f"{company['slug']}:{number}",
        source_url=f"https://{company['ats']}.example/{company['slug']}/{number}", title=title, location=location,
        raw_description=f"<p>{description}</p>", normalized_description=description, description_status="Complete",
    )


def board(*jobs_by_company, complete=True):
    """A fake adapter serving fixed jobs per slug, or raising the exception given for a slug."""
    calls = []

    async def fetch(client, company, known_ids):
        calls.append(company["slug"])
        outcome = dict(jobs_by_company).get(company["slug"], [])
        if isinstance(outcome, Exception):
            raise outcome
        drafts = [job(company, *spec) if isinstance(spec, tuple) else job(company, spec) for spec in outcome]
        return BoardFetch(drafts, {d.source_job_id for d in drafts}, complete)

    fetch.calls = calls
    return fetch


async def run(db, **adapters):
    return await BoardsRunner(db, SETTINGS, client=object(), adapters=adapters).run()


def jobs(db):
    return {row["source_job_id"]: dict(row) for row in db.connection.execute("SELECT * FROM jobs")}


async def test_only_kept_jobs_are_saved_but_all_count_as_seen(db):
    add(db, "greenhouse", "acme")
    result = await run(db, greenhouse=board(("acme", [1, (2, DROP), (3, KEEP, "London, United Kingdom")])))
    assert set(jobs(db)) == {"acme:1"}
    summary = result["summary"]
    assert (summary["jobs_seen"], summary["jobs_kept"], summary["companies_succeeded"]) == (3, 1, 1)
    assert result["completed_at"] is not None
    assert result["source"] == "boards"


async def test_500_keeps_jobs_active_and_records_failure(db):
    add(db, "greenhouse", "acme", "beta")
    await run(db, greenhouse=board(("acme", [1])))
    result = await run(db, greenhouse=board(("acme", BoardError("acme answered 500")), ("beta", [7])))
    saved = jobs(db)
    assert saved["acme:1"]["active"] == 1
    assert "beta:7" in saved
    acme = next(c for c in db.companies() if c["slug"] == "acme")
    assert acme["last_error"] == "acme answered 500"
    assert result["summary"]["companies_failed"] == 1
    assert result["errors"][0]["company"] == "greenhouse/acme"


async def test_429_stops_only_that_ats(db):
    add(db, "greenhouse", "acme", "beta")
    add(db, "lever", "gamma", "delta")
    gh = board(("acme", BoardBlocked("boards-api.greenhouse.io", "120", 429)), ("beta", [1]))
    lv = board(("gamma", [2]), ("delta", [3]))
    result = await run(db, greenhouse=gh, lever=lv)
    assert gh.calls == ["acme"]
    assert lv.calls == ["gamma", "delta"]
    assert result["summary"]["companies_skipped"] == 2
    checked = {c["slug"]: c for c in db.companies()}
    # The company that drew the block goes to the back of the queue; the ones never asked stay first.
    assert checked["acme"]["last_checked_at"] is not None and "blocked" in checked["acme"]["last_error"]
    assert checked["beta"]["last_checked_at"] is None
    message = result["errors"][0]["error"]
    assert "boards-api.greenhouse.io" in message and "120" in message


async def test_one_blocked_workday_tenant_does_not_stop_others(db):
    add(db, "workday", "acme", "beta", "gamma")
    wd = board(("acme", BoardBlocked("acme.wd1.myworkdayjobs.com", None, 403)), ("beta", [1]), ("gamma", [2]))
    result = await run(db, workday=wd)
    assert wd.calls == ["acme", "beta", "gamma"]
    assert result["summary"]["companies_skipped"] == 1
    assert set(jobs(db)) == {"beta:1", "gamma:2"}


async def test_three_blocked_workday_tenants_in_a_row_stop_workday(db):
    add(db, "workday", "a", "b", "c", "d", "e")
    blocked = lambda slug: (slug, BoardBlocked(f"{slug}.wd1.myworkdayjobs.com", None, 429))
    wd = board(blocked("a"), blocked("b"), blocked("c"), ("d", [1]))
    result = await run(db, workday=wd)
    assert wd.calls == ["a", "b", "c"]
    assert result["summary"]["companies_skipped"] == 5
    assert any("Workday stopped" in error["error"] for error in result["errors"])


async def test_success_resets_workday_block_streak(db):
    add(db, "workday", "a", "b", "c", "d", "e")
    blocked = lambda slug: (slug, BoardBlocked(f"{slug}.wd1.myworkdayjobs.com", None, 429))
    wd = board(blocked("a"), blocked("b"), ("c", [1]), blocked("d"), ("e", [2]))
    await run(db, workday=wd)
    assert wd.calls == ["a", "b", "c", "d", "e"]


async def test_404_counts_toward_disable(db):
    add(db, "lever", "gone")
    for _ in range(5):
        await run(db, lever=board(("gone", BoardMissing("gone answered 404"))))
    assert db.companies() == []


async def test_parse_error_is_recorded_and_closes_nothing(db):
    add(db, "ashby", "acme")
    await run(db, ashby=board(("acme", [1])))
    result = await run(db, ashby=board(("acme", ParseError("ashby board response format changed"))))
    assert jobs(db)["acme:1"]["active"] == 1
    assert result["summary"]["companies_failed"] == 1


async def test_unexpected_adapter_error_is_a_company_failure(db):
    add(db, "ashby", "acme", "beta")
    result = await run(db, ashby=board(("acme", KeyError("id")), ("beta", [1])))
    assert result["summary"]["companies_failed"] == 1
    assert "beta:1" in jobs(db)


async def test_duplicate_url_recorded_not_fatal(db):
    add(db, "greenhouse", "acme")
    add(db, "lever", "acme")
    db.upsert_job(JobDraft(source="air", source_url="https://greenhouse.example/acme/1", title="Taken"))
    result = await run(db, greenhouse=board(("acme", [1, 2])))
    assert "acme:2" in jobs(db)
    assert any("acme:1" in error["error"] for error in result["errors"])


async def test_job_missing_from_successful_fetch_closes_then_reopens(db):
    add(db, "greenhouse", "acme")
    await run(db, greenhouse=board(("acme", [1, 2])))
    result = await run(db, greenhouse=board(("acme", [1])))
    assert jobs(db)["acme:2"]["active"] == 0
    assert result["summary"]["jobs_closed"] == 1
    await run(db, greenhouse=board(("acme", [1, 2])))
    assert jobs(db)["acme:2"]["active"] == 1


async def test_incomplete_fetch_closes_nothing(db):
    add(db, "greenhouse", "acme")
    await run(db, greenhouse=board(("acme", [1, 2])))
    await run(db, greenhouse=board(("acme", [1]), complete=False))
    assert jobs(db)["acme:2"]["active"] == 1


async def test_refresh_runs_first_when_list_empty(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.sqlite3")
    called = []

    async def refresh(database, client):
        called.append(True)
        add(database, "lever", "found")
        return {"found": 1, "new": 1, "errors": []}

    monkeypatch.setattr(runner_module, "refresh_companies", refresh)
    lv = board(("found", [1]))
    await run(db, lever=lv)
    assert called and lv.calls == ["found"]


async def test_refresh_failure_does_not_stop_run_on_existing_list(db, monkeypatch):
    add(db, "lever", "acme")
    monkeypatch.setattr(runner_module, "companies_stale", lambda database: True)

    async def refresh(database, client):
        raise RuntimeError("index down")

    monkeypatch.setattr(runner_module, "refresh_companies", refresh)
    result = await run(db, lever=board(("acme", [1])))
    assert "acme:1" in jobs(db)
    assert any("index down" in error["error"] for error in result["errors"])


async def test_progress_visible_before_finish(db):
    add(db, "greenhouse", "acme", "beta")
    seen = []

    async def fetch(client, company, known_ids):
        seen.append(db.latest_run("boards"))
        return BoardFetch()

    await run(db, greenhouse=fetch)
    second = seen[1]
    assert second["completed_at"] is None
    assert second["summary"]["companies_checked"] == 1
    assert second["summary"]["companies_total"] == 2


async def test_finish_run_called_even_if_unexpected_error(db, monkeypatch):
    add(db, "greenhouse", "acme")
    monkeypatch.setattr(runner_module, "companies_stale", lambda database: (_ for _ in ()).throw(RuntimeError("boom")))
    result = await run(db, greenhouse=board(("acme", [1])))
    assert result["completed_at"] is not None
    assert any("boom" in error["error"] for error in result["errors"])


async def test_errors_capped_at_200(db):
    add(db, "lever", *[f"c{number}" for number in range(205)])
    failing = board(*[(f"c{number}", BoardError("down")) for number in range(205)])
    result = await run(db, lever=failing)
    assert len(result["errors"]) == 201
    assert result["errors"][-1] == {"error": "5 more errors not listed"}


async def test_limit_per_ats_checks_only_that_many(db):
    add(db, "lever", "a", "b", "c")
    lv = board()
    await BoardsRunner(db, SETTINGS, client=object(), adapters={"lever": lv}).run(limit_per_ats=2)
    assert lv.calls == ["a", "b"]


async def test_known_ids_passed_to_adapter(db):
    add(db, "greenhouse", "acme")
    await run(db, greenhouse=board(("acme", [1])))
    received = []

    async def fetch(client, company, known_ids):
        received.append(known_ids)
        return BoardFetch()

    await run(db, greenhouse=fetch)
    assert received == [{"acme:1"}]


async def test_a_block_does_not_starve_the_ats_on_later_runs(db):
    add(db, "lever", "html", "good")
    lv = board(("html", BoardBlocked("api.lever.co", None, None)), ("good", [1]))
    await run(db, lever=lv)
    lv2 = board(("good", [1]))
    await run(db, lever=lv2)
    assert lv2.calls[0] == "good"


async def test_a_database_error_while_saving_fails_one_company_not_the_run(db, monkeypatch):
    import sqlite3
    add(db, "greenhouse", "acme", "beta")
    add(db, "lever", "gamma")
    real = db.save_board_job

    def flaky(company_id, draft):
        if draft.source_job_id.startswith("acme:"):
            raise sqlite3.OperationalError("database is locked")
        return real(company_id, draft)

    monkeypatch.setattr(db, "save_board_job", flaky)
    result = await run(db, greenhouse=board(("acme", [1]), ("beta", [2])), lever=board(("gamma", [3])))
    assert {"beta:2", "gamma:3"} <= set(jobs(db))
    assert result["summary"]["companies_failed"] == 1
    assert result["summary"]["companies_succeeded"] == 2
    assert any("database is locked" in error["error"] for error in result["errors"])
