"""Add a company's job board to Company boards by hand.

Usage: .venv/bin/python scripts/add-company.py <board-or-job-url> [company name]
Accepts Greenhouse, Lever, Ashby, SmartRecruiters and Workday URLs, for example
https://jobs.lever.co/acme or https://acme.wd5.myworkdayjobs.com/en-US/External/job/123.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings  # noqa: E402
from backend.app.database import Database  # noqa: E402
from backend.app.sources.refs import parse_board_url  # noqa: E402


def main(arguments: list[str]) -> int:
    if not arguments:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    ref = parse_board_url(arguments[0])
    if ref is None:
        print(f"Not a Greenhouse, Lever, Ashby, SmartRecruiters or Workday board URL: {arguments[0]}", file=sys.stderr)
        return 1
    name = " ".join(arguments[1:]) or None
    settings = Settings()
    added = Database(settings.database, settings.resume).upsert_company(ref, name, "manual")
    where = f"{ref.ats} board '{ref.slug}'" + (f" (site {ref.site})" if ref.site else "")
    print(f"Added {where}." if added else f"Already listed: {where}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
