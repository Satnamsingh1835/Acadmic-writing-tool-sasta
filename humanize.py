"""Academic text humanization without changing the author's argument."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple


class HumanizeAI:
    """Conservatively revise AI-like academic prose into clearer prose."""

    DEFAULT_AI_PHRASES = (
        "it is important to note that", "it is worth noting that",
        "it should be noted that", "in today's world", "in the modern era",
        "in the realm of", "a wide range of", "a plethora of",
        "plays a crucial role in", "plays a vital role in", "delve into",
        "delves into", "deep dive into", "shed light on", "multifaceted",
        "groundbreaking", "seamless", "robust and comprehensive",
    )

    DEFAULT_BRITISH = {
        r"\banalyzes\b": "analyses", r"\banalyze\b": "analyse",
        r"\bbehavior\b": "behaviour", r"\bcentered\b": "centred",
        r"\bcontextualized\b": "contextualised", r"\bconceptualized\b": "conceptualised",
        r"\bcriticized\b": "criticised", r"\bdecentralized\b": "decentralised",
        r"\bemphasized\b": "emphasised", r"\bemphasize\b": "emphasise",
        r"\bemphasizes\b": "emphasises",
        r"\bfavor\b": "favour", r"\bfavored\b": "favoured",
        r"\bglobalization\b": "globalisation", r"\bmaximize\b": "maximise",
        r"\bminimize\b": "minimise", r"\borganize\b": "organise",
        r"\borganized\b": "organised", r"\brecognize\b": "recognise",
        r"\btheorize\b": "theorise",
    }

    DEFAULT_WORDINESS = {
        r"\bin order to\b": "to", r"\bdue to the fact that\b": "because",
        r"\bdespite the fact that\b": "although", r"\bat this point in time\b": "currently",
        r"\bhas the ability to\b": "can", r"\bis able to\b": "can",
        r"\ba number of\b": "several", r"\bin the event that\b": "if",
        r"\bfor the purpose of\b": "for",
    }

    def __init__(self, *, remove_ai_phrases: bool = True,
                 simplify_wordiness: bool = True,
                 soften_absolute_claims: bool = False,
                 british_english: bool = True) -> None:
        self.remove_ai_phrases = remove_ai_phrases
        self.simplify_wordiness = simplify_wordiness
        self.soften_absolute_claims = soften_absolute_claims
        self.british_english = british_english

    @staticmethod
    def _protect(text: str) -> Tuple[str, List[str]]:
        """Protect URLs, DOIs, citations, and quoted text."""
        protected: List[str] = []
        patterns = [
            r"https?://\S+",
            r"\b(?:doi:)?10\.\d{4,9}/[-._;()/:A-Z0-9]+\b",
            r"\([^()]{0,120}\b(?:19|20)\d{2}[a-z]?\b[^()]{0,120}\)",
            r'"[^"]*"', r"'[^']*'",
        ]

        def repl(match: re.Match[str]) -> str:
            token = f"___ACADEMIC_PROTECTED_{len(protected)}___"
            protected.append(match.group(0))
            return token

        for pattern in patterns:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text, protected

    @staticmethod
    def _restore(text: str, protected: Iterable[str]) -> str:
        for i, value in enumerate(protected):
            text = text.replace(f"___ACADEMIC_PROTECTED_{i}___", value)
        return text

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [s.strip() for s in re.split(
            r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ])", text.strip()
        ) if s.strip()]

    @staticmethod
    def _capitalise_after_removal(text: str) -> str:
        text = re.sub(r"\s{2,}", " ", text).strip()
        return text[:1].upper() + text[1:] if text else text

    def remove_ai_markers(self, text: str) -> str:
        for phrase in self.DEFAULT_AI_PHRASES:
            text = re.sub(rf"\b{re.escape(phrase)}\s*[:,]?\s*", "", text, flags=re.IGNORECASE)
        return self._capitalise_after_removal(text)

    def britishize(self, text: str) -> str:
        if not self.british_english:
            return text
        for pattern, replacement in self.DEFAULT_BRITISH.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def simplify(self, text: str) -> str:
        for pattern, replacement in self.DEFAULT_WORDINESS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def soften_claims(self, text: str) -> str:
        replacements = {
            r"\balways\b": "often", r"\bnever\b": "rarely",
            r"\bproves that\b": "suggests that",
            r"\bclearly demonstrates\b": "suggests",
            r"\bdefinitively shows\b": "indicates",
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def language_only_diagnostics(original: str, revised: str) -> dict:
        """Check structural invariants after a language-only edit."""
        sentence_count = lambda value: len(HumanizeAI._sentences(value))
        paragraph_count = lambda value: len(
            [p for p in re.split(r"\n\s*\n+", value.strip()) if p.strip()]
        )
        citations = lambda value: re.findall(
            r"\([^()]{0,120}\b(?:19|20)\d{2}[a-z]?\b[^()]{0,120}\)",
            value,
        )
        return {
            "paragraph_count_preserved": paragraph_count(original) == paragraph_count(revised),
            "sentence_count_preserved": sentence_count(original) == sentence_count(revised),
            "citations_preserved": citations(original) == citations(revised),
            "requires_manual_semantic_check": True,
            "note": "Structural checks are safeguards, not proof that the author's meaning or argument is unchanged.",
        }

    def humanize_literature_review(self, text: str) -> str:
        """Language-only editing entry point; paragraph and sentence order are retained."""
        return self.humanize(text)

    def humanize(self, text: str) -> str:
        """Revise wording only; never reorder or generate substantive content."""
        if not text or not text.strip():
            return text

        working, protected = self._protect(text.strip())
        paragraphs = re.split(r"\n\s*\n", working)

        revised = []
        for paragraph in paragraphs:
            if self.remove_ai_phrases:
                paragraph = self.remove_ai_markers(paragraph)
            if self.simplify_wordiness:
                paragraph = self.simplify(paragraph)
            paragraph = self.britishize(paragraph)
            if self.soften_absolute_claims:
                paragraph = self.soften_claims(paragraph)
            paragraph = re.sub(r"[ \t]+", " ", paragraph).strip()
            revised.append(paragraph)

        return self._restore("\n\n".join(revised).strip(), protected)
