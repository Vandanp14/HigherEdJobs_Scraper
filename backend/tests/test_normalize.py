from datetime import datetime, timezone
from pathlib import Path

from backend.app.parser import normalize_air_description, normalize_hej_description, parse_air_job

FIXTURES = Path(__file__).parent / "fixtures"


def test_double_escaped_hej_html_becomes_plain_lines():
    raw = "&lt;p&gt;Duties include analysis.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;li&gt;Visa sponsorship is not available.&lt;/li&gt;&lt;/ul&gt;"
    assert normalize_hej_description(raw) == "Duties include analysis.\nSQL\nVisa sponsorship is not available."


def test_plain_hej_html_unchanged_behaviour():
    assert normalize_hej_description("<p>A &amp; B</p><p>C</p>") == "A & B\nC"


def test_air_normalization_matches_parser_output():
    job = parse_air_job(
        (FIXTURES / "air_detail.html").read_text(),
        "https://www.airweb.org/community/Career-Center/21096",
        datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    assert job.normalized_description == normalize_air_description(job.raw_description)
