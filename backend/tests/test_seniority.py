import pytest

from backend.app.seniority import LABELS, flag_role


def labels(title=None, description=None):
    return [flag["label"] for flag in flag_role(title, description)]


@pytest.mark.parametrize(
    ("title", "label"),
    [
        ("Director of Institutional Research", "Director"),
        ("Assistant Director of IT", "Director"),
        ("Associate Director, Data Services", "Director"),
        ("Postdoctoral Researcher - Research Software Engineer", "Postdoc / PhD"),
        ("Post-Doc Fellow in Data Science", "Postdoc / PhD"),
        ("IT Manager (Sightline Information Technology)", "Leadership"),
        ("Chief Data Officer", "Leadership"),
        ("Help Desk Supervisor", "Leadership"),
        ("Head of Analytics", "Leadership"),
        ("Assistant Vice President for Enrollment Technology", "Leadership"),
        ("Senior Data Analyst", "Senior / Lead"),
        ("Sr. Research Data Analyst", "Senior / Lead"),
        ("Data Engineer Lead", "Senior / Lead"),
        ("Principal Data Architect", "Senior / Lead"),
        ("Data Architect - Hybrid", "Senior / Lead"),
        ("Applications Programmer V", "Level III+"),
        ("Business Intelligence Analyst IV - R109565", "Level III+"),
        ("Systems Administrator III", "Level III+"),
    ],
)
def test_title_rules_flag_roles_a_new_grad_does_not_qualify_for(title, label):
    assert label in labels(title)


@pytest.mark.parametrize(
    "title",
    [
        "Software Developer I",
        "Systems Administrator II",
        "Directory Services Engineer",
        "Leadership Program Analyst",
        "Management Information Systems Analyst",
        "Data Analyst",
        "Web Developer",
        "Database Administrator",
        "Help Desk Specialist I",
    ],
)
def test_title_rules_leave_entry_level_roles_alone(title):
    assert labels(title) == []


@pytest.mark.parametrize(
    ("description", "label"),
    [
        ("A PhD is required. Duties include analysis.", "Postdoc / PhD"),
        ("Doctorate required in computer science or a related field.", "Postdoc / PhD"),
        ("Minimum of 5 years of experience in software development.", "5+ years"),
        ("Requires seven (7) years of related experience.", "5+ years"),
        ("At least 10 years of experience required.", "5+ years"),
        ("Master's degree required in information systems.", "Master's required"),
        ("Requires a master’s degree in data science.", "Master's required"),
    ],
)
def test_description_rules_flag_stated_requirements(description, label):
    assert label in labels("Data Analyst", description)


@pytest.mark.parametrize(
    "description",
    [
        "5 years of experience preferred.",
        "Five or more years of experience is desired.",
        "3 years of experience required.",
        "Master's degree preferred.",
        "Bachelor's degree and 5 years of experience preferred, or Master's degree required and 3 years.",
        "Master's degree or equivalent experience required.",
        "PhD preferred but not required.",
    ],
)
def test_description_rules_ignore_preferred_or_alternative_wording(description):
    assert labels("Data Analyst", description) == []


def test_flags_carry_exact_evidence_in_label_order():
    title = "Senior Director of Data"
    description = "Minimum of 6 years of experience required."
    flags = flag_role(title, description)
    assert [flag["label"] for flag in flags] == ["Director", "Senior / Lead", "5+ years"]
    for flag in flags:
        assert flag["evidence"] in title or flag["evidence"] in description
    assert [flag["label"] for flag in flags] == [label for label in LABELS if label in labels(title, description)]


def test_missing_title_and_description_yield_no_flags():
    assert flag_role(None, None) == []


@pytest.mark.parametrize(
    "description",
    [
        "3-5 years of experience required.",
        "Minimum of 2 to 5 years of experience.",
        "Requires three to five (5) years of experience.",
        "Two to five+ years of experience required.",
        "Bachelor's degree required (or 5+ years of equivalent experience).",
        "In lieu of a Bachelor's degree, at least nine (9) years of experience is required.",
    ],
)
def test_years_rule_ignores_ranges_starting_below_five_and_degree_substitutes(description):
    assert "5+ years" not in labels("Data Analyst", description)


@pytest.mark.parametrize(
    "description",
    [
        "5-7 years of experience required.",
        "Bachelor's degree and 5 years of experience required.",
    ],
)
def test_years_rule_still_flags_hard_five_year_minimums(description):
    assert "5+ years" in labels("Data Analyst", description)


@pytest.mark.parametrize(
    "description",
    [
        "A master's degree in computer science may be substituted for one year of the required experience.",
        "BA/BS plus at least two years of experience required, or master's degree.",
        "Requires a master's degree or 2 years of experience.",
        "In lieu of a Master's degree, 3 years of experience required.",
    ],
)
def test_masters_rule_ignores_substitutes_and_alternatives(description):
    assert "Master's required" not in labels("Data Analyst", description)


@pytest.mark.parametrize(
    "description",
    [
        "They would receive additional guidance from at least one PhD student.",
        "MS and PhD students must have approval from their advisors.",
        "Must have experience working with PhD students.",
        "Requires a PhD plus 4 years, or BA/BS plus 6 years.",
        "Doctorate, Master's or Bachelor's degree required.",
    ],
)
def test_phd_rule_ignores_mentions_and_alternatives(description):
    assert "Postdoc / PhD" not in labels("Data Analyst", description)


def test_phd_rule_flags_a_required_doctorate_in_a_field():
    assert "Postdoc / PhD" in labels("Data Analyst", "PhD in computer science or a related field required.")


@pytest.mark.parametrize(
    "title",
    [
        "Title IV Financial Aid Analyst",
        "Title III Grant Data Coordinator",
        "Network Engineer I/II/III",
        "APPLICATION ADMINISTRATOR I/II/III",
        "BI ETL Data Developer II or III",
        "IT Support Technician I, II, and III",
    ],
)
def test_level_rule_ignores_grant_titles_and_multi_level_postings(title):
    assert "Level III+" not in labels(title)
