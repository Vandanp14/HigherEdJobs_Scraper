"""Typo- and order-tolerant matching for the dashboard search box.

Every word typed must match some word of the job text: as a plain substring, or within a small
edit distance of the word or of its start (so partial words with a typo still match). Short words
must match exactly, since one edit on a three-letter word matches almost anything.
"""
import re

_WORD = re.compile(r"[a-z0-9]+")


def _allowed_edits(token: str) -> int:
    return 0 if len(token) <= 3 else 1 if len(token) <= 7 else 2


def _distance(a: str, b: str, limit: int) -> int:
    """Optimal string alignment distance (adjacent swaps count as one edit), capped above limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous, current = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        before, previous, current = previous, current, [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                current[j] = min(current[j], before[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
    return current[-1]


def _token_matches(token: str, text: str, words: list[str]) -> bool:
    if token in text:
        return True
    limit = _allowed_edits(token)
    if not limit:
        return False
    n = len(token)
    for word in words:
        candidates = {word, word[:n - 1], word[:n], word[:n + 1]}
        if any(_distance(token, candidate, limit) <= limit for candidate in candidates if candidate):
            return True
    return False


def fuzzy_match(query: str | None, *fields: str | None) -> bool:
    tokens = _WORD.findall((query or "").lower())
    if not tokens:
        return True
    text = " ".join(field for field in fields if field).lower()
    words = _WORD.findall(text)
    return all(_token_matches(token, text, words) for token in tokens)
