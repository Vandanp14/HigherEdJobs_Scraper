"""Greenhouse public job board API: one request returns every job with its description."""
from ..early_career import title_candidate
from .adapters import BoardFetch, company_name, draft, job_id, jobs_list, required, utc_date

ATS = "greenhouse"


async def fetch_board(client, company: dict, known_ids: set[str]) -> BoardFetch:
    body = await client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs?content=true", key=ATS)
    result = BoardFetch()
    for job in jobs_list(body, "jobs", ATS):
        ats_id, title = required(job, ("id", "title"), ATS)
        result.seen_ids.add(job_id(company, ats_id))
        if not title_candidate(title):
            continue  # Never kept, so its description is not parsed.
        # Built, not absolute_url: that can be a shared company page, and job URLs must be unique.
        item = draft(
            company, ATS, ats_id, title, f"https://job-boards.greenhouse.io/{company['slug']}/jobs/{ats_id}",
            job.get("content"), apply_url=job.get("absolute_url"),
            institution=company_name(company, job.get("company_name")),
            location=(job.get("location") or {}).get("name"),
            posted_date=utc_date(job.get("first_published")) or utc_date(job.get("updated_at")),
        )
        result.drafts.append(item)
    return result
