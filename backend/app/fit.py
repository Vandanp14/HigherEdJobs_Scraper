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
