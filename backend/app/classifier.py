"""Deterministic, versioned rules. Evidence is always an exact source substring."""

import re
from dataclasses import asdict, dataclass

VERSION = "1.0.0"
TRIGGER = re.compile(
    r"\b(?:visa(?:\s+sponsorship)?|sponsor(?:ship|ing|ed|s)?|h[-‑–]?1b|"
    r"work\s+authorization|employment\s+authorization|authorized\s+to\s+work|"
    r"legally\s+authorized)\b", re.I,
)

# Match within clauses rather than joining unrelated sentences across a posting.
NEGATIVE = [
    r"\b(?:cannot|can\s+not|can't|will\s+not|won't|does\s+not|do\s+not|unable\s+to)\s+(?:\w+[ -]){0,5}sponsor(?:ship)?\b",
    r"\b(?:visa\s+|h[-‑–]?1b\s+)?sponsorship\s+(?:\w+\s+){0,3}(?:not\s+(?:available|provided|offered|possible|supported)|unavailable)\b",
    r"\bnot\s+eligible\s+for\s+(?:\w+[ -]){0,3}sponsorship\b",
    r"\bwithout\s+(?:(?:current|future)\s+(?:(?:or|and)\s+)?){0,2}(?:visa\s+|employer\s+)?sponsorship\b",
    r"\bno\s+(?:visa\s+|h[-‑–]?1b\s+)?sponsorship\s+(?:is\s+)?(?:available|provided|offered)\b",
]
LIKELY = [
    r"\b(?:must|require\w*|already)\b.{0,80}\bunrestricted\b.{0,30}\b(?:work|employment)\s+authorization\b",
]
POSITIVE = [
    r"\b(?:visa\s+|h[-‑–]?1b\s+)?sponsorship\s+(?:is|may\s+be|can\s+be|will\s+be)\s+(?:available|provided|offered|considered)\b",
    r"\b(?:will|can|may)\s+(?:provide\s+(?:visa\s+|h[-‑–]?1b\s+)?sponsorship|sponsor\s+(?:qualified\s+)?(?:candidates|applicants))\b",
]


@dataclass
class Analysis:
    status: str
    confidence: str
    evidence: str | None
    evidence_context: str | None
    matched_terms: list[str]
    classifier_version: str = VERSION

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


def classify(description: str) -> Analysis:
    candidates = []
    terms = list(dict.fromkeys(m[0] for m in TRIGGER.finditer(description)))
    for paragraph in description.splitlines():
        for sentence in sentences(paragraph):
            if not TRIGGER.search(sentence):
                continue
            lowered = sentence.lower().replace("’", "'")
            if any(re.search(p, lowered) for p in NEGATIVE):
                rank, status, confidence = 4, "Not Worth It", "High"
            elif any(re.search(p, lowered) for p in POSITIVE):
                rank, status, confidence = 3, "Sponsorship Possible", "High"
                if "may " in lowered or "considered" in lowered:
                    confidence = "Medium"
            elif any(re.search(p, lowered) for p in LIKELY):
                rank, status, confidence = 2, "Likely No Sponsorship", "Medium"
            else:
                rank, status, confidence = 1, "Unsure - Review", "Low"
            candidates.append((rank, Analysis(status, confidence, sentence, paragraph.strip(), terms)))
    if not candidates:
        return Analysis("No Mention Found", "Low", None, None, terms)
    return max(candidates, key=lambda item: item[0])[1]
