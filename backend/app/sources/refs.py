from dataclasses import dataclass


@dataclass(frozen=True)
class BoardRef:
    """One company's public job board. `host` and `site` are used by Workday only."""
    ats: str
    slug: str
    host: str = ""
    site: str = ""
