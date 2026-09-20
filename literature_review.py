"""Paragraph-level diagnostics for academic literature reviews.

This module does not write or score scholarship. It identifies common rhetorical
roles and gives the author neutral editorial questions for manual revision.
"""

from __future__ import annotations

import re
from typing import Dict, List

from academic_analyser import AcademicAnalyzer


class LiteratureReviewAnalyzer:
    """Analyse paragraph logic: source -> claim -> interpretation -> synthesis -> gap -> connection."""

    REQUIRED_FLOW = (
        "source_or_evidence",
        "interpretation",
        "comparison_or_synthesis",
        "gap",
        "author_connection",
    )

    PROMPTS = {
        "source_or_evidence": "Which author or study establishes the claim, and what evidence does it provide?",
        "interpretation": "What does the evidence mean for the debate rather than merely what does the source report?",
        "comparison_or_synthesis": "How does this study relate to, extend, qualify, or challenge the studies already discussed?",
        "gap": "What remains unexplained, underexplored, or unresolved in the literature?",
        "author_connection": "How does this unresolved issue connect to the question this study will investigate?",
    }

    def __init__(self, long_sentence_words: int = 35) -> None:
        self.analyzer = AcademicAnalyzer(long_sentence_words=long_sentence_words)

    @staticmethod
    def _paragraphs(text: str) -> List[str]:
        return [p.strip() for p in re.split(r"\n\s*\n+", text.strip()) if p.strip()]

    @staticmethod
    def _author_signal(paragraph: str) -> bool:
        patterns = (
            r"\b(?:19|20)\d{2}[a-z]?\b",
            r"\b(?:argues?|finds?|found|shows?|observes?|documents?|examines?|suggests?)\b",
        )
        return any(re.search(p, paragraph, re.IGNORECASE) for p in patterns)

    def analyse_paragraph(self, paragraph: str) -> Dict[str, object]:
        report = self.analyzer.analyse(paragraph)
        signals = report["literature_review_signals"]
        author_connection = bool(
            re.search(
                r"\b(?:this study|this research|the present study|this paper|i argue|i examine|i explore)\b",
                paragraph,
                re.IGNORECASE,
            )
        )

        return {
            "signals": {
                "source_or_evidence": bool(signals["source_or_evidence"] or self._author_signal(paragraph)),
                "interpretation": bool(signals["interpretation"]),
                "comparison_or_synthesis": bool(signals["comparison_or_synthesis"]),
                "gap": bool(signals["gap"]),
                "author_connection": author_connection,
            },
            "sentence_roles": report["roles"],
            "possible_overclaims": report["possible_overclaims"],
            "long_sentences": report["long_sentences"],
            "citation_count": report["citation_count"],
        }

    def analyse(self, text: str) -> Dict[str, object]:
        paragraphs = self._paragraphs(text)
        results = []

        for number, paragraph in enumerate(paragraphs, 1):
            report = self.analyse_paragraph(paragraph)
            missing = [k for k in self.REQUIRED_FLOW if not report["signals"][k]]
            prompts = [self.PROMPTS[k] for k in missing]
            results.append(
                {
                    "paragraph": number,
                    "signals": report["signals"],
                    "missing": missing,
                    "editorial_prompts": prompts,
                    "citation_count": report["citation_count"],
                    "possible_overclaims": report["possible_overclaims"],
                    "long_sentences": report["long_sentences"],
                    "sentence_roles": report["sentence_roles"],
                }
            )

        return {
            "paragraph_count": len(results),
            "paragraphs": results,
            "note": "Signals are heuristic prompts for author review, not evaluations of scholarly quality.",
        }

    def summary(self, text: str) -> str:
        report = self.analyse(text)
        lines = [f"{report['paragraph_count']} paragraph(s) analysed."]
        for item in report["paragraphs"]:
            missing = item["missing"]
            if missing:
                lines.append(
                    f"Paragraph {item['paragraph']}: review " + ", ".join(missing) + "."
                )
            else:
                lines.append(
                    f"Paragraph {item['paragraph']}: all tracked literature-review roles detected."
                )
        return "\n".join(lines)


if __name__ == "__main__":
    sample = (
        "Jodhka (2004) examines caste and land relations. "
        "This suggests that land relations cannot be separated from caste. "
        "However, other studies identify regional variation.\n\n"
        "This study examines how these relations are reconfigured."
    )
    print(LiteratureReviewAnalyzer().summary(sample))
