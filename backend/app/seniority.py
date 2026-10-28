"""Label roles a new-grad BS holder does not qualify for: seniority, doctorates, years of experience.

Labels are a view filter, not a verdict: the dashboard hides labelled jobs by default and lets the
user show each label again. Each flag keeps the exact matched text so the badge can say why.
Description rules read one sentence at a time and skip sentences that only prefer the requirement
or offer an alternative ("Master's or equivalent experience"), so a nice-to-have never hides a job.
"""
import re

VERSION = "seniority-2"
LABELS = ("Director", "Postdoc / PhD", "Leadership", "Senior / Lead", "Level III+", "5+ years", "Master's required")

_TITLE_RULES = {
    "Director": re.compile(r"\bdirector\b", re.I),
    "Postdoc / PhD": re.compile(r"\bpost[-\s]?doc\w*|\bdoctoral\b", re.I),
    "Leadership": re.compile(
        r"\bchief\b|\bvice\s+president\b|\bvp\b|\bcio\b|\bcto\b|\bhead\s+of\b|\bmanager\b|\bsupervisor\b", re.I
    ),
    "Senior / Lead": re.compile(r"\bsenior\b|\bsr\b\.?|\blead\b|\bprincipal\b|\barchitect\b", re.I),
    # Roman pay grades are case-sensitive so words like "vi" or "iv" in prose do not count.
    # "Title III/IV/V" are federal grant programs, not levels.
    "Level III+": re.compile(
        r"(?<!Title )(?<!TITLE )\b(?:III|IV|V|VI)\b"
        r"|\b(?:analyst|programmer|engineer|developer|specialist|administrator|technician)\s+[3-9]\b"
    ),
}
# "Engineer I/II/III" hires at every listed level, including entry level.
_MULTI_LEVEL = re.compile(r"\bI{1,2}\b\s*(?:/|,|or\b|and\b)")

_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")
_SOFT = re.compile(r"prefer|desir|\ba\s+plus\b|not\s+required|nice\s+to\s+have", re.I)
_REQUIRED = re.compile(r"requir|minimum|at\s+least|must", re.I)
# A degree that can be swapped for another degree or for experience is not a hard requirement.
_ALTERNATIVE = re.compile(
    r"bachelor|equivalent|\bB\.?[AS]\b|in\s+lieu|substitut|\bor\b[^.]{0,80}?\byears?\b", re.I
)
_PHD_ALTERNATIVE = re.compile(_ALTERNATIVE.pattern + r"|master", re.I)
_PHD = re.compile(
    r"(?:\bph\.?\s?d\b\.?|\bdoctorate\b|\bdoctoral\s+degree\b)"
    r"(?!\s+(?:students?|candidates?|programs?|supervisors?|advisors?)\b)",
    re.I,
)
_NUMBER = r"\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty"
_WORDS = {word: value for value, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())} | {"fifteen": 15, "twenty": 20}
# A range counts by its lower bound: "3-5 years" is open to someone with three.
_YEARS = re.compile(
    rf"\b(?P<low>{_NUMBER})\b(?:\s*(?:-|–|to)\s*(?:{_NUMBER})\b)?"
    r"(?:\s*\(\d{1,2}\))?\+?\s+(?:or\s+more\s+)?(?:full[-\s]time\s+)?years?",
    re.I,
)
# "or 5+ years of experience" offered in place of a degree.
_YEARS_SUBSTITUTE = re.compile(r"in\s+lieu|substitut|\bor\s+(?:at\s+least\s+)?$", re.I)
_MASTERS = re.compile(r"\bmaster(?:'|’)?s(?:'|’)?\s+degree", re.I)


def _description_flags(description: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for sentence in _SENTENCES.split(description):
        if _SOFT.search(sentence) or not _REQUIRED.search(sentence):
            continue
        if "Postdoc / PhD" not in found and not _PHD_ALTERNATIVE.search(sentence) and (match := _PHD.search(sentence)):
            found["Postdoc / PhD"] = match.group(0)
        if "5+ years" not in found and re.search(r"experience", sentence, re.I) and (evidence := _years_required(sentence)):
            found["5+ years"] = evidence
        if "Master's required" not in found and not _ALTERNATIVE.search(sentence) and (match := _MASTERS.search(sentence)):
            found["Master's required"] = match.group(0)
    return found


def _years_required(sentence: str) -> str | None:
    if re.search(r"in\s+lieu|substitut", sentence, re.I):
        return None
    for match in _YEARS.finditer(sentence):
        low = match.group("low").lower()
        value = int(low) if low.isdigit() else _WORDS[low]
        if value >= 5 and not _YEARS_SUBSTITUTE.search(sentence[max(0, match.start() - 20):match.start()]):
            return match.group(0)
    return None


def flag_role(title: str | None, description: str | None) -> list[dict]:
    found = {label: match.group(0) for label, rule in _TITLE_RULES.items() if title and (match := rule.search(title))}
    if title and _MULTI_LEVEL.search(title):
        found.pop("Level III+", None)
    for label, evidence in _description_flags(description or "").items():
        found.setdefault(label, evidence)
    return [{"label": label, "evidence": found[label]} for label in LABELS if label in found]
