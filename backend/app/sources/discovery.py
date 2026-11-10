"""Find companies' job boards from free public data: Common Crawl's URL index and the
community-maintained SimplifyJobs new-grad list. No search engine is used."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from .client import BoardBlocked, BoardClient, BoardError, BoardMissing
from .refs import parse_board_url

COMMON_CRAWL = "https://index.commoncrawl.org"
CDX_PATTERNS = (
    "job-boards.greenhouse.io/*", "boards.greenhouse.io/*", "jobs.lever.co/*", "jobs.ashbyhq.com/*",
    "*.myworkdayjobs.com", "jobs.smartrecruiters.com/*",
)
SIMPLIFY_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"
# Common Crawl's index often answers 504 under load; wait and retry before giving up on a pattern.
CDX_RETRY_WAITS = (5, 15, 45)
REFRESH_DAYS = 7


def companies_stale(database, max_age_days: int = REFRESH_DAYS) -> bool:
    """True when there are no companies, or no refresh has finished in the last `max_age_days`."""
    if not database.companies(enabled_only=False):
        return True
    run = database.latest_run("discovery")
    finished = run and run["completed_at"]
    if not finished:
        return True
    return datetime.fromisoformat(finished) < datetime.now(timezone.utc) - timedelta(days=max_age_days)


async def _cdx(client: BoardClient, url: str, as_text: bool = False):
    """One index request with retries on server errors; a 404 means no captures."""
    for attempt, wait in enumerate((*CDX_RETRY_WAITS, None)):
        try:
            return await (client.get_text(url, key="commoncrawl") if as_text else client.get_json(url, key="commoncrawl"))
        except BoardMissing:
            return "" if as_text else {"pages": 0}
        except BoardError:
            if wait is None:
                raise
            await asyncio.sleep(wait)


async def _common_crawl(client: BoardClient, save, errors: list[dict]) -> None:
    """Save boards from Common Crawl page by page, so nothing large is held in memory. A block
    stops every Common Crawl request for the run."""
    try:
        collections = await client.get_json(f"{COMMON_CRAWL}/collinfo.json", key="commoncrawl")
        index = f"{COMMON_CRAWL}/{collections[0]['id']}-index"
    except BoardBlocked as error:
        errors.append({"source": "commoncrawl", "error": str(error)})
        return
    except (BoardError, BoardMissing, KeyError, IndexError, TypeError) as error:
        errors.append({"source": "commoncrawl", "error": f"Collection list unavailable: {error}"})
        return
    for pattern in CDX_PATTERNS:
        query = f"{index}?url={pattern}&output=json&fl=url"
        try:
            pages = int((await _cdx(client, query + "&showNumPages=true")).get("pages", 0))
            for page in range(pages):
                text = await _cdx(client, f"{query}&page={page}", as_text=True)
                for line in text.splitlines():
                    if line.strip():
                        save(json.loads(line).get("url", ""), None, "commoncrawl")
                await asyncio.sleep(0)  # Let the dashboard's requests run between pages.
        except BoardBlocked as error:
            errors.append({"source": f"commoncrawl {pattern}", "error": f"{error}; no more Common Crawl requests this run"})
            return
        except (BoardError, ValueError, AttributeError) as error:
            errors.append({"source": f"commoncrawl {pattern}", "error": str(error)})


async def refresh_companies(database, client: BoardClient) -> dict:
    """Add every board found to `ats_companies`. A failed source is reported and the existing list
    is kept; companies are never removed here."""
    run_id = database.start_run([], source="discovery")
    errors: list[dict] = []
    counts = {"found": 0, "new": 0}
    seen: dict[str, set] = {"commoncrawl": set(), "simplify": set()}

    def save(url: str, name: str | None, via: str):
        ref = parse_board_url(url)
        key = ref and (ref.ats, ref.slug.lower(), ref.site.lower())
        if not ref or key in seen[via]:
            return  # Many URLs share one board; each board is written once per source.
        seen[via].add(key)
        counts["found"] += 1
        counts["new"] += database.upsert_company(ref, name, via)

    try:
        await _common_crawl(client, save, errors)
        try:
            listings = await client.get_json(SIMPLIFY_URL, key="github")
        except (BoardError, BoardBlocked, BoardMissing) as error:
            errors.append({"source": "simplify", "error": str(error)})
            listings = []
        for listing in listings if isinstance(listings, list) else []:
            if isinstance(listing, dict):
                save(str(listing.get("url") or ""), listing.get("company_name") or None, "simplify")
    finally:
        database.finish_run(run_id, counts["found"], counts["new"], 0, errors)
    return {**counts, "errors": errors}
