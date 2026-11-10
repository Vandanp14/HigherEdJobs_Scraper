"""Run Company boards: check every enabled company's board, keep early-career jobs, and record
what failed so a failed fetch is never mistaken for an empty board."""
import asyncio
import sqlite3
import time
from datetime import date, timedelta
from functools import partial

from ..early_career import keep_job, location_allowed, title_candidate
from ..progress import elapsed, report
from . import ashby, greenhouse, lever, smartrecruiters, workday
from .client import BoardBlocked, BoardClient, BoardMissing
from .discovery import companies_stale, refresh_companies

SOURCE = "boards"
LABEL = "Boards"
ADAPTERS = {"greenhouse": greenhouse.fetch_board, "lever": lever.fetch_board, "ashby": ashby.fetch_board,
            "workday": workday.fetch_board, "smartrecruiters": smartrecruiters.fetch_board}
# Workday tenants are separate hosts, so one block skips one tenant; this many in a row stops Workday.
WORKDAY_BLOCK_LIMIT = 3
ERROR_LIMIT = 200


class BoardsRunner:
    def __init__(self, database, settings, client=None, adapters: dict | None = None):
        self.database, self.settings = database, settings
        self.client = client
        self.max_age_days = getattr(settings, "board_max_age_days", 0)
        # Workday and SmartRecruiters list each job's age, so old jobs skip their detail request.
        self.adapters = adapters if adapters is not None else {
            ats: partial(fetch, max_age_days=self.max_age_days) if ats in ("workday", "smartrecruiters") else fetch
            for ats, fetch in ADAPTERS.items()
        }
        self.errors: list[dict] = []
        self.unlisted_errors = 0
        self.summary = dict(companies_total=0, companies_checked=0, companies_succeeded=0, companies_failed=0,
                            companies_skipped=0, jobs_seen=0, jobs_kept=0, jobs_closed=0)
        self.new = self.updated = 0

    async def run(self, limit_per_ats: int | None = None) -> dict:
        own_client = self.client is None
        client = BoardClient(self.settings.board_delay) if own_client else self.client
        self.run_id = self.database.start_run([], source=SOURCE)
        started = time.monotonic()
        try:
            if companies_stale(self.database):
                report(LABEL, "Company list is empty or over a week old; refreshing it first")
                try:
                    found = await refresh_companies(self.database, client)
                    for error in found["errors"]:
                        self._error({"company": "discovery", **error})
                except Exception as error:
                    self._error({"company": "discovery", "error": f"Company list refresh failed: {error}"})
            queues = {ats: [] for ats in self.adapters}
            for company in self.database.companies():
                if company["ats"] in queues and (limit_per_ats is None or len(queues[company["ats"]]) < limit_per_ats):
                    queues[company["ats"]].append(company)
            self.summary["companies_total"] = sum(map(len, queues.values()))
            report(LABEL, f"Checking {self.summary['companies_total']} company boards: " + ", ".join(f"{ats} {len(q)}" for ats, q in queues.items()))
            self._progress()
            outcomes = await asyncio.gather(*(self._run_ats(client, ats, queue) for ats, queue in queues.items() if queue), return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    self._error({"error": f"An ATS stopped early: {outcome!r}"})
        except Exception as error:
            self._error({"error": f"Boards run stopped: {error!r}"})
        finally:
            if own_client:
                await client.__aexit__(None, None, None)
            errors = self.errors + ([{"error": f"{self.unlisted_errors} more errors not listed"}] if self.unlisted_errors else [])
            self.database.finish_run(self.run_id, self.summary["jobs_seen"], self.new, self.updated, errors, summary=self.summary)
            s = self.summary
            report(LABEL, f"Finished in {elapsed(time.monotonic() - started)}: {s['companies_succeeded']} boards read, "
                          f"{s['companies_failed']} failed, {s['companies_skipped']} skipped, {s['jobs_kept']} jobs kept, {s['jobs_closed']} closed")
        return self.database.latest_run(SOURCE)

    async def _run_ats(self, client, ats: str, queue: list[dict]):
        adapter, streak = self.adapters[ats], 0
        for index, company in enumerate(queue):
            name = f"{ats}/{company['slug']}"
            try:
                fetched = await adapter(client, company, self.database.known_job_ids(company["id"]))
            except BoardBlocked as blocked:
                # Never retried or worked around. The company that drew the block is recorded so it
                # moves to the back of the queue; the ones not asked stay first in line next run.
                self.database.record_company_check(company["id"], error=str(blocked))
                self._error({"company": name, "error": str(blocked)})
                if ats != "workday":
                    self.summary["companies_skipped"] += len(queue) - index
                    report(LABEL, f"{blocked}; no more {ats} requests this run")
                    return self._progress()
                streak += 1
                self.summary["companies_skipped"] += 1
                if streak >= WORKDAY_BLOCK_LIMIT:
                    self.summary["companies_skipped"] += len(queue) - index - 1
                    self._error({"error": f"Workday stopped for this run after {streak} blocked tenants in a row"})
                    report(LABEL, "Workday stopped for this run after repeated blocks")
                    return self._progress()
                self._progress()
                continue
            except Exception as error:
                self.database.record_company_check(company["id"], error=str(error), missing=isinstance(error, BoardMissing))
                self._error({"company": name, "error": str(error)})
                self.summary["companies_failed"] += 1
                self.summary["companies_checked"] += 1
                self._progress()
                continue
            streak = 0
            try:
                self._save(company, fetched)
            except Exception as error:
                # A database error (for example "database is locked") fails this company only.
                self.database.connection.rollback()
                self.database.record_company_check(company["id"], error=str(error))
                self._error({"company": name, "error": f"Saving failed: {error}"})
                self.summary["companies_failed"] += 1
            self.summary["companies_checked"] += 1
            self._progress()

    def _save(self, company: dict, fetched):
        self.summary["jobs_seen"] += len(fetched.seen_ids)
        oldest = (date.today() - timedelta(days=self.max_age_days)).isoformat() if self.max_age_days else None
        for draft in fetched.drafts:
            if oldest and draft.posted_date and draft.posted_date < oldest:
                continue  # Older than HEJ_BOARD_MAX_AGE_DAYS; undated postings are kept.
            if draft.description_status == "Failed":
                # The description could not be read, so the early-career check cannot run; keep
                # software roles anyway so the failure is visible instead of silently dropped.
                if not (title_candidate(draft.title) and location_allowed(draft.location)):
                    continue
            elif not keep_job(draft.title, draft.location, draft.normalized_description):
                continue
            try:
                _, is_new = self.database.save_board_job(company["id"], draft)
            except sqlite3.IntegrityError as error:
                self.database.connection.rollback()
                self._error({"company": f"{company['ats']}/{company['slug']}", "error": f"{draft.source_job_id} not saved: {error}"})
                continue
            self.summary["jobs_kept"] += 1
            self.new, self.updated = self.new + is_new, self.updated + (not is_new)
        self.summary["jobs_closed"] += self.database.reconcile_board(company["id"], fetched.seen_ids, fetched.complete)
        self.database.record_company_check(company["id"])
        self.summary["companies_succeeded"] += 1

    def _error(self, entry: dict):
        if len(self.errors) < ERROR_LIMIT:
            self.errors.append(entry)
        else:
            self.unlisted_errors += 1

    def _progress(self):
        self.database.update_run_progress(self.run_id, self.summary["jobs_seen"], self.new, self.updated, dict(self.summary))
