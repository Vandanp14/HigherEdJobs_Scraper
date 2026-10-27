"""Decide whether a job title is a computer science / IT role worth applying to.

HigherEdJobs keyword search matches anywhere in a description, so a chemistry faculty post that
mentions "data analysis" comes back from the data query. Only CS-field roles are useful here
(STEM OPT employment must relate to the CS degree), so keyword results are kept only when the
title itself names such a role. Teaching and academic-track roles (professors, lecturers, instructors, deans, department
chairs) are dropped even in CS, because they are not roles to apply to here.
"""
import re

_WORDS = re.compile(
    r"""
    software | (?<!job\ )(?<!content\ )(?<!curriculum\ )(?<!course\ )(?<!services\ )developer | programmer
    | \bdata\b | database | analytics | business\ intelligence
    | machine\ learning | artificial\ intelligence | deep\ learning
    | computer | computing | (?:bio|health\ )?informatic | information\ (?:technology|systems|security)
    | cyber | network\ (?:engineer|administrator|analyst|architect|specialist|technician)
    | \bweb(?:site|master)?\b | full[-\ ]?stack | front[-\ ]?end | back[-\ ]?end
    | devops | \bcloud\b | \baws\b | azure | site\ reliability
    | \bsystems?\ (?:\S+\ )?(?:administrator|analyst|engineer|architect|developer|integrat|programmer|specialist)(?!ing)
    | \bapplications?\ (?:&\ |support\ |services\ |solutions\ )?(?:analyst|developer|development|administrator|architect|engineer|specialist|programmer)
    | user\ experience | digital\ accessibility | computational | linux | \bserver\b | infrastructure\ engineer
    | desktop\ support | help\ ?desk | technical\ support | endpoint | release\ manager | \.net\b
    | salesforce | servicenow | chief\ (?:information|technology)\ officer | technology\ services
    | institutional\ research | identity\ (?:&\ |and\ )?access | access\ management | hardware
    """,
    re.IGNORECASE | re.VERBOSE,
)
_TEACHING = re.compile(
    r"""professor | lecturer | instructor | faculty | \bfac\b | tenure | adjunct | teaching | \btutor
    | course\ director | \bdean\b | \bchair\b | provost | grading\ assistant""",
    re.IGNORECASE | re.VERBOSE,
)
# Acronyms are matched case-sensitively so ordinary words ("it", "ai") do not count.
_ACRONYMS = re.compile(r"\b(?:IT|AI|BI|UX|UI|HPC|SRE|DBA|ERP|HRIS|CIO|CRM)\b")


def is_teaching_title(title: str | None) -> bool:
    return bool(title) and bool(_TEACHING.search(title))


def is_cs_title(title: str | None) -> bool:
    return bool(title) and not is_teaching_title(title) and bool(_WORDS.search(title) or _ACRONYMS.search(title))
