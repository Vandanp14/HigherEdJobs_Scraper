import os
import tempfile

# Importing backend.app.main opens Settings().database and runs startup work on it. Point it at a
# throwaway file before any test imports the app, so tests never touch data/jobs.sqlite3.
_scratch = tempfile.mkdtemp(prefix="hej-tests-")
os.environ["HEJ_DATABASE"] = os.path.join(_scratch, "jobs.sqlite3")
# Tests never read the personal resume in data/; fit tests pass their own synthetic resume file.
os.environ["HEJ_RESUME"] = os.path.join(_scratch, "no-resume.json")
