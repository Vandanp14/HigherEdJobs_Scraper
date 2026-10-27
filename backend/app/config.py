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
    # HigherEdJobs listings posted longer ago than this are skipped, and a search stops paging once a
    # whole results page is older. 0 means no limit.
    max_age_days: int = max(0, int(os.getenv("HEJ_MAX_AGE_DAYS", "14")))
    state_path: Path = ROOT / "data/browser-state.json"
    verification_timeout_s: float = float(os.getenv("HEJ_VERIFICATION_TIMEOUT", "300"))
    storage_state: str | None = os.getenv("HEJ_STORAGE_STATE") or (str(ROOT / "data/browser-state.json") if (ROOT / "data/browser-state.json").exists() else None)


# (id, name, keyword query, HigherEdJobs JobCat ids). Quoted phrases are exact on HigherEdJobs and
# wildcards do not work inside quotes, so each group lists the word variants it should also match.
# Category groups leave the keyword empty and use HigherEdJobs' own job categories, which catch
# listings whose text never names the role (for example a "Digital Content Specialist" filed under
# Web Developer).
SEARCH_GROUPS = [
    ("data", "Data & Analytics", '"data analyst" OR "data analysts" OR "data analytics" OR "data analysis" OR "business intelligence" OR "BI analyst" OR "BI developer"', ""),
    ("software", "Software Development", '"software developer" OR "software development" OR "software engineer" OR "application developer" OR "applications developer" OR "programmer analyst" OR "programmer/analyst"', ""),
    ("web", "Web Development", '"web developer" OR "web development" OR "website developer" OR "web programmer" OR "web application" OR "web applications" OR "full stack" OR "front-end developer" OR "frontend developer" OR "front end developer"', ""),
    ("database", "Database", '"database administrator" OR "database administration" OR "database analyst" OR "database developer" OR "database engineer"', ""),
    ("systems", "Systems & Applications", '"systems analyst" OR "system analyst" OR "business systems analyst" OR "applications analyst" OR "application analyst"', ""),
    ("cloud", "Cloud & DevOps", '"cloud engineer" OR "cloud engineering" OR "cloud architect" OR AWS OR Azure OR DevOps', ""),
    ("research", "Research Computing", '"research programmer" OR "research software" OR "research computing" OR "scientific programmer"', ""),
    ("it", "University IT Titles", '"programmer analyst" OR "applications analyst" OR "systems analyst"', ""),
    ("cat_web", "Category: Web Developer", "", "160"),
    ("cat_software", "Category: Software Engineer/Programmer", "", "159"),
    ("cat_database", "Category: Database Administrator", "", "211"),
    ("cat_other_it", "Category: Other IT", "", "162"),
]

SPONSORSHIP_STATUSES = [
    "Not Worth It", "Likely No Sponsorship", "Unsure - Review",
    "No Mention Found", "Sponsorship Possible",
]
APPLICATION_STATUSES = ["New", "Opened", "Applied", "Skipped"]
