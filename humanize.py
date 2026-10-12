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

    AI_MARKER_REPLACEMENTS = (
        (r"\bplays a (?:crucial|vital) role in shaping\b", "shapes"),
        (r"\bplay a (?:crucial|vital) role in shaping\b", "shape"),
        (r"\bplays a (?:crucial|vital) role in\b", "shapes"),
        (r"\bplay a (?:crucial|vital) role in\b", "shape"),
        (r"\bprovides? a deep dive into\b", "examines"),
        (r"\bdelves? into\b", "examines"),
        (r"\bdeep dive into\b", "detailed examination of"),
        (r"\bsheds? light on\b", "examines"),
        (r"\ba plethora of\b", "many"),
        (r"\ba wide range of\b", "many"),
        (r"\bin the realm of\b", "in"),
        (r"\bin today's world\b", "currently"),
        (r"\bin the modern era\b", "currently"),
        (r"\bmultifaceted\b", "complex"),
        (r"\brobust and comprehensive\b", "detailed"),
    )
    AI_MARKERS_TO_REMOVE = (
        "it is important to note that",
        "it is worth noting that",
        "it should be noted that",
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
        """Replace formulaic wording without leaving grammatical fragments."""
        for pattern, replacement in self.AI_MARKER_REPLACEMENTS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        for phrase in self.AI_MARKERS_TO_REMOVE:
            text = re.sub(
                rf"\b{re.escape(phrase)}\s*[:,]?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )
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
        def sentence_count(value: str) -> int:
            return len(HumanizeAI._sentences(value))

        def paragraph_count(value: str) -> int:
            return len(
                [
                    paragraph
                    for paragraph in re.split(r"\n\s*\n+", value.strip())
                    if paragraph.strip()
                ]
            )

        def citation_list(value: str) -> list[str]:
            return re.findall(
                r"\([^()]{0,120}\b(?:19|20)\d{2}[a-z]?\b[^()]{0,120}\)",
                value,
            )

        return {
            "paragraph_count_preserved": (
                paragraph_count(original) == paragraph_count(revised)
            ),
            "sentence_count_preserved": sentence_count(original) == sentence_count(revised),
            "citations_preserved": citation_list(original) == citation_list(revised),
            "requires_manual_semantic_check": True,
            "note": (
                "Structural checks are safeguards, not proof that the author's "
                "meaning or argument is unchanged."
            ),
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
