"""Regressions from the final review: wording that must never become a false "Not Worth It"."""

import pytest

from backend.app.classifier import classify


@pytest.mark.parametrize("description", [
    # Job 391, University at Buffalo: a hedge, not a refusal.
    "The University at Buffalo does not guarantee that it will sponsor, support, or otherwise assist with obtaining work authorization.",
    "We cannot guarantee visa sponsorship, but will consider it.",
    "Sponsorship is not guaranteed.",
    "Sponsorship may not be available for this role.",
])
def test_guarantees_and_hedges_are_likely_no(description):
    assert classify(description).status == "Likely No Sponsorship"


@pytest.mark.parametrize("description", [
    # Job 181, UMGC: "sponsor" unrelated to visas.
    "UMGC does not sponsor logistical support for this role.",
    "Applicants do not need to request sponsorship at the time of application.",
    "Candidates do not need to provide proof of work authorization until hire.",
    "No security clearance is required.",
    "Ability to obtain a security clearance is preferred but not required.",
    "No green card required.",
    "Permanent residents only need to submit a copy of their card.",
    "The university sponsors H-1B visas for faculty who require sponsorship now or in the future, with no cost to the employee.",
    "Citizenship or visa restrictions: No",
    "Visa sponsorship is not available for part-time positions, but full-time faculty roles are eligible.",
])
def test_not_refusals(description):
    assert classify(description).status != "Not Worth It"


@pytest.mark.parametrize("description", [
    "Applicants requiring sponsorship will not be considered.",
    "Applicants who need sponsorship will not be considered.",
])
def test_will_not_be_considered_is_a_refusal(description):
    assert classify(description).status == "Not Worth It"


def test_e_verify_negation_is_not_a_positive_badge():
    signals = classify("The college does not participate in E-Verify and cannot support a STEM OPT extension.").signals
    assert "E-Verify" not in signals
    assert "No E-Verify" in signals
