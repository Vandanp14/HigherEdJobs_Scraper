import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class BoardRef:
    """One company's public job board. `host` and `site` are used by Workday only."""
    ats: str
    slug: str
    host: str = ""
    site: str = ""


_PATH_HOSTS = {
    "job-boards.greenhouse.io": "greenhouse",
    "boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
    "jobs.smartrecruiters.com": "smartrecruiters",
}
# First path parts that are pages of the ATS itself, not a company's board.
_NOT_SLUGS = {"embed", "api", "v1", "jobs", "job", "search", "login", "privacy", "static", "assets"}
_WORKDAY_HOST = re.compile(r"^(?P<tenant>[a-z0-9-]+)\.(?:wd\d+\.)?myworkdayjobs\.com$")
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_board_url(url: str) -> BoardRef | None:
    """The board a job or board URL belongs to, or None for anything else."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = [part for part in parts.path.split("/") if part]
    if host in _PATH_HOSTS:
        if not path or path[0].lower() in _NOT_SLUGS or not _SLUG.match(path[0]):
            return None
        return BoardRef(_PATH_HOSTS[host], path[0])
    match = _WORKDAY_HOST.match(host)
    if match:
        if path and _LOCALE.match(path[0]):
            path = path[1:]
        if not path or path[0].lower() in {"wday", "login", "job"} or not _SLUG.match(path[0]):
            return None
        return BoardRef("workday", match["tenant"], host, path[0])
    return None
