"""Regression tests built from real HigherEdJobs wording the 1.x classifier got wrong."""

import pytest

from backend.app.classifier import VERSION, classify

HEDGE = "Please note that this position may not be eligible for visa sponsorship now or in the future."


def check(description, status):
    result = classify(description)
    assert result.status == status
    if result.evidence is not None:
        assert result.evidence in description
    return result


def test_version_is_two():
    assert VERSION == "2.0.0"


def test_form_field_no_on_same_line():
    check("A visa sponsorship is available for the position listed in this vacancy: No", "Not Worth It")


def test_form_field_answer_on_next_line():
    result = check("Job details\nSponsorship Available:\n\nNo\nOther text", "Not Worth It")
    assert "No" in result.evidence


def test_form_field_yes():
    check("Sponsorship Available:\nYes", "Sponsorship Possible")


def test_without_sponsorship_now_or_future():
    check(
        "The selected candidate for this position must be authorized to work in the United States at the time "
        "of hire without employer assistance or sponsorship now or in the future.",
        "Not Worth It",
    )


def test_hedge_is_likely_no():
    check(HEDGE, "Likely No Sponsorship")


def test_hedge_alone_is_likely_no_but_flat_refusal_elsewhere_wins():
    check(HEDGE + "\nVisa sponsorship is not available.", "Not Worth It")


@pytest.mark.parametrize("description", [
    "Paid leave for new parents and IU-sponsored volunteer events",
    "The incumbent is also expected to carry out sponsored research and projects involving students.",
    "Working visa and residence permit in China: XJTLU sponsors working visa and residence permit in China for the staff.",
])
def test_noise_is_ignored(description):
    result = check(description, "No Mention Found")
    assert result.evidence is None


def test_authorization_only_is_neutral():
    sentence = "California State University, Chico employs only individuals lawfully authorized to work in the United States."
    result = check(sentence, "No Mention Found")
    assert result.evidence == sentence


@pytest.mark.parametrize("description", [
    "Applicants must be a U.S. citizen.",
    "U.S. citizenship is required.",
    "Candidates must obtain a security clearance.",
])
def test_citizens_only(description):
    check(description, "Not Worth It")


def test_possible_still_detected():
    check("Employment visa sponsorship may be considered for this position.", "Sponsorship Possible")


def test_signals():
    assert classify("Employer participates in E-Verify. The university is H-1B cap-exempt.").signals == ["E-Verify", "Cap-exempt"]


@pytest.mark.parametrize("institution", [
    "Penn State Harrisburg", "Virginia Tech", "SUNY Oneonta", "Cal Poly San Luis Obispo", "William &amp; Mary",
    "Weill Cornell Medicine", "UC Davis Health", "The Clarice Smith Performing Arts Center",
])
def test_college_employers_are_not_warned(institution):
    assert "Non-college employer" not in classify("Text.", institution).signals


def test_non_college_employer_is_warned():
    assert "Non-college employer" in classify("Text.", "Acme Analytics LLC").signals


# Found when re-labelling the 451 saved jobs.
@pytest.mark.parametrize("description", [
    "Applicants must be legally authorized to work in the United States on a full-time basis without need now or in the future for sponsorship for employment.",
    "Sponsorship for work authorization is not available for this position.",
    "Must be legally authorized to work in the United States without the need for employer sponsorship currently or in the future.",
    "You can pass a background check and obtain and maintain an active Department of War (DoW) security clearance.",
])
def test_more_real_refusals(description):
    check(description, "Not Worth It")


@pytest.mark.parametrize("description", [
    "This position does not require security clearance.",
    "Founded and sponsored by the Order of St. Francis.",
    "To recruit and retain the best faculty, the campus sponsors a Work Life Program that provides programs and services.",
    "Co-lead or sponsor initiatives such as the BI + AI Community of Practice and Data Hours.",
    "sponsor research, pilots, and innovation where institutional value and readiness are demonstrated.",
])
def test_more_real_noise(description):
    assert classify(description).status == "No Mention Found"
