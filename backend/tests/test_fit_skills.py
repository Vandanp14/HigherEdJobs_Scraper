"""Skill extraction for fit scoring. The resume here is synthetic; tests never read data/resume.json."""
from backend.app.fit import asked_skills, asked_skills_for, load_resume, resume_from_dict

RESUME = {
    "skills": [
        {"name": "Languages", "keywords": [
            "Python", "JavaScript", "SQL", "Go", "C", "Accessibility-compliant interface development",
        ]},
    ],
    "projects": [{"technologies": ["Python", "React"]}],
    "work": [{"highlights": ["Built ETL pipelines in SQL"]}],
    "skill_check": {"declined": ["Salesforce", "Slate"]},
}


def test_resume_collects_skills_backed_and_declined():
    resume = resume_from_dict(RESUME)
    assert {"Python", "JavaScript", "SQL", "React"} <= resume.skills
    assert {"Python", "React", "SQL"} <= resume.backed
    assert resume.declined == {"Salesforce", "Slate"}
    # Long descriptive phrases never appear verbatim in postings, so they are not matched.
    assert "Accessibility-compliant interface development" not in resume.skills


def test_synonyms_map_to_canonical():
    assert asked_skills("Experience with JS and Postgres required.") == {"JavaScript": "required", "PostgreSQL": "required"}


def test_short_names_do_not_match_inside_other_tokens():
    asked = asked_skills_for("Familiar with C++ and C#, R&D, NoSQL stores. Go to the office.", resume_from_dict(RESUME))
    assert "C" not in asked and "Go" not in asked and "SQL" not in asked


def test_short_names_match_on_their_own():
    asked = asked_skills_for("Write services in Go and C.", resume_from_dict(RESUME))
    assert asked == {"Go": "required", "C": "required"}


def test_preferred_section_and_soft_sentences():
    text = "Required Qualifications\nPython and SQL.\nPreferred Qualifications\nReact.\nTableau experience is a plus."
    assert asked_skills(text) == {"Python": "required", "SQL": "required", "React": "preferred", "Tableau": "preferred"}


def test_soft_sentence_inside_required_section_is_preferred():
    text = "Minimum Qualifications\nPython required. Experience with Tableau preferred."
    assert asked_skills(text) == {"Python": "required", "Tableau": "preferred"}


def test_required_wins_over_preferred():
    assert asked_skills("Python required. Python 3 experience preferred.") == {"Python": "required"}


def test_unsectioned_text_counts_as_required():
    assert asked_skills("You will build tools in Python.") == {"Python": "required"}


def test_declined_and_resume_terms_join_the_vocabulary():
    asked = asked_skills_for("Slate CRM experience required.", resume_from_dict(RESUME))
    assert asked == {"Slate": "required"}


def test_load_resume_missing_or_invalid(tmp_path):
    assert load_resume(tmp_path / "nope.json") is None
    (tmp_path / "bad.json").write_text("{not json")
    assert load_resume(tmp_path / "bad.json") is None


def test_load_resume_digest_tracks_file_contents(tmp_path):
    import json
    path = tmp_path / "resume.json"
    path.write_text(json.dumps(RESUME))
    first = load_resume(path)
    path.write_text(json.dumps(RESUME | {"skill_check": {"declined": []}}))
    second = load_resume(path)
    assert first.digest != second.digest and len(first.digest) == 12


def test_load_resume_wrong_shape_returns_none(tmp_path):
    import json
    for data in ({"skills": ["Python", "SQL"]}, {"skills": [{"keywords": [None]}]}, {"projects": "abc"}, {"skill_check": "x"}):
        (tmp_path / "odd.json").write_text(json.dumps(data))
        assert load_resume(tmp_path / "odd.json") is None


def test_english_words_are_not_skills():
    text = ("Work with the rest of the team. Start date: Spring 2027 semester. Provide Go-Live support "
            "to the C-suite at an R-1 university. Excel in a fast-paced role. Navigate campus systems. "
            "Department of Statistics.")
    assert asked_skills(text) == {}


def test_rest_apis_still_match():
    assert asked_skills("Build REST APIs and RESTful services.") == {"REST APIs": "required"}
