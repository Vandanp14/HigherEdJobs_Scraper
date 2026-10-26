from datetime import datetime, timezone

import pytest

from backend.app.parser import AccessBlocked, checked_soup, parse_job

# A normal job page loads a Google reCAPTCHA widget for one of its forms a few seconds
# after DOMContentLoaded. It is part of the page, not an access check.
JOB_PAGE_WITH_RECAPTCHA = """
<html><head><title>Specify Software Developer - HigherEdJobs</title></head><body>
<h1>Specify Software Developer</h1>
<div class="g-recaptcha" data-sitekey="key"><iframe title="reCAPTCHA"
  src="https://www.google.com/recaptcha/api2/anchor?ar=1&amp;k=key"></iframe></div>
</body></html>
"""

INCAPSULA_BLOCK = """
<html><body><iframe id="main-iframe" src="/_Incapsula_Resource?CWUDNSAI=1&amp;incident_id=1"></iframe>
Request unsuccessful. Incapsula incident ID: 1</body></html>
"""


def test_recaptcha_widget_on_job_page_is_not_an_access_check():
    checked_soup(JOB_PAGE_WITH_RECAPTCHA)


def test_incapsula_block_page_is_an_access_check():
    with pytest.raises(AccessBlocked):
        checked_soup(INCAPSULA_BLOCK)


# Some HigherEdJobs pages emit JobPosting JSON-LD with a trailing comma, which strict JSON rejects.
TRAILING_COMMA_JOB = """
<html><body><script type="application/ld+json">
{"@context": "http://schema.org/", "@type": "JobPosting", "title": "Specify Software Developer",
 "description": "<p>Build Specify. We are unable to sponsor visas.</p>",}
</script></body></html>
"""

JOBDESC_ONLY_JOB = """
<html><body><div id="jobDesc"><p>Build Specify. We are unable to sponsor visas.</p></div></body></html>
"""

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
URL = "https://www.higheredjobs.com/search/details.cfm?JobCode=179598161"


def test_job_posting_with_trailing_comma_is_parsed():
    job = parse_job(TRAILING_COMMA_JOB, URL, NOW)
    assert "unable to sponsor" in job.normalized_description
    assert job.title == "Specify Software Developer"


def test_job_description_falls_back_to_jobdesc_block():
    job = parse_job(JOBDESC_ONLY_JOB, URL, NOW)
    assert "unable to sponsor" in job.normalized_description
