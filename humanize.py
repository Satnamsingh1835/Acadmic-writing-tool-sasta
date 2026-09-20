"""Academic text humanization without changing the author's argument."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple


class HumanizeAI:
    """Conservatively revise AI-like academic prose into clearer prose."""

    DEFAULT_AI_PHRASES = (
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
        "multifaceted",
        "groundbreaking",
        "seamless",
        "robust and comprehensive",
    )

    DEFAULT_TRANSITIONS = {
        "furthermore": "also",
        "moreover": "also",
        "additionally": "also",
        "thus": "therefore",
        "hence": "therefore",
    }

    DEFAULT_WORDINESS = {
        r"\bin order to\b": "to",
        r"\bdue to the fact that\b": "because",
        r"\bdespite the fact that\b": "although",
        r"\bat this point in time\b": "currently",
        r"\bhas the ability to\b": "can",
        r"\bis able to\b": "can",
        r"\ba number of\b": "several",
        r"\bin the event that\b": "if",
        r"\bfor the purpose of\b": "for",
    }

    def __init__(
        self,
        *,
        remove_ai_phrases: bool = True,
        simplify_wordiness: bool = True,
        soften_absolute_claims: bool = False,
    ) -> None:
        self.remove_ai_phrases = remove_ai_phrases
        self.simplify_wordiness = simplify_wordiness
        self.soften_absolute_claims = soften_absolute_claims

    @staticmethod
    def _protect(text: str) -> Tuple[str, List[str]]:
        """Protect URLs, citations, and quoted text."""
        protected: List[str] = []
        patterns = [
            r"https?://\S+",
            r"\b(?:doi:)?10\.\d{4,9}/[-._;()/:A-Z0-9]+\b",
            r"\([^()]{0,120}\b(?:19|20)\d{2}[a-z]?\b[^()]{0,120}\)",
            r'"[^"]*"',
            r"'[^']*'",
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
        return [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ])", text.strip())
            if s.strip()
        ]

    @staticmethod
    def _capitalise_after_removal(text: str) -> str:
        text = re.sub(r"\s{2,}", " ", text).strip()
        if text:
            text = text[0].upper() + text[1:]
        return text

    def remove_ai_markers(self, text: str) -> str:
        """Remove formulaic AI framing while retaining the underlying claim."""
        for phrase in self.DEFAULT_AI_PHRASES:
            text = re.sub(
                rf"\b{re.escape(phrase)}\s*[:,]?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )
        return self._capitalise_after_removal(text)

    def simplify(self, text: str) -> str:
        """Reduce common wordiness without changing the proposition."""
        for pattern, replacement in self.DEFAULT_WORDINESS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def normalize_transitions(self, text: str) -> str:
        """Reduce formulaic paragraph transitions."""
        for source, target in self.DEFAULT_TRANSITIONS.items():
            text = re.sub(
                rf"^\s*{source}\s*[,;:]\s*",
                f"{target.capitalize()}, ",
                text,
                flags=re.IGNORECASE,
            )
        return text

    def vary_repetition(self, text: str) -> str:
        """Remove immediate word repetition only; never reorder sentences."""
        return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)

    def soften_claims(self, text: str) -> str:
        """Optionally soften categorical claims; disabled by default."""
        replacements = {
            r"\balways\b": "often",
            r"\bnever\b": "rarely",
            r"\bproves that\b": "suggests that",
            r"\bclearly demonstrates\b": "suggests",
            r"\bdefinitively shows\b": "indicates",
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def humanize_literature_review(self, text: str) -> str:
        """Entry point for literature-review prose; preserves paragraph boundaries."""
        return self.humanize(text)

    def humanize(self, text: str) -> str:
        """Return a conservative academic-style revision."""
        if not text or not text.strip():
            return text

        working, protected = self._protect(text.strip())

        if self.remove_ai_phrases:
            working = self.remove_ai_markers(working)
        if self.simplify_wordiness:
            working = self.simplify(working)

        sentences = self._sentences(working)
        sentences = [self.normalize_transitions(s) for s in sentences]
        working = " ".join(sentences)
        working = self.vary_repetition(working)

        if self.soften_absolute_claims:
            working = self.soften_claims(working)

        working = re.sub(r"[ \t]+", " ", working)
        working = re.sub(r"\n{3,}", "\n\n", working).strip()
        return self._restore(working, protected)


if __name__ == "__main__":
    example = (
        "It is important to note that caste plays a crucial role in shaping "
        "agrarian relations. Furthermore, this relationship is complex due to "
        "the fact that land relations change over time."
    )
    print(HumanizeAI().humanize(example))
