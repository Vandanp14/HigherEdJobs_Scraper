"""Print the best and worst For you matches so the fit weights can be checked against real jobs.

Usage: .venv/bin/python scripts/fit-report.py [top] [bottom]
Rescores every saved HigherEdJobs job with the current rules and resume, then prints the ranking
the For you tab shows by default (any posting date, Skipped jobs excluded).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings  # noqa: E402
from backend.app.database import Database  # noqa: E402


def line(item: dict) -> str:
    details = item["fit_details"]
    reasons = "; ".join(details.get("reasons", []))
    return (f"{item['rank_value']:>8.1f}  fit {item['fit_score'] if item['fit_score'] is not None else '-':>3}  "
            f"{item['age_days'] if item['age_days'] is not None else '?':>3}d  {item['title']} — {item['institution']}\n"
            f"{'':>26}{reasons}")


def main(top: int = 20, bottom: int = 10) -> None:
    settings = Settings()
    database = Database(settings.database, settings.resume)
    if database.resume is None:
        sys.exit(f"No readable resume at {settings.resume}")
    print(f"Rescored {database.rescore_fit()} jobs.")
    query = dict(source="higheredjobs", days="all", sort="fit", application_status="open", per_page=10_000)
    data = database.jobs(**query)
    items = data["items"]
    print(f"\nTop {top} of {data['total']}:")
    print("\n".join(line(item) for item in items[:top]))
    print(f"\nBottom {bottom}:")
    print("\n".join(line(item) for item in items[-bottom:]))


if __name__ == "__main__":
    main(*(int(value) for value in sys.argv[1:3]))
