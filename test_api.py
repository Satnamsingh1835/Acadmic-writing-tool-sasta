"""Cached document analysis for academic prose."""
from __future__ import annotations

import re
from collections import Counter

from text_parser import citations as parse_citations
from text_parser import split_sentences, words as parse_words


class AcademicAnalyzer:
    FORMULAIC = (
        "it is important to note that",
        "it is worth noting that",
        "it should be noted that",
        "in today's world",
        "in the modern era",
        "in the realm of",
        "a plethora of",
        "plays a crucial role in",
        "plays a vital role in",
    )
    ABSOLUTES = (
        "always",
        "never",
        "proves that",
        "clearly demonstrates",
        "definitively shows",
        "undeniable",
        "unquestionably",
    )
    COMPARISON = (
        "however",
        "whereas",
        "although",
        "by contrast",
        "in contrast",
        "similarly",
        "likewise",
        "unlike",
        "while",
        "yet",
    )
    EVIDENCE = (
        "according to",
        "finds",
        "found",
        "reports",
        "reported",
        "documents",
        "documented",
        "observes",
        "observed",
        "estimates",
        "estimated",
        "survey",
        "interview",
        "data",
        "evidence",
    )
    INTERPRETATION = (
        "this suggests",
        "this indicates",
        "this means",
        "this demonstrates",
        "this reveals",
        "therefore",
        "thus",
        "hence",
        "because",
    )
    GAP = (
        "however, few",
        "however, little",
        "remains unclear",
        "remains underexplored",
        "limited attention",
        "little attention",
        "has not examined",
        "has received little",
        "gap in the literature",
    )
    CONTRIBUTION = (
        "this study",
        "this research",
        "the present study",
        "this paper",
        "this article",
        "i argue",
        "i examine",
        "i explore",
    )
    SOURCE_RE = re.compile(
        r"\b(?:according to|argues?|argue|finds?|found|shows?|show|reports?|reported|documents?|documented|observes?|observed|estimates?|estimated)\b",
        re.IGNORECASE,
    )

    def __init__(self, long_sentence_words: int = 35) -> None:
        if long_sentence_words < 1:
            raise ValueError("long_sentence_words must be positive")
        self.long_sentence_words = long_sentence_words

    @classmethod
    def sentences(cls, text: str) -> list[str]:
        return split_sentences(text)

    @classmethod
    def words(cls, text: str) -> list[str]:
        return parse_words(text)

    @classmethod
    def contains(cls, sentence: str, signals: tuple[str, ...]) -> list[str]:
        lower = sentence.lower()
        return [s for s in signals if re.search(r"\b" + re.escape(s) + r"\b", lower)]

    @classmethod
    def citations(cls, text: str) -> list[str]:
        return parse_citations(text)

    def analyse(self, text: str) -> dict:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text.strip():
            raise ValueError("Text is empty.")

        sentences = self.sentences(text)
        sentence_words = [self.words(s) for s in sentences]
        sentence_citations = [self.citations(s) for s in sentences]
        roles = []

        for index, sentence in enumerate(sentences):
            evidence = self.contains(sentence, self.EVIDENCE)
            interpretation = self.contains(sentence, self.INTERPRETATION)
            comparison = self.contains(sentence, self.COMPARISON)
            gap = self.contains(sentence, self.GAP)
            contribution = self.contains(sentence, self.CONTRIBUTION)
            has_citation = bool(sentence_citations[index])

            if gap:
                role = "gap"
            elif comparison:
                role = "comparison_or_synthesis"
            elif evidence or has_citation:
                role = "source_or_evidence"
            elif interpretation:
                role = "interpretation"
            elif contribution:
                role = "author_connection"
            else:
                role = "interpretation"

            roles.append(
                {
                    "sentence": index + 1,
                    "role": role,
                    "signals": {
                        "citation": has_citation,
                        "evidence": evidence,
                        "interpretation": interpretation,
                        "comparison": comparison,
                        "gap": gap,
                        "contribution": contribution,
                    },
                }
            )

        role_names = [r["role"] for r in roles]
        openings = [" ".join(words[:2]) for words in sentence_words if words]
        counts = Counter(openings)
        lower_text = text.lower()
        source_claims = [
            i + 1
            for i, sentence in enumerate(sentences)
            if (sentence_citations[i] or self.SOURCE_RE.search(sentence))
        ]
        cited_source_claims = [
            i + 1 for i, citations in enumerate(sentence_citations) if citations
        ]

        return {
            "sentence_count": len(sentences),
            "word_count": sum(len(words) for words in sentence_words),
            "formulaic_phrases": [phrase for phrase in self.FORMULAIC if phrase in lower_text],
            "possible_overclaims": [phrase for phrase in self.ABSOLUTES if phrase in lower_text],
            "long_sentences": [
                i + 1 for i, words in enumerate(sentence_words) if len(words) > self.long_sentence_words
            ],
            "citation_count": sum(len(cites) for cites in sentence_citations),
            "literature_review_signals": {
                "source_or_evidence": "source_or_evidence" in role_names,
                "interpretation": "interpretation" in role_names,
                "comparison_or_synthesis": "comparison_or_synthesis" in role_names,
                "gap": "gap" in role_names,
                "author_connection": "author_connection" in role_names,
            },
            "roles": roles,
            "opening_phrases": counts.most_common(5),
            "source_claims": source_claims,
            "cited_source_claims": cited_source_claims,
        }

    def summary(self, text: str) -> str:
        report = self.analyse(text)
        return f"{report['sentence_count']} sentences, {report['word_count']} words."

