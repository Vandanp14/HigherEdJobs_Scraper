"""Ashby public job board API: one request returns every listed job with its description."""
from .adapters import BoardFetch, company_name, draft, jobs_list, required, utc_date

ATS = "ashby"


async def fetch_board(client, company: dict, known_ids: set[str]) -> BoardFetch:
    body = await client.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}", key=ATS)
    result = BoardFetch()
    for job in jobs_list(body, "jobs", ATS):
        ats_id, title, url = required(job, ("id", "title", "jobUrl"), ATS)
        if job.get("isListed") is False:
            continue
        secondary = [place.get("location") for place in job.get("secondaryLocations") or [] if isinstance(place, dict)]
        item = draft(
            company, ATS, ats_id, title, url, job.get("descriptionHtml"), apply_url=job.get("applyUrl"),
            institution=company_name(company), location=" / ".join(filter(None, [job.get("location"), *secondary])) or None,
            posted_date=utc_date(job.get("publishedAt")),
        )
        result.drafts.append(item)
        result.seen_ids.add(item.source_job_id)
    return result
