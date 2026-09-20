"""Diagnostics for literature-review argument structure.

The analyzer is heuristic. It identifies patterns for human review; it does not
claim to understand or evaluate the author's scholarship.
"""
import re
from collections import Counter
from typing import Dict, List


class AcademicAnalyzer:
    """Analyse prose for literature-review structure and style signals."""

    FORMULAIC = (
        "it is important to note that", "it is worth noting that",
        "it should be noted that", "in today's world", "in the modern era",
        "in the realm of", "a plethora of", "plays a crucial role in",
        "plays a vital role in", "delve into", "deep dive into", "shed light on",
    )
    ABSOLUTES = (
        "always", "never", "proves that", "clearly demonstrates",
        "definitively shows", "undeniable", "unquestionably",
    )
    COMPARISON = (
        "however", "whereas", "although", "by contrast", "in contrast",
        "similarly", "likewise", "unlike", "while", "yet",
    )
    EVIDENCE = (
        "according to", "finds", "found", "reports", "reported", "documents",
        "documented", "observes", "observed", "estimates", "estimated",
        "survey", "interview", "data", "evidence",
    )
    INTERPRETATION = (
        "this suggests", "this indicates", "this means", "this demonstrates",
        "this reveals", "therefore", "thus", "hence", "because",
    )
    GAP = (
        "however, few", "however, little", "remains unclear", "remains underexplored",
        "limited attention", "little attention", "has not examined",
        "has received little", "gap in the literature", "underexplored",
    )
    CONTRIBUTION = (
        "this study", "this research", "the present study", "this paper",
        "this article", "i argue", "i examine", "i explore",
    )

    def __init__(self, long_sentence_words: int = 35) -> None:
        if long_sentence_words < 1:
            raise ValueError("long_sentence_words must be positive")
        self.long_sentence_words = long_sentence_words

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]

    @staticmethod
    def _words(text: str) -> List[str]:
        return re.findall(r"\b[\w'-]+\b", text.lower())

    @staticmethod
    def _contains(sentence: str, signals: tuple[str, ...]) -> List[str]:
        lower = sentence.lower()
        return [s for s in signals if re.search(r"\b" + re.escape(s) + r"\b", lower)]

    CITATION_PATTERNS = (
        r"\\((?:[^()]*?\\b(?:19|20)\\d{2}[a-z]?\\b[^()]*)\\)",
        r"\\b[A-Z][A-Za-z'’-]+(?:\\s+et al\\.)?\\s*\\((?:19|20)\\d{2}[a-z]?\\)",
    )

    @classmethod
    def _citations(cls, text: str) -> List[str]:
        citations = []
        for pattern in cls.CITATION_PATTERNS:
            citations.extend(re.findall(pattern, text))
        return list(dict.fromkeys(citations))

    @classmethod
    def _citation_count(cls, text: str) -> int:
        return len(cls._citations(text))

    @classmethod
    def _has_citation(cls, text: str) -> bool:
        return bool(cls._citations(text))

    @classmethod
    def _source_attribution(cls, sentence: str) -> bool:
        return bool(re.search(
            r"\\b(?:[A-Z][A-Za-z'’-]+(?:\\s+et al\\.)?\\s*\\((?:19|20)\\d{2}[a-z]?\\)|"
            r"according to|argues?|argue|finds?|found|shows?|show|reports?|reported|"
            r"documents?|documented|observes?|observed|estimates?|estimated)\\b",
            sentence,
            re.IGNORECASE,
        ))

    def _repetitive_openings(self, sentences: List[str]) -> Dict[str, int]:
        openings = []
        for s in sentences:
            words = self._words(s)
            if words:
                openings.append(" ".join(words[:2]))
        counts = Counter(openings)
        return {k: v for k, v in counts.items() if v > 1}

    def _roles(self, sentences: List[str]) -> List[Dict[str, object]]:
        roles = []
        for i, sentence in enumerate(sentences, 1):
            citation = self._has_citation(sentence)
            evidence = self._contains(sentence, self.EVIDENCE)
            interpretation = self._contains(sentence, self.INTERPRETATION)
            comparison = self._contains(sentence, self.COMPARISON)
            gap = self._contains(sentence, self.GAP)
            contribution = self._contains(sentence, self.CONTRIBUTION)

            if gap:
                role = "gap"
            elif comparison:
                role = "comparison_or_synthesis"
            elif evidence or citation:
                role = "source_or_evidence"
            elif interpretation:
                role = "interpretation"
            elif contribution:
                role = "author_position"
            else:
                role = "claim_or_context"

            roles.append({
                "sentence": i,
                "role": role,
                "signals": {
                    "citation": citation,
                    "evidence": evidence,
                    "interpretation": interpretation,
                    "comparison": comparison,
                    "gap": gap,
                    "contribution": contribution,
                },
                "text": sentence,
            })
        return roles

    def analyse(self, text: str) -> Dict[str, object]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        sentences = self._sentences(text)
        roles = self._roles(sentences)
        role_names = [r["role"] for r in roles]

        missing = []
        for role in ("source_or_evidence", "interpretation", "comparison_or_synthesis"):
            if role not in role_names:
                missing.append(role)

        return {
            "sentence_count": len(sentences),
            "word_count": len(self._words(text)),
            "formulaic_phrases": [p for p in self.FORMULAIC if p in text.lower()],
            "possible_overclaims": [p for p in self.ABSOLUTES if p in text.lower()],
            "repetitive_openings": self._repetitive_openings(sentences),
            "long_sentences": [
                {"sentence": i, "words": len(self._words(s)), "text": s}
                for i, s in enumerate(sentences, 1)
                if len(self._words(s)) >= self.long_sentence_words
            ],
            "citation_count": self._citation_count(text),
            "citations": self._citations(text),
            "citation_diagnostics": {
                "cited_source_claims": len(cited_source_claims),
                "possible_uncited_source_claims": uncited_source_claims,
                "note": "Possible flags only; some claims may be common knowledge or supported by a citation elsewhere in the paragraph.",
            },
            "roles": roles,
            "literature_review_signals": {
                "source_or_evidence": any(r["role"] == "source_or_evidence" for r in roles),
                "interpretation": any(r["role"] == "interpretation" for r in roles),
                "comparison_or_synthesis": any(r["role"] == "comparison_or_synthesis" for r in roles),
                "gap": any(r["role"] == "gap" for r in roles),
                "author_position": any(r["role"] == "author_position" for r in roles),
                "possible_missing": missing,
            },
        }

    def summary(self, text: str) -> str:
        r = self.analyse(text)
        messages = [f"{r['sentence_count']} sentences, {r['word_count']} words."]
        if r["formulaic_phrases"]:
            messages.append("Formulaic phrasing: " + ", ".join(r["formulaic_phrases"]) + ".")
        if r["possible_overclaims"]:
            messages.append("Possible overclaiming: " + ", ".join(r["possible_overclaims"]) + ".")
        if r["citation_diagnostics"]["possible_uncited_source_claims"]:\n            messages.append("Possible uncited source-based claims in sentence(s): " + ", ".join(map(str, r["citation_diagnostics"]["possible_uncited_source_claims"])) + ".")\n        if r["repetitive_openings"]:
            messages.append("Repeated openings: " + ", ".join(
                f"{k} ({v})" for k, v in r["repetitive_openings"].items()) + ".")
        if r["long_sentences"]:
            messages.append(f"{len(r['long_sentences'])} long sentence(s) need review.")
        missing = r["literature_review_signals"]["possible_missing"]
        if missing:
            messages.append("Review paragraph logic for: " + ", ".join(missing) + ".")
        return " ".join(messages)


if __name__ == "__main__":
    sample = (
        "Jodhka (2004) shows that caste remains connected to land relations. "
        "This suggests that land cannot be treated separately from caste. "
        "However, other studies emphasise regional variation. "
        "This study examines how these relations are reconfigured."
    )
    print(AcademicAnalyzer().summary(sample))
