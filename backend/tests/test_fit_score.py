"""Fit score composition. Tests pin ordering and caps; exact weights are tuned against real jobs."""
from backend.app.fit import VERSION, resume_from_dict, score_job, version_for

RESUME = resume_from_dict({
    "skills": [{"name": "All", "keywords": ["Python", "SQL", "JavaScript", "Tableau", "React"]}],
    "projects": [{"technologies": ["Python", "SQL", "React"]}],
    "skill_check": {"declined": ["Salesforce"]},
})
PYTHON_SQL = "Required Qualifications\nExperience with Python and SQL."


def score(title="Software Developer", description=PYTHON_SQL, status="No Mention Found", flags=()):
    return score_job(title, description, status, list(flags), RESUME)


def test_better_skill_match_scores_higher():
    assert score()["score"] > score(description="Experience with Angular and Ruby required.")["score"]


def test_required_outweighs_preferred():
    text = "Required Qualifications\nPython.\nPreferred Qualifications\nTableau."
    only_python = resume_from_dict({"skills": [{"keywords": ["Python"]}], "projects": [{"technologies": ["Python"]}]})
    only_tableau = resume_from_dict({"skills": [{"keywords": ["Tableau"]}], "projects": [{"technologies": ["Tableau"]}]})
    assert score_job("Data Analyst", text, "No Mention Found", [], only_python)["score"] > \
        score_job("Data Analyst", text, "No Mention Found", [], only_tableau)["score"]


def test_declined_required_skill_is_a_gap():
    with_gap = score(description=PYTHON_SQL + " Salesforce administration required.")
    assert "Salesforce" in with_gap["declined"]
    assert with_gap["score"] < score()["score"]


def test_backed_skills_count_more():
    # React is used in a project; JavaScript is only listed.
    assert score(description="React required.")["score"] > score(description="JavaScript required.")["score"]


def test_not_worth_it_caps_at_15():
    result = score(status="Not Worth It")
    assert isinstance(result["score"], int) and result["score"] <= 15


def test_no_mention_is_not_a_yes():
    assert score(status="Sponsorship Possible")["score"] > score(status="No Mention Found")["score"]


def test_seniority_flags_lower_score():
    flag = {"label": "Senior / Lead", "evidence": "Senior"}
    assert score()["score"] - score(flags=[flag])["score"] == 12
    assert "Senior / Lead" in score(flags=[flag])["reasons"]


def test_data_role_can_beat_software_role():
    strong_data = score("Data Analyst", "Required: SQL, Python and Tableau.")
    weak_software = score("Software Engineer", "Required: Angular, Ruby, Kotlin and Swift.")
    assert strong_data["score"] > weak_software["score"]


def test_missing_description_still_scores():
    result = score(description=None)
    assert isinstance(result["score"], int)
    assert "Description not captured; skills not checked" in result["reasons"]


def test_result_lists_matched_and_missing():
    result = score(description="Required: Python, SQL and Kubernetes.")
    assert result["matched"] == ["Python", "SQL"]
    assert result["missing"] == ["Kubernetes"]
    assert (result["required_matched"], result["required_total"]) == (2, 3)


def test_score_stays_within_bounds():
    flags = [{"label": label, "evidence": label} for label in ("Director", "Senior / Lead", "5+ years", "Leadership")]
    assert score(description="Angular required.", status="Likely No Sponsorship", flags=flags)["score"] >= 0
    assert score(status="Sponsorship Possible")["score"] <= 100


def test_version_includes_resume_digest():
    assert version_for(RESUME) == f"{VERSION}:{RESUME.digest}"
