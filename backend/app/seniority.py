"""Label roles a new-grad BS holder does not qualify for: seniority, doctorates, years of experience.

Labels are a view filter, not a verdict: the dashboard hides labelled jobs by default and lets the
user show each label again. Each flag keeps the exact matched text so the badge can say why.
Description rules read one sentence at a time and skip sentences that only prefer the requirement
or offer an alternative ("Master's or equivalent experience"), so a nice-to-have never hides a job.
"""
import re

VERSION = "seniority-1"
LABELS = ("Director", "Postdoc / PhD", "Leadership", "Senior / Lead", "Level III+", "5+ years", "Master's required")

_TITLE_RULES = {
    "Director": re.compile(r"\bdirector\b", re.I),
    "Postdoc / PhD": re.compile(r"\bpost[-\s]?doc\w*|\bdoctoral\b", re.I),
    "Leadership": re.compile(
        r"\bchief\b|\bvice\s+president\b|\bvp\b|\bcio\b|\bcto\b|\bhead\s+of\b|\bmanager\b|\bsupervisor\b", re.I
    ),
    "Senior / Lead": re.compile(r"\bsenior\b|\bsr\b\.?|\blead\b|\bprincipal\b|\barchitect\b", re.I),
    # Roman pay grades are case-sensitive so words like "vi" or "iv" in prose do not count.
    "Level III+": re.compile(
        r"\b(?:III|IV|V|VI)\b|\b(?:analyst|programmer|engineer|developer|specialist|administrator|technician)\s+[3-9]\b"
    ),
}

_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")
_SOFT = re.compile(r"prefer|desir|\ba\s+plus\b|not\s+required|nice\s+to\s+have", re.I)
_REQUIRED = re.compile(r"requir|minimum|at\s+least|must", re.I)
_ALTERNATIVE = re.compile(r"bachelor|equivalent", re.I)
_PHD = re.compile(r"\bph\.?\s?d\b\.?|\bdoctorate\b|\bdoctoral\s+degree\b", re.I)
_YEARS = re.compile(
    r"\b(?:[5-9]|[1-3]\d|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)\b"
    r"(?:\s*\(\d{1,2}\))?\+?\s+(?:or\s+more\s+)?(?:full[-\s]time\s+)?years?",
    re.I,
)
_MASTERS = re.compile(r"\bmaster(?:'|’)?s(?:'|’)?\s+degree", re.I)


def _description_flags(description: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for sentence in _SENTENCES.split(description):
        if _SOFT.search(sentence) or not _REQUIRED.search(sentence):
            continue
        if "Postdoc / PhD" not in found and (match := _PHD.search(sentence)):
            found["Postdoc / PhD"] = match.group(0)
        if "5+ years" not in found and re.search(r"experience", sentence, re.I) and (match := _YEARS.search(sentence)):
            found["5+ years"] = match.group(0)
        if "Master's required" not in found and not _ALTERNATIVE.search(sentence) and (match := _MASTERS.search(sentence)):
            found["Master's required"] = match.group(0)
    return found


def flag_role(title: str | None, description: str | None) -> list[dict]:
    found = {label: match.group(0) for label, rule in _TITLE_RULES.items() if title and (match := rule.search(title))}
    for label, evidence in _description_flags(description or "").items():
        found.setdefault(label, evidence)
    return [{"label": label, "evidence": found[label]} for label in LABELS if label in found]
