"""Lever public postings API: one request returns every posting with its description."""
from .adapters import BoardFetch, company_name, draft, jobs_list, required, utc_date

ATS = "lever"


def _description(job: dict) -> str:
    parts = [job.get("description") or ""]
    for section in job.get("lists") or []:
        if isinstance(section, dict):
            parts.append(f"<h3>{section.get('text') or ''}</h3><ul>{section.get('content') or ''}</ul>")
    parts.append(job.get("additional") or "")
    return "".join(parts)


async def fetch_board(client, company: dict, known_ids: set[str]) -> BoardFetch:
    body = await client.get_json(f"https://api.lever.co/v0/postings/{company['slug']}?mode=json", key=ATS)
    result = BoardFetch()
    for job in jobs_list(body, None, ATS):
        ats_id, title = required(job, ("id", "text"), ATS)
        categories = job.get("categories") or {}
        locations = categories.get("allLocations") or [categories.get("location")]
        item = draft(
            company, ATS, ats_id, title, job.get("hostedUrl"), _description(job), apply_url=job.get("applyUrl"),
            fallback_url=f"https://jobs.lever.co/{company['slug']}/{ats_id}",
            institution=company_name(company), location=" / ".join(filter(None, locations)) or None,
            posted_date=utc_date(job.get("createdAt")),
        )
        result.drafts.append(item)
        result.seen_ids.add(item.source_job_id)
    return result
