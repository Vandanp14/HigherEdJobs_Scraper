#!/usr/bin/env python3
"""Local database housekeeping. It never changes data/browser-state.json."""

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "jobs.sqlite3"
STATE = ROOT / "data" / "browser-state.json"


def size(path: Path) -> str:
    return f"{path.stat().st_size / 1024 / 1024:.2f} MB" if path.exists() else "0 MB"


def main():
    parser = argparse.ArgumentParser(description="Manage local job data without changing the browser session.")
    parser.add_argument("command", choices=("status", "compact", "clear-jobs"))
    command = parser.parse_args().command
    if not DATABASE.exists():
        raise SystemExit("No jobs database exists yet.")
    connection = sqlite3.connect(DATABASE)
    if command == "status":
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        raw = connection.execute("SELECT COUNT(*) FROM jobs WHERE raw_description IS NOT NULL").fetchone()[0]
        print(f"Database: {size(DATABASE)} · {jobs} jobs · {raw} raw descriptions")
        print(f"Browser session: {size(STATE)} · {STATE}")
        return
    if command == "compact":
        affected = connection.execute("UPDATE jobs SET raw_description=NULL WHERE raw_description IS NOT NULL").rowcount
        connection.commit()
        connection.execute("VACUUM")
        print(f"Removed original page HTML from {affected} jobs. Database is now {size(DATABASE)}.")
    else:
        connection.executescript("DELETE FROM scrape_runs; DELETE FROM jobs;")
        connection.commit()
        connection.execute("VACUUM")
        print(f"Cleared job data and run history. Browser session remains: {STATE}")


if __name__ == "__main__":
    main()
