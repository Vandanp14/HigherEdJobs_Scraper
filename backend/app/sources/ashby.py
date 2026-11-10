"""Ashby public job board API: one request returns every listed job with its description."""
from ..early_career import title_candidate
from .adapters import BoardFetch, company_name, draft, job_id, jobs_list, required, utc_date

ATS = "ashby"


async def fetch_board(client, company: dict, known_ids: set[str]) -> BoardFetch:
    body = await client.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}", key=ATS)
    result = BoardFetch()
    for job in jobs_list(body, "jobs", ATS):
        ats_id, title = required(job, ("id", "title"), ATS)
        if job.get("isListed") is False:
            continue
        result.seen_ids.add(job_id(company, ats_id))
        if not title_candidate(title):
            continue  # Never kept, so its description is not parsed.
        secondary = [place.get("location") for place in job.get("secondaryLocations") or [] if isinstance(place, dict)]
        item = draft(
            company, ATS, ats_id, title, job.get("jobUrl"), job.get("descriptionHtml"), apply_url=job.get("applyUrl"),
            fallback_url=f"https://jobs.ashbyhq.com/{company['slug']}/{ats_id}",
            institution=company_name(company), location=" / ".join(filter(None, [job.get("location"), *secondary])) or None,
            posted_date=utc_date(job.get("publishedAt")),
        )
        result.drafts.append(item)
    return result
