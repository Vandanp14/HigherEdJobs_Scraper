"""SmartRecruiters public postings API. List pages carry no description, so each job that could be
kept and is not saved yet needs one more request."""
from datetime import date, timedelta

from ..early_career import location_allowed, title_candidate
from ..parser import JobDraft, ParseError
from .adapters import BoardFetch, company_name, draft, job_id, utc_date
from .client import BoardError, BoardMissing

ATS = "smartrecruiters"
PAGE_SIZE = 100
SECTIONS = ("jobDescription", "qualifications", "additionalInformation")


def _description(info: dict) -> str:
    sections = (info.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in SECTIONS:
        section = sections.get(key) or {}
        if section.get("text"):
            parts.append(f"<h3>{section.get('title') or ''}</h3>{section['text']}")
    return "".join(parts)


def _location(item: dict) -> str | None:
    return (item.get("location") or {}).get("fullLocation") or None


async def fetch_board(client, company: dict, known_ids: set[str], max_age_days: int = 0) -> BoardFetch:
    base = f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings"
    found: dict[str, dict] = {}
    result, offset = BoardFetch(), 0
    while True:
        try:
            body = await client.get_json(f"{base}?limit={PAGE_SIZE}&offset={offset}", key=ATS)
        except (BoardError, BoardMissing):
            if offset == 0:
                raise  # Nothing read at all: the board failed, not one page.
            result.complete = False
            break
        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, list) or not all(isinstance(item, dict) and item.get("id") for item in content):
            raise ParseError("smartrecruiters list response format changed: no content with ids")
        for item in content:
            found.setdefault(str(item["id"]), item)
        offset += PAGE_SIZE
        if not content or offset >= int(body.get("totalFound") or 0):
            break
    oldest = (date.today() - timedelta(days=max_age_days)).isoformat() if max_age_days else None
    for ats_id, item in found.items():
        source_job_id = job_id(company, ats_id)
        result.seen_ids.add(source_job_id)
        title = " ".join((item.get("name") or "").split())
        if source_job_id in known_ids or not title_candidate(title) or not location_allowed(_location(item)):
            continue
        released = utc_date(item.get("releasedDate"))
        if oldest and released and released < oldest:
            continue  # Too old to keep, so its detail is not requested.
        fallback = f"https://jobs.smartrecruiters.com/{company['slug']}/{ats_id}"
        try:
            info = await client.get_json(f"{base}/{ats_id}", key=ATS)
            if not isinstance(info, dict):
                raise BoardError("unreadable posting")
        except (BoardError, BoardMissing):
            result.drafts.append(JobDraft(source=ATS, source_job_id=source_job_id, source_url=fallback, title=title,
                                          location=_location(item), institution=company_name(company), description_status="Failed"))
            continue
        result.drafts.append(draft(
            company, ATS, ats_id, info.get("name") or title, info.get("postingUrl"), _description(info),
            fallback_url=fallback, apply_url=info.get("applyUrl"),
            institution=company_name(company, (info.get("company") or {}).get("name")),
            location=_location(info) or _location(item), posted_date=utc_date(info.get("releasedDate") or item.get("releasedDate")),
        ))
    return result
