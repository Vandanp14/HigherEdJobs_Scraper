import re

from backend.app.progress import report


def test_report_prefixes_time_and_source(capsys):
    report("AIR", "Found 19 listings")
    assert re.fullmatch(r"\d\d:\d\d:\d\d \[AIR\] Found 19 listings\n", capsys.readouterr().out)
