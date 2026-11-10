"""Pieces every board adapter shares. An adapter turns one company's board into JobDrafts."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..parser import JobDraft, ParseError, normalize_ats_description


@dataclass
class BoardFetch:
    """Jobs read from one board. `seen_ids` holds every job the board lists, kept or not, and
    `complete` is False when part of the board could not be read, so nothing is closed."""
    drafts: list[JobDraft] = field(default_factory=list)
    seen_ids: set[str] = field(default_factory=set)
    complete: bool = True


def job_id(company: dict, ats_id) -> str:
    # Prefixed with the board so the same ATS id on two boards never collides.
    return f"{company['slug']}:{ats_id}"


def company_name(company: dict, listed: str | None = None) -> str:
    return listed or company.get("name") or company["slug"].replace("-", " ").replace("_", " ").title()


def utc_date(value) -> str | None:
    """`YYYY-MM-DD` in UTC from an ISO timestamp or epoch milliseconds; None when absent or unreadable."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            moment = datetime.fromtimestamp(value / 1000, timezone.utc)
        else:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def jobs_list(body, key: str | None, ats: str) -> list[dict]:
    """The job list from a board response, or ParseError when the format changed."""
    jobs = body if key is None else (body.get(key) if isinstance(body, dict) else None)
    if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
        raise ParseError(f"{ats} board response format changed: no job list")
    return jobs


def required(job: dict, keys: tuple[str, ...], ats: str):
    missing = [key for key in keys if not job.get(key)]
    if missing:
        raise ParseError(f"{ats} job is missing {', '.join(missing)}; the board format may have changed")
    return [job[key] for key in keys]


def draft(company: dict, ats: str, ats_id, title: str, url: str, raw: str | None, **fields) -> JobDraft:
    text = normalize_ats_description(raw) if raw else None
    return JobDraft(
        source=ats, source_job_id=job_id(company, ats_id), source_url=url, title=" ".join(title.split()),
        raw_description=raw or None, normalized_description=text or None,
        description_status="Complete" if text else "Failed", **fields,
    )
