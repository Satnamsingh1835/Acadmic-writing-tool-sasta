from __future__ import annotations
import re
from typing import Dict, List, Optional
from advanced_humanize import AdvancedHumanizer
from academic_analyser import AcademicAnalyzer

class AcademicSuggestionEngine:
    def __init__(self, long_sentence_words: int = 35) -> None:
        self.analyzer = AcademicAnalyzer(long_sentence_words=long_sentence_words)
        self.editor = AdvancedHumanizer()

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return AcademicAnalyzer.sentences(text)

    @staticmethod
    def _word_count(text: str) -> int:
        return len(AcademicAnalyzer.words(text))

    def suggest(self, text: str, profile: str = "standard", revised_text: Optional[str] = None, analysis: Optional[Dict[str, object]] = None) -> List[Dict[str, object]]:
        if not isinstance(text, str): raise TypeError("text must be a string")
        if not text.strip(): return []
        revised_text = revised_text if revised_text is not None else self.editor.humanize_literature_review(text, profile)
        analysis = analysis or self.analyzer.analyse(text)
        original_sentences = self._sentences(text)
        revised_sentences = self._sentences(revised_text)
        long_sentences = {item["sentence"]: item["words"] for item in analysis["long_sentences"]}
        suggestions = []
        for index, original in enumerate(original_sentences, 1):
            revised = revised_sentences[index - 1] if len(revised_sentences) == len(original_sentences) else original
            lower = original.lower()
            formulaic = [p for p in AcademicAnalyzer.FORMULAIC if p in lower]
            overclaims = [p for p in AcademicAnalyzer.ABSOLUTES if p in lower]
            long = index in long_sentences
            if not (formulaic or overclaims or long or revised != original): continue
            why = "The opening uses formulaic academic phrasing that can be stated more directly." if formulaic else "The wording is categorical; check whether the evidence supports this strength of claim." if overclaims else "The sentence is long enough to risk obscuring its main claim." if long else "Selected wording can be made more concise without changing its intended meaning."
            suggestions.append({"sentence": index, "original": original, "issue": ", ".join(formulaic or overclaims) if formulaic or overclaims else f"{long_sentences[index]} words" if long else "Selected academic wording", "suggested_revision": revised, "why": why, "manual_check": True})
        return suggestions
