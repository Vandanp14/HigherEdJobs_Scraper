"""Score how well a saved job fits the user's resume, with the reasons behind every point.

Fit is a suggestion, not a filter: a low score only moves a job down the For you ranking. The
skill part compares what a posting asks for with the skills in the master resume
(data/resume.json, JSON Resume layout with a skill_check.declined list). Skills come from a
resume-derived vocabulary plus skills_vocab, so the panel can say exactly which skills matched
and which are missing.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .relevance import is_cs_title
from .skills_vocab import CASE_SENSITIVE, COMMON_SKILLS, SYNONYMS

# Descriptive resume phrases ("Accessibility-compliant interface development") never appear
# verbatim in postings, so only names this short are matched.
_MAX_WORDS = 3
# English words that double as skill names: they do not count at the start of a sentence ("Go to").
_SENTENCE_START_AMBIGUOUS = frozenset({"Go", "R"})


@dataclass(frozen=True)
class Resume:
    skills: frozenset[str]
    backed: frozenset[str]
    declined: frozenset[str]
    digest: str


_ALIASES = {alias.lower(): canonical for canonical, aliases in SYNONYMS.items() for alias in (canonical, *aliases)}


def _canonical(name: str) -> str:
    return _ALIASES.get(name.lower(), name)


def _resume_names(raw: str) -> list[str]:
    """One resume keyword as matchable names: "Progressive Web Apps (PWA)" gives both forms."""
    names = []
    if match := re.fullmatch(r"(.+?)\s*\(([^)]+)\)", raw.strip()):
        raw, acronym = match.group(1), match.group(2)
        if len(acronym.split()) <= _MAX_WORDS:
            names.append(acronym)
    raw = raw.strip()
    if raw and len(re.split(r"[\s-]+", raw)) <= _MAX_WORDS:
        names.append(raw)
    return [_canonical(name) for name in names]


def resume_from_dict(data: dict, digest: str = "dict") -> Resume:
    skills: set[str] = set()
    for group in data.get("skills") or []:
        for keyword in group.get("keywords") or []:
            skills.update(_resume_names(keyword))
    technologies: set[str] = set()
    evidence_text = []
    for project in data.get("projects") or []:
        for technology in project.get("technologies") or []:
            technologies.update(_resume_names(technology))
        evidence_text += [project.get("description") or "", *(project.get("highlights") or [])]
    for job in data.get("work") or []:
        evidence_text += [job.get("summary") or "", *(job.get("highlights") or [])]
    skills |= technologies
    text = "\n".join(evidence_text)
    used_in_text = set(_find(text, _matcher(frozenset(skills))).keys()) if text.strip() else set()
    declined = {_canonical(name) for raw in (data.get("skill_check") or {}).get("declined") or [] for name in _resume_names(raw)}
    return Resume(frozenset(skills), frozenset(technologies | used_in_text), frozenset(declined - skills), digest)


def load_resume(path: Path) -> Resume | None:
    """The resume at path, or None when it is missing or not valid JSON. Never raises."""
    try:
        content = Path(path).read_bytes()
        data = json.loads(content)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return resume_from_dict(data, hashlib.sha256(content).hexdigest()[:12])


@dataclass(frozen=True)
class _Matcher:
    sensitive: re.Pattern | None
    insensitive: re.Pattern | None
    exact: dict[str, str]
    folded: dict[str, str]


def _pattern(surfaces: list[str], flags: int) -> re.Pattern | None:
    if not surfaces:
        return None
    alternation = "|".join(re.escape(surface) for surface in sorted(set(surfaces), key=len, reverse=True))
    # A name must stand alone: "C" is not inside "C++", "SQL" is not inside "NoSQL", "R" not in "R&D".
    return re.compile(rf"(?<![\w+#.&/-])(?:{alternation})(?![\w+#&]|\.\w)", flags)


@lru_cache(maxsize=8)
def _matcher(names: frozenset[str]) -> _Matcher:
    exact: dict[str, str] = {}
    folded: dict[str, str] = {}
    for canonical in names:
        for surface in (canonical, *SYNONYMS.get(canonical, ())):
            if len(surface) <= 3 or surface in CASE_SENSITIVE:
                exact[surface] = canonical
            else:
                folded[surface.lower()] = canonical
    return _Matcher(_pattern(list(exact), 0), _pattern(list(folded), re.IGNORECASE), exact, folded)


_STARTS_SENTENCE = re.compile(r"(?:^|[.!?:\n])\s*[\"'(]?$")
_SENTENCE = re.compile(r"(?<=[.!?;])\s+")
_SOFT = re.compile(r"prefer|desir|\ba\s+plus\b|nice\s+to\s+have|bonus|not\s+required", re.I)
_REQUIRED_HEADING = re.compile(r"requir|minimum|basic|essential|must", re.I)
_PREFERRED_HEADING = re.compile(r"prefer|desir|additional|nice\s+to\s+have|bonus", re.I)


def _find(text: str, matcher: _Matcher) -> dict[str, int]:
    """Canonical skill -> first offset found in text."""
    found: dict[str, int] = {}
    for pattern, lookup, fold in ((matcher.sensitive, matcher.exact, False), (matcher.insensitive, matcher.folded, True)):
        if pattern is None:
            continue
        for match in pattern.finditer(text):
            canonical = lookup[match.group(0).lower() if fold else match.group(0)]
            if canonical in _SENTENCE_START_AMBIGUOUS and _STARTS_SENTENCE.search(text[:match.start()]):
                continue
            found.setdefault(canonical, match.start())
    return found


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    return 0 < len(stripped) <= 60 and not stripped.endswith((".", "!", "?", ";"))


def _asked(description: str, names: frozenset[str]) -> dict[str, str]:
    matcher = _matcher(names)
    asked: dict[str, str] = {}
    section = "required"
    for line in (description or "").splitlines():
        if _is_heading(line):
            if _PREFERRED_HEADING.search(line):
                section = "preferred"
            elif _REQUIRED_HEADING.search(line):
                section = "required"
        for sentence in _SENTENCE.split(line):
            level = "preferred" if section == "preferred" or _SOFT.search(sentence) else "required"
            for skill in _find(sentence, matcher):
                if asked.get(skill) != "required":
                    asked[skill] = level
    return asked


_BASE_NAMES = frozenset(COMMON_SKILLS) | frozenset(SYNONYMS)


def asked_skills(description: str) -> dict[str, str]:
    """Skills from the shared vocabulary a posting asks for, each "required" or "preferred"."""
    return _asked(description, _BASE_NAMES)


def asked_skills_for(description: str, resume: Resume) -> dict[str, str]:
    """asked_skills, with the resume's own skills and declined skills added to the vocabulary."""
    return _asked(description, _BASE_NAMES | resume.skills | resume.declined)


