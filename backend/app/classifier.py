"""Deterministic, versioned rules. Evidence is always an exact source substring.

Tuned for an F-1 OPT -> STEM OPT -> cap-exempt H-1B path: current work authorization alone is
fine, any refusal of future sponsorship is not, and a hedge never becomes a hard "Not Worth It".
"""

import html
import re
from dataclasses import asdict, dataclass, field

VERSION = "2.0.0"
TRIGGER = re.compile(
    r"\b(?:visa(?:\s+sponsorship)?|sponsor(?:ship|ing|ed|s)?|h[-‑–]?1b|"
    r"work\s+authorization|employment\s+authorization|authorized\s+to\s+work|"
    r"legally\s+authorized|lawfully\s+authorized|u\.?s\.?\s+citizen(?:s|ship)?|"
    r"permanent\s+residents?|green\s+card|security\s+clearance)\b", re.I,
)
# Current authorization only. An OPT holder meets it, so on its own it is neutral.
AUTHORIZATION_ONLY = re.compile(
    r"^(?:work\s+authorization|employment\s+authorization|authorized\s+to\s+work|"
    r"legally\s+authorized|lawfully\s+authorized)$", re.I,
)
COUNTRIES = r"(?:china|canada|the\s+uk|united\s+kingdom|qatar|the\s+uae|uae|singapore|hong\s+kong|australia)"
# Trigger words used for something other than U.S. work sponsorship.
NOISE = re.compile(
    r"\b\w+-sponsored\b|"
    r"\bsponsored\s+(?:research|projects?|programs?|events?|activities|volunteer\w*|travel|trips?)\b|"
    r"\b(?:sponsors?\s+)?(?:working\s+|work\s+)?visas?\b[^.\n]{0,60}?\bin\s+" + COUNTRIES + r"\b|"
    r"\b(?:does\s+not|doesn't|do\s+not)\s+require\s+(?:an?\s+)?(?:active\s+)?security\s+clearance\b",
    re.I,
)
FUTURE = r"(?:now\s+or\s+in\s+the\s+future|now\s+or\s+future|current(?:ly)?\s+or\s+(?:in\s+the\s+)?future)"
REFUSAL_WORD = r"\b(?:without|not|no|unable|cannot|can't|won't)\b"
# A bare "sponsor" with none of these nearby is about events, research, or founders, not visas.
VISA_CONTEXT = re.compile(r"visa|immigra|h[-‑–]?1b|employ|work\s+auth|authoriz|status|petition|green\s+card")
HEDGE = re.compile(r"\bmay\b|\bmight\b|not\s+guaranteed")
FORM_FIELD = re.compile(
    r"^[^\n]*(?:sponsor|visa)[^\n]*:[ \t]*(?:\n[ \t]*)*(yes|no)[ \t]*(?=\n|$)", re.I | re.M,
)

# Match within clauses rather than joining unrelated sentences across a posting.
NEGATIVE = [
    # Employer names and modifiers can appear before the denial, so anchor on the
    # unambiguous negative verb + sponsorship action instead of an institution.
    r"\b(?:cannot|can\s+not|can't|will\s+not|won't|does\s+not|do\s+not|"
    r"is\s+not\s+able\s+to|are\s+not\s+able\s+to|unable\s+to)\s+"
    r"(?:(?:\w+[ -]){0,5})?(?:sponsor(?:ship|ing|ed)?|provide|offer|support)\b",
    r"\b(?:visa\s+|h[-‑–]?1b\s+|immigration\s+|employer\s+)?sponsorship\s+"
    r"(?:(?:is|will|can)(?:\s+be)?\s+)?(?:(?:currently|presently|at\s+this\s+time)\s+)?"
    r"(?:not\s+(?:be\s+)?(?:available|provided|offered|possible|supported)|unavailable)\b",
    # Some institutions specifically decline a transfer, takeover, or assumption
    # of an existing visa sponsorship. These are as definitive as a flat refusal.
    r"\b(?:does|do|will)\s+not\s+(?:sponsor|transfer|take\s+over|assume)\b"
    r".{0,100}\b(?:visa|sponsorship|employment\s+authorization|immigration)\b",
    r"\bnot\s+eligible\s+for\s+(?:\w+[ -]){0,3}sponsorship\b",
    r"\b(?:is|are)\s+not\s+an?\s+(?:visa\s+)?sponsoring\s+(?:agency|employer|institution)\b",
    r"\bwithout\s+(?:(?:current|future)\s+(?:(?:or|and)\s+)?){0,2}(?:visa\s+|employer\s+)?sponsorship\b",
    r"\bno\s+(?:visa\s+|h[-‑–]?1b\s+)?sponsorship\s+(?:is\s+)?(?:available|provided|offered)\b",
    # The H-1B step comes later for an OPT holder, so refusing future sponsorship is decisive.
    r"\bsponsorship\b[^.]{0,50}?\b(?:is|are|will\s+be)\s+not\s+(?:available|provided|offered|possible)\b",
    r"\b(?:obtain|maintain|hold)\b.{0,40}\bsecurity\s+clearance\b",
    r"\b(?:only\s+(?:u\.?s\.?\s+)?citizens|must\s+be\s+a\s+u\.?s\.?\s+citizen|"
    r"(?:u\.?s\.?\s+)?citizenship\s+(?:is\s+)?required|permanent\s+residents?\s+only|green\s+card\s+required)\b",
    r"\b(?:(?:must|required\s+to)\s+(?:have|hold|obtain)\b.{0,40}security\s+clearance|"
    r"security\s+clearance\s+(?:is\s+)?required)\b",
]
LIKELY = [
    r"\b(?:must|require\w*|already)\b.{0,80}\bunrestricted\b.{0,30}\b(?:work|employment)\s+authorization\b",
]
POSITIVE = [
    r"\b(?:visa\s+|h[-‑–]?1b\s+)?sponsorship\s+(?:is|may\s+be|can\s+be|will\s+be)\s+(?:available|provided|offered|considered)\b",
    r"\b(?:will|can|may)\s+(?:provide\s+(?:visa\s+|h[-‑–]?1b\s+)?sponsorship|sponsor\s+(?:qualified\s+)?(?:candidates|applicants))\b",
]
COLLEGE_WORDS = re.compile(
    r"university|college|institute|school|academy|seminary|conservatory|poly|tech|state|suny|cuny|"
    r"community college|board of regents|system|medicine|medical|health|hospital|campus|"
    r"william & mary|cornell|arts center", re.I,
)


