"""Run Company boards from the terminal, without the dashboard.

Usage: .venv/bin/python scripts/run-boards.py [--limit N]
--limit checks only the first N companies per ATS, for a quick real-world check. The dashboard and
./run.sh always check every company.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings  # noqa: E402
from backend.app.database import Database  # noqa: E402
from backend.app.sources.runner import BoardsRunner  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Check Company boards for early-career jobs.")
    parser.add_argument("--limit", type=int, default=None, help="companies per ATS (default: all)")
    limit = parser.parse_args().limit
    settings = Settings()
    run = asyncio.run(BoardsRunner(Database(settings.database, settings.resume), settings).run(limit_per_ats=limit))
    print(json.dumps(run["summary"], indent=2))
    for error in run["errors"][:20]:
        print("error:", error)


if __name__ == "__main__":
    main()
