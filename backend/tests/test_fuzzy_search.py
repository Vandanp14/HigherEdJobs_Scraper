import pytest

from backend.app.database import Database
from backend.app.fuzzy import fuzzy_match
from backend.app.parser import JobDraft

TEXT = "Senior Software Developer University of Pennsylvania Philadelphia, PA"


@pytest.mark.parametrize("query", [
    "software developer",       # exact
    "developer software",       # word order
    "devloper",                 # missing letter
    "sofware",                  # missing letter
    "developre",                # swapped letters
    "softwear develper",        # two typos, one per word
    "dev",                      # partial word
    "soft dev penn",            # partial words across fields
    "pennsylvania",
    "philadelphia",
    "philadephia",              # long word, missing letter
    "pensylv",                  # typo inside a partial word
    "SENIOR",                   # case
])
def test_matches(query):
    assert fuzzy_match(query, TEXT)


@pytest.mark.parametrize("query", [
    "chemistry",
    "software chemistry",       # every word must match
    "nurse",
    "xyz",
    "data",
])
def test_rejects(query):
    assert not fuzzy_match(query, TEXT)


def test_short_words_need_exact_prefix():
    assert not fuzzy_match("sen", "Junior Developer")
    assert fuzzy_match("sen", "Senior Developer")


def test_empty_query_matches_everything():
    assert fuzzy_match("", TEXT)
    assert fuzzy_match("  ", TEXT)


def test_dashboard_search_is_fuzzy(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/1", title="Software Developer", institution="Franklin & Marshall College", location="Lancaster, PA"), "software")
    db.upsert_job(JobDraft(higheredjobs_url="https://x/2", title="Data Analyst", institution="Ohio State University", location="Columbus, OH"), "data")
    def titles(query): return {job["title"] for job in db.jobs(query=query, days="all")["items"]}
    assert titles("sofware devloper") == {"Software Developer"}
    assert titles("franklin marshal") == {"Software Developer"}
    assert titles("analist ohio") == {"Data Analyst"}
    assert titles("lancaster") == {"Software Developer"}
    assert titles("") == {"Software Developer", "Data Analyst"}
