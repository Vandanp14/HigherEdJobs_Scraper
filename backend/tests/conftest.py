import os
import tempfile

# Importing backend.app.main opens Settings().database and runs startup work on it. Point it at a
# throwaway file before any test imports the app, so tests never touch data/jobs.sqlite3.
os.environ["HEJ_DATABASE"] = os.path.join(tempfile.mkdtemp(prefix="hej-tests-"), "jobs.sqlite3")
