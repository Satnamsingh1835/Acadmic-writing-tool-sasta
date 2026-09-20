"""Diagnostic analysis for academic prose.

This module does not rewrite text. It identifies patterns a writer may want
to review before or after using the academic humanizer.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List


class AcademicAnalyzer:
    """Conservative, deterministic diagnostics for academic paragraphs."""

    FORMULAIC = (
        "it is important to note that",
        "it is worth noting that",
        "it should be noted that",
        "in today's world",
        "in the modern era",
        "in the realm of",
        "a wide range of",
        "a plethora of",
        "plays a crucial role in",
        "plays a vital role in",
        "delve into",
        "delves into",
        "deep dive into",
        "shed light on",
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

    ARGUMENT_SIGNALS = (
        "however",
        "although",
        "whereas",
        "because",
        "therefore",
        "thus",
        "hence",
        "suggests",
        "indicates",
        "argues",
        "demonstrates",
        "shows",
        "implies",
        "while",
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

    def _formulaic(self, text: str) -> List[str]:
        lower = text.lower()
        return [phrase for phrase in self.FORMULAIC if phrase in lower]

    def _overclaims(self, text: str) -> List[str]:
        lower = text.lower()
        return [phrase for phrase in self.ABSOLUTES if phrase in lower]

    def _repetitive_openings(self, sentences: List[str]) -> Dict[str, int]:
        openings = []
        for sentence in sentences:
            words = self._words(sentence)
            if words:
                openings.append(" ".join(words[:2]))
        counts = Counter(openings)
        return {opening: count for opening, count in counts.items() if count > 1}

    def _transition_count(self, text: str) -> int:
        lower = text.lower()
        return sum(len(re.findall(r"\b" + re.escape(term) + r"\b", lower))
                   for term in self.ARGUMENT_SIGNALS)

    def _long_sentences(self, sentences: List[str]) -> List[Dict[str, object]]:
        result = []
        for index, sentence in enumerate(sentences, start=1):
            count = len(self._words(sentence))
            if count >= self.long_sentence_words:
                result.append({"sentence": index, "words": count, "text": sentence})
        return result

    def _argument_signals(self, text: str) -> List[str]:
        lower = text.lower()
        return [
            term for term in self.ARGUMENT_SIGNALS
            if re.search(r"\b" + re.escape(term) + r"\b", lower)
        ]

    def analyse(self, text: str) -> Dict[str, object]:
        """Return deterministic diagnostics without changing the input."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        sentences = self._sentences(text)
        words = self._words(text)

        return {
            "sentence_count": len(sentences),
            "word_count": len(words),
            "formulaic_phrases": self._formulaic(text),
            "possible_overclaims": self._overclaims(text),
            "repetitive_openings": self._repetitive_openings(sentences),
            "argument_signal_count": self._transition_count(text),
            "argument_signals_present": self._argument_signals(text),
            "long_sentences": self._long_sentences(sentences),
            "citation_count": len(re.findall(r"\([^()]*\b(?:19|20)\d{2}[a-z]?\b[^()]*\)", text)),
        }

    def summary(self, text: str) -> str:
        """Return a short human-readable diagnostic summary."""
        report = self.analyse(text)
        messages = [
            f"{report['sentence_count']} sentences, {report['word_count']} words."
        ]

        if report["formulaic_phrases"]:
            messages.append(
                "Formulaic phrases: " + ", ".join(report["formulaic_phrases"]) + "."
            )
        if report["possible_overclaims"]:
            messages.append(
                "Possible overclaims: " + ", ".join(report["possible_overclaims"]) + "."
            )
        if report["repetitive_openings"]:
            messages.append(
                "Repeated sentence openings: "
                + ", ".join(
                    f"{key} ({value})"
                    for key, value in report["repetitive_openings"].items()
                )
                + "."
            )
        if report["long_sentences"]:
            messages.append(
                f"{len(report['long_sentences'])} sentence(s) exceed "
                f"{self.long_sentence_words} words."
            )

        if len(messages) == 1:
            messages.append("No predefined warning patterns detected.")

        return " ".join(messages)


if __name__ == "__main__":
    sample = (
        "It is important to note that caste relations play a crucial role in "
        "agrarian change. However, this argument should be examined carefully."
    )
    analyzer = AcademicAnalyzer()
    print(analyzer.summary(sample))