@dataclass
class Analysis:
    status: str
    confidence: str
    evidence: str | None
    evidence_context: str | None
    matched_terms: list[str]
    classifier_version: str = VERSION
    signals: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def sentences(paragraph: str):
    # Protect abbreviations without altering the returned evidence text.
    protected = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m[0].replace(".", "\x00"), paragraph)
    protected = re.sub(r"\b(?:Dr|Mr|Mrs|Ms|Prof)\.", lambda m: m[0].replace(".", "\x00"), protected)
    for match in re.finditer(r".+?(?:[.!?](?=\s|$)|;(?=\s)|$)", protected):
        start, end = match.span()
        clause = paragraph[start:end].strip()
        if clause:
            yield clause


def signals(description: str, institution: str | None) -> list[str]:
    found = []
    if re.search(r"\be-?verify\b", description, re.I):
        found.append("E-Verify")
    if re.search(r"\bcap[\s-]exempt\b", description, re.I):
        found.append("Cap-exempt")
    if institution and not COLLEGE_WORDS.search(html.unescape(institution)):
        found.append("Non-college employer")
    return found


def rate(sentence: str) -> tuple[float, str, str] | None:
    """Rank, status, and confidence for one sentence, or None when it says nothing about sponsorship."""
    lowered = NOISE.sub(" ", sentence.lower().replace("’", "'"))
    found = [match[0] for match in TRIGGER.finditer(lowered)]
    if not found:
        return None
    hedged = bool(HEDGE.search(lowered))
    future_refusal = re.search(REFUSAL_WORD, lowered) and (
        re.search(r"\bsponsor\w*\b.{0,60}\b" + FUTURE, lowered) or re.search(FUTURE + r".{0,60}\bsponsor\w*\b", lowered)
    )
    if future_refusal or any(re.search(p, lowered) for p in NEGATIVE):
        # A hedge keeps a job visible: false "Not Worth It" is the costliest mistake.
        return (2, "Likely No Sponsorship", "Medium") if hedged else (4, "Not Worth It", "High")
    if any(re.search(p, lowered) for p in POSITIVE) and not re.search(r":\s*no\b", lowered):
        return 3, "Sponsorship Possible", "Medium" if hedged or "considered" in lowered else "High"
    if all(re.fullmatch(r"sponsor\w*", term) for term in found) and not VISA_CONTEXT.search(lowered):
        return None
    if hedged and re.search(r"\bnot\b|\bno\b", lowered) and re.search(r"sponsor|visa|h[-‑–]?1b", lowered):
        return 2, "Likely No Sponsorship", "Medium"
    if any(re.search(p, lowered) for p in LIKELY):
        return 2, "Likely No Sponsorship", "Medium"
    if all(AUTHORIZATION_ONLY.match(term) for term in found):
        return 0.5, "No Mention Found", "Low"
    return 1, "Unsure - Review", "Low"


def classify(description: str, institution: str | None = None) -> Analysis:
    candidates = []
    terms = list(dict.fromkeys(m[0] for m in TRIGGER.finditer(NOISE.sub(" ", description))))
    for match in FORM_FIELD.finditer(description):
        if match[1].lower() == "no":
            candidates.append((4, Analysis("Not Worth It", "High", match[0], match[0], terms)))
        else:
            candidates.append((3, Analysis("Sponsorship Possible", "High", match[0], match[0], terms)))
    for paragraph in description.splitlines():
        for sentence in sentences(paragraph):
            rated = rate(sentence)
            if rated:
                rank, status, confidence = rated
                candidates.append((rank, Analysis(status, confidence, sentence, paragraph.strip(), terms)))
    found_signals = signals(description, institution)
    if not candidates:
        return Analysis("No Mention Found", "Low", None, None, terms, signals=found_signals)
    best = max(candidates, key=lambda item: item[0])[1]
    best.signals = found_signals
    return best
