import pytest

from backend.app.sources.refs import BoardRef, parse_board_url


@pytest.mark.parametrize("url,expected", [
    ("https://job-boards.greenhouse.io/0verwatch?error=true", BoardRef("greenhouse", "0verwatch")),
    ("https://boards.greenhouse.io/stripe/jobs/123", BoardRef("greenhouse", "stripe")),
    ("https://jobs.lever.co/100ms/4c9f19c7?utm_source=x", BoardRef("lever", "100ms")),
    ("https://jobs.ashbyhq.com/ramp/34413f8d", BoardRef("ashby", "ramp")),
    ("https://jobs.smartrecruiters.com/Visa/123", BoardRef("smartrecruiters", "Visa")),
    ("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/X",
     BoardRef("workday", "nvidia", "nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite")),
    ("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite",
     BoardRef("workday", "nvidia", "nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite")),
    ("http://JOBS.LEVER.CO/Acme/", BoardRef("lever", "Acme")),
])
def test_parse_board_url(url, expected):
    assert parse_board_url(url) == expected


@pytest.mark.parametrize("url", [
    "https://job-boards.greenhouse.io/", "https://job-boards.greenhouse.io/embed/job_app",
    "https://nvidia.wd5.myworkdayjobs.com/", "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/x",
    "https://example.com/careers", "not a url", "",
])
def test_parse_rejects(url):
    assert parse_board_url(url) is None
