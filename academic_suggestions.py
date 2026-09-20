"""Sentence-level editorial suggestions for academic literature-review prose.

The module is deliberately conservative. It identifies detectable language patterns,
shows a possible revision, and explains the reason. It does not claim to judge
scholarly quality or invent substantive arguments.
"""

from __future__ import annotations

import re
from typing import Dict, List

from advanced_humanize import AdvancedHumanizer
from academic_analyser import AcademicAnalyzer


class AcademicSuggestionEngine:
    """Generate sentence-level language suggestions for manual review."""

    def __init__(self, long_sentence_words: int = 35) -> None:
        self.analyzer = AcademicAnalyzer(long_sentence_words=long_sentence_words)
        self.editor = AdvancedHumanizer()

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ])", text.strip())
            if s.strip()
        ]

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\b[\w'-]+\b", text))

    @staticmethod
    def _category_for(sentence: str, revised: str, long_threshold: int) -> str:
        lower = sentence.lower()
        if any(p in lower for p in AcademicAnalyzer.FORMULAIC):
            return "Academic style / formulaic phrasing"
        if any(p in lower for p in AcademicAnalyzer.ABSOLUTES):
            return "Claim strength / evidentiary caution"
        if AcademicSuggestionEngine._word_count(sentence) >= long_threshold:
            return "Sentence clarity / length"
        if revised != sentence:
            return "Academic language / concision"
        return "Grammar / sentence clarity"

    def suggest(self, text: str, profile: str = "standard") -> List[Dict[str, object]]:
        """Return only sentences for which an editorial issue is detectable."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text.strip():
            return []

        try:
            revised_text = self.editor.humanize_literature_review(text, profile)
        except ValueError:
            raise

        original_sentences = self._sentences(text)
        revised_sentences = self._sentences(revised_text)
        analysis = self.analyzer.analyse(text)
        long_sentences = {
            item["sentence"]: item["words"] for item in analysis["long_sentences"]
        }

        suggestions: List[Dict[str, object]] = []
        for index, original in enumerate(original_sentences, 1):
            revised = (
                revised_sentences[index - 1]
                if len(revised_sentences) == len(original_sentences)
                else original
            )
            lower = original.lower()
            formulaic = [p for p in AcademicAnalyzer.FORMULAIC if p in lower]
            overclaims = [p for p in AcademicAnalyzer.ABSOLUTES if p in lower]
            long = index in long_sentences

            if not (formulaic or overclaims or long or revised != original):
                continue

            if formulaic:
                why = "The opening uses formulaic academic phrasing that can be stated more directly."
            elif overclaims:
                why = "The wording is categorical; check whether the evidence supports this strength of claim."
            elif long:
                why = "The sentence is long enough to risk obscuring its main subject, claim, or relationship between clauses."
            else:
                why = "The sentence contains selected wording that can be made more concise without changing its intended meaning."

            suggestions.append({
                "sentence": index,
                "original": original,
                "category": self._category_for(
                    original, revised, self.analyzer.long_sentence_words
                ),
                "issue": (
                    ", ".join(formulaic)
                    if formulaic else
                    ", ".join(overclaims)
                    if overclaims else
                    f"{long_sentences[index]} words"
                    if long else
                    "Selected academic wording"
                ),
                "suggested_revision": revised,
                "why": why,
                "confidence": "high" if formulaic or revised != original else "medium",
                "manual_check": True,
            })

        return suggestions
