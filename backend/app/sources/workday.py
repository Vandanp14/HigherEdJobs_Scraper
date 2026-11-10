"""Workday career sites. The JSON endpoint behind each site is unofficial: list pages are searched
server-side per term, and a job's description needs one more request, made only for jobs that
could be kept and are not saved yet."""
from ..early_career import WORKDAY_SEARCH_TERMS, location_allowed, title_candidate
from ..parser import JobDraft, ParseError
from .adapters import BoardFetch, company_name, draft, safe_url, utc_date
from .client import BoardError, BoardMissing

ATS = "workday"
PAGE_SIZE = 20


def _postings(body) -> list[dict]:
    """Usable postings on one list page. Workday sometimes lists an entry with only `bulletFields`
    and no path; it cannot be opened, so it is skipped. A page with no usable entry at all means
    the format changed."""
    postings = body.get("jobPostings") if isinstance(body, dict) else None
    if not isinstance(postings, list):
        raise ParseError("workday list response format changed: no jobPostings")
    usable = [item for item in postings if isinstance(item, dict) and item.get("externalPath")]
    if postings and not usable:
        raise ParseError("workday list response format changed: no jobPostings with externalPath")
    return usable


async def fetch_board(client, company: dict, known_ids: set[str]) -> BoardFetch:
    base = f"https://{company['host']}/wday/cxs/{company['slug']}/{company['site']}"
    found: dict[str, dict] = {}
    result = BoardFetch()
    for term in WORKDAY_SEARCH_TERMS:
        offset, total = 0, None
        while True:
            try:
                body = await client.post_json(f"{base}/jobs", {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": term}, key=ATS)
            except (BoardError, BoardMissing):
                if not found and total is None and term == WORKDAY_SEARCH_TERMS[0]:
                    raise  # Nothing read at all: the board failed, not one page.
                result.complete = False
                break
            postings = _postings(body)
            if total is None:
                total = int(body.get("total") or 0)  # Later pages report 0, so only the first counts.
            for item in postings:
                found.setdefault(item["externalPath"], item)
            offset += PAGE_SIZE
            if not postings or offset >= total:
                break
    for path, item in found.items():
        source_job_id = f"{company['slug']}/{company['site']}:{path}"
        result.seen_ids.add(source_job_id)
        title, location = item.get("title") or "", item.get("locationsText")
        if source_job_id in known_ids or not title_candidate(title) or not location_allowed(location):
            continue
        url = f"https://{company['host']}/{company['site']}{path}"
        try:
            info = (await client.get_json(f"{base}{path}", key=ATS)).get("jobPostingInfo") or {}
        except (BoardError, BoardMissing, AttributeError):
            # Kept with a failed description: distinguishable from "no sponsorship mention".
            result.drafts.append(JobDraft(source=ATS, source_job_id=source_job_id, source_url=url, title=title,
                                          location=location, institution=company_name(company), description_status="Failed"))
            continue
        url = safe_url(info.get("externalUrl")) or url
        result.drafts.append(draft(
            company, ATS, path, info.get("title") or title, url, info.get("jobDescription"), apply_url=url,
            institution=company_name(company), location=info.get("location") or location,
            posted_date=utc_date(info.get("startDate")),
        ))
        result.drafts[-1].source_job_id = source_job_id
    return result
