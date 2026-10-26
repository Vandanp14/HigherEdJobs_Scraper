import pytest

from backend.app.classifier import VERSION, classify


@pytest.mark.parametrize(
    "description",
    [
        "Purdue will not sponsor employment authorization for this position.",
        "Visa sponsorship is not available for this position.",
        "Visa sponsorship will not be provided for this position.",
        "Sponsorship is currently not available.",
        "Penn State does not sponsor or take over sponsorship of a staff employment Visa.",
        "The university will not transfer or assume an existing visa sponsorship.",
        "This role is not eligible for employer sponsorship.",
    ],
)
def test_explicit_sponsorship_denials_are_not_worth_it(description):
    result = classify(description)

    assert result.status == "Not Worth It"
    assert result.confidence == "High"
    assert result.evidence == description
    assert result.classifier_version == VERSION


def test_authorization_requirement_alone_is_neutral_for_opt():
    # An F-1 OPT holder is authorized at hire, so this alone says nothing about future sponsorship.
    result = classify("Applicants must be authorized to work in the U.S.")

    assert result.status == "No Mention Found"
    assert result.confidence == "Low"
    assert result.evidence == "Applicants must be authorized to work in the U.S."


def test_explicit_denial_wins_over_authorization_requirement():
    description = (
        "Penn State does not sponsor or take over sponsorship of a staff employment Visa. "
        "Applicants must be authorized to work in the U.S."
    )

    result = classify(description)

    assert result.status == "Not Worth It"
    assert result.evidence == "Penn State does not sponsor or take over sponsorship of a staff employment Visa."