VERSION = "fit-1"
# Weights are a starting point tuned against the user's real saved jobs; tests pin only ordering.
_SKILLS_MAX = 70
_LISTED_ONLY = 0.7  # a skill only listed on the resume, never used in a project or job
_PREFERRED_WEIGHT = 0.5
_DECLINED_PENALTY, _DECLINED_MAX = 5, 15
_NO_KNOWN_SKILLS, _NO_DESCRIPTION = 30, 20
_SPONSORSHIP = {
    "Sponsorship Possible": 20, "No Mention Found": 12, "Unsure - Review": 8, "Likely No Sponsorship": 0,
}
_SPONSORSHIP_UNKNOWN = 10
# An explicit denial keeps the job visible but at the bottom of any group of similar age.
_NOT_WORTH_IT_CAP = 15
_SENIORITY_PENALTY, _SENIORITY_MAX = 12, 36
_CORE_ROLE = re.compile(
    r"software|developer|programmer|engineer|\bweb|\bdata\b|analyst|database|systems?\b|cloud", re.I
)


def _role_points(title: str | None) -> tuple[int, str | None]:
    if title and _CORE_ROLE.search(title):
        return 10, "Core CS role"
    if is_cs_title(title):
        return 5, "Other CS role"
    return 0, None


def score_job(title: str | None, description: str | None, sponsorship_status: str | None,
              seniority_flags: list[dict], resume: Resume) -> dict:
    reasons: list[str] = []
    matched: list[str] = []
    missing: list[str] = []
    declined: list[str] = []
    required_total = required_matched = 0
    if not (description or "").strip():
        skills = float(_NO_DESCRIPTION)
        reasons.append("Description not captured; skills not checked")
    else:
        asked = asked_skills_for(description, resume)
        if not asked:
            skills = float(_NO_KNOWN_SKILLS)
            reasons.append("No listed skills recognised")
        else:
            possible = earned = 0.0
            for skill, level in sorted(asked.items(), key=lambda item: (item[1] != "required", item[0])):
                weight = 1.0 if level == "required" else _PREFERRED_WEIGHT
                possible += weight
                required_total += level == "required"
                if skill in resume.skills:
                    earned += weight * (1.0 if skill in resume.backed else _LISTED_ONLY)
                    matched.append(skill)
                    required_matched += level == "required"
                elif skill in resume.declined and level == "required":
                    declined.append(skill)
                else:
                    missing.append(skill)
            skills = _SKILLS_MAX * earned / possible
            skills -= min(_DECLINED_MAX, _DECLINED_PENALTY * len(declined))
            if required_total:
                reasons.append(f"{required_matched} of {required_total} required skills")
            if declined:
                reasons.append("Needs " + ", ".join(declined))
    role, role_reason = _role_points(title)
    if role_reason:
        reasons.append(role_reason)
    sponsorship = _SPONSORSHIP.get(sponsorship_status or "", _SPONSORSHIP_UNKNOWN)
    if sponsorship_status:
        reasons.append(sponsorship_status)
    labels = [flag["label"] for flag in seniority_flags]
    seniority = -min(_SENIORITY_MAX, _SENIORITY_PENALTY * len(labels))
    reasons += labels
    total = skills + role + sponsorship + seniority
    if sponsorship_status == "Not Worth It":
        total = min(total, _NOT_WORTH_IT_CAP)
    return {
        "score": int(round(max(0.0, min(100.0, total)))),
        "matched": matched, "missing": missing, "declined": declined,
        "required_total": required_total, "required_matched": required_matched,
        "parts": {"skills": round(skills, 1), "role": role, "sponsorship": sponsorship, "seniority": seniority},
        "reasons": reasons,
    }


def version_for(resume: Resume) -> str:
    """Stored with each score so a rules change or a resume edit rescores saved jobs."""
    return f"{VERSION}:{resume.digest}"
