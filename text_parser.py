"""Shared deterministic parsing primitives for academic prose.

The analytical modules use this layer so sentence, paragraph, and citation
boundaries are defined consistently across the application.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List


# Common abbreviations that should not terminate a sentence.
_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "fig.", "no.", "nos.", "dr.", "mr.", "mrs.",
    "prof.", "inc.", "dept.", "gov.", "ed.", "eds.", "vol.", "pp.", "p.",
    "u.s.", "u.k.", "a.m.", "p.m.", "et al.",
}

_WORD_RE = re.compile(
    r"[\w\u0300-\u036f\u0900-\u097F\u0A00-\u0A7F]+"
    r"(?:['’\-][\w\u0300-\u036f\u0900-\u097F\u0A00-\u0A7F]+)*",
    re.UNICODE,
)
_YEAR_RE = r"(?:19|20)\d{2}[a-z]?"
_NARRATIVE_RE = re.compile(
    rf"\b[A-Z][A-Za-z'’-]+(?:\s+et al\.)?\s*\({_YEAR_RE}\)"
)
_PAREN_RE = re.compile(rf"\([^()]*?{_YEAR_RE}[^()]*?\)")
_AUTHOR_YEAR_RE = re.compile(
    rf"[A-Z][A-Za-z'’-]+(?:\s+et al\.)?,?\s+{_YEAR_RE}"
)


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return unicodedata.normalize(
        "NFC", text.replace("\r\n", "\n").replace("\r", "\n")
    )


def split_paragraphs(text: str) -> List[str]:
    text = normalize_text(text).strip()
    if not text:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def _is_abbreviation(text: str, end: int) -> bool:
    start = end
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in ".'"):
        start -= 1
    token = text[start:end].lower()
    if token in _ABBREVIATIONS:
        return True
    if token == "al.":
        return text[max(0, start - 3):start].lower() == "et "
    return len(token) == 2 and token[0].isalpha() and token[1] == "."


def split_sentences(text: str) -> List[str]:
    """Split sentences conservatively around academic punctuation."""
    text = normalize_text(text).strip()
    if not text:
        return []

    boundaries: List[int] = []
    for i, char in enumerate(text[:-1]):
        if char not in ".!?":
            continue
        if char == "." and _is_abbreviation(text, i + 1):
            continue
        if (
            char == "."
            and i > 0
            and i + 1 < len(text)
            and text[i - 1].isdigit()
            and text[i + 1].isdigit()
        ):
            continue

        j = i + 1
        while j < len(text) and text[j] in ""”’'»)]}":
            j += 1
        if j >= len(text) or not text[j].isspace():
            continue

        while j < len(text) and text[j].isspace():
            j += 1
        if j >= len(text):
            boundaries.append(j)
            continue

        nxt = text[j]
        if nxt.isupper() or nxt.isdigit() or nxt in ""“‘([—":
            boundaries.append(j)

    if not boundaries:
        return [text]

    sentences: List[str] = []
    start = 0
    for end in boundaries:
        part = text[start:end].strip()
        if part:
            sentences.append(part)
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def words(text: str) -> List[str]:
    """Return Unicode-aware word tokens, including combining marks."""
    return _WORD_RE.findall(normalize_text(text).lower())


def author_year_citations(text: str) -> List[str]:
    """Extract narrative and parenthetical author-year citation forms."""
    text = normalize_text(text)
    found = [m.group(0).strip() for m in _NARRATIVE_RE.finditer(text)]
    for match in _PAREN_RE.finditer(text):
        found.extend(
            m.group(0).strip() for m in _AUTHOR_YEAR_RE.finditer(match.group(0))
        )
    return list(dict.fromkeys(found))


def citations(text: str) -> List[str]:
    """Return de-duplicated author-year citations detected in text."""
    return author_year_citations(text)


def has_citation(text: str) -> bool:
    return bool(citations(text))


def paragraph_count(text: str) -> int:
    return len(split_paragraphs(text))
