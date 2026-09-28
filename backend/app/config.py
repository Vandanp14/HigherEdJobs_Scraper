import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database: Path = ROOT / os.getenv("HEJ_DATABASE", "data/jobs.sqlite3")
    request_delay: float = max(0.5, float(os.getenv("HEJ_REQUEST_DELAY", "2")))
    # HigherEdJobs can invalidate a visible, manually verified session when the
    # follow-up search uses a headless browser. Default to visible operation so
    # any access check remains actionable rather than becoming silent failures.
    headless: bool = os.getenv("HEJ_HEADLESS", "false").lower() == "true"
    browser_channel: str | None = os.getenv("HEJ_BROWSER_CHANNEL") or None
    cache_hours: float = max(0, float(os.getenv("HEJ_CACHE_HOURS", "24")))
    timeout_ms: int = int(os.getenv("HEJ_TIMEOUT_MS", "30000"))
    storage_state: str | None = os.getenv("HEJ_STORAGE_STATE") or (str(ROOT / "data/browser-state.json") if (ROOT / "data/browser-state.json").exists() else None)


SEARCH_GROUPS = [
    ("data", "Data & Analytics", '"data analyst" OR "data analytics" OR "business intelligence"'),
    ("software", "Software Development", '"software developer" OR "application developer" OR "programmer analyst"'),
    ("web", "Web Development", '"web developer" OR "web application" OR "full stack"'),
    ("database", "Database", '"database administrator" OR "database analyst" OR "database developer"'),
    ("systems", "Systems & Applications", '"systems analyst" OR "business systems analyst" OR "applications analyst"'),
    ("cloud", "Cloud & DevOps", '"cloud engineer" OR AWS OR DevOps'),
    ("research", "Research Computing", '"research programmer" OR "research software" OR "research computing"'),
    ("it", "University IT Titles", '"programmer analyst" OR "applications analyst" OR "systems analyst"'),
]

SPONSORSHIP_STATUSES = [
    "Not Worth It", "Likely No Sponsorship", "Unsure - Review",
    "No Mention Found", "Sponsorship Possible",
]
APPLICATION_STATUSES = ["New", "Opened", "Applied", "Skipped"]
