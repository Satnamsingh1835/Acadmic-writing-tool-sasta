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

    SYNTHESIS_PATTERNS = {
        "agreement_or_extension": r"\b(?:similarly|likewise|also|extends?|builds? on|supports?|reinforces?|complements?)\b",
        "contrast_or_tension": r"\b(?:however|whereas|while|in contrast|by contrast|challenges?|disputes?|differs?|contrasts?|tension|divergence|competing)\b",
        "qualification_or_condition": r"\b(?:qualifies?|complicates?|conditional|contingent|depends? on|varies?|variation|context[- ]dependent)\b",
        "temporal_reconfiguration": r"\b(?:over time|historically|historical(?:ly)?|changes?|transformed?|reconfigured?|reproduced?|reshaped?)\b",
        "debate_language": r"\b(?:debate|disagreement|contested|competing|divergence|tension|controversy|dispute)\b",
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

    @staticmethod
    def _source_count(paragraph: str) -> int:
        years = re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", paragraph, re.IGNORECASE)
        parenthetical = re.findall(r"\([^)]*(?:19|20)\d{2}[a-z]?[^)]*\)", paragraph)
        return max(len(set(years)), len(parenthetical))

    def _synthesis_diagnostics(self, paragraph: str) -> Dict[str, object]:
        source_count = self._source_count(paragraph)
        signals = {
            name: bool(re.search(pattern, paragraph, re.IGNORECASE))
            for name, pattern in self.SYNTHESIS_PATTERNS.items()
        }
        comparison_signal = any(signals.values())
        source_listing = source_count >= 2 and not comparison_signal
        return {
            "source_count": source_count,
            "signals": signals,
            "multiple_sources": source_count >= 2,
            "explicit_synthesis_signal": comparison_signal,
            "possible_source_listing": source_listing,
            "editorial_prompt": (
                "What relationship exists between the studies cited here? "
                "Identify agreement, disagreement, extension, qualification, or contextual variation "
                "rather than only listing their findings."
                if source_listing else None
            ),
        }

    def analyse_paragraph(self, paragraph: str) -> Dict[str, object]:
        report = self.analyzer.analyse(paragraph)
        signals = report["literature_review_signals"]
        author_connection = bool(re.search(
            r"\b(?:this study|this research|the present study|this paper|i argue|i examine|i explore)\b",
            paragraph, re.IGNORECASE
        ))
        synthesis = self._synthesis_diagnostics(paragraph)
        return {
            "signals": {
                "source_or_evidence": bool(signals["source_or_evidence"] or self._author_signal(paragraph)),
                "interpretation": bool(signals["interpretation"]),
                "comparison_or_synthesis": bool(signals["comparison_or_synthesis"] or synthesis["explicit_synthesis_signal"]),
                "gap": bool(signals["gap"]),
                "author_connection": author_connection,
            },
            "sentence_roles": report["roles"],
            "possible_overclaims": report["possible_overclaims"],
            "long_sentences": report["long_sentences"],
            "citation_count": report["citation_count"],
            "synthesis_diagnostics": synthesis,
        }

    def analyse(self, text: str, analysis: Dict[str, object] | None = None) -> Dict[str, object]:
        paragraphs = self._paragraphs(text)
        results = []
        for number, paragraph in enumerate(paragraphs, 1):
            report = self.analyse_paragraph(paragraph)
            missing = [k for k in self.REQUIRED_FLOW if not report["signals"][k]]
            results.append({
                "paragraph": number,
                "signals": report["signals"],
                "missing": missing,
                "editorial_prompts": [self.PROMPTS[k] for k in missing],
                "citation_count": report["citation_count"],
                "possible_overclaims": report["possible_overclaims"],
                "long_sentences": report["long_sentences"],
                "sentence_roles": report["sentence_roles"],
                "synthesis_diagnostics": report["synthesis_diagnostics"],
            })
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
                lines.append(f"Paragraph {item['paragraph']}: review " + ", ".join(missing) + ".")
            else:
                lines.append(f"Paragraph {item['paragraph']}: all tracked literature-review roles detected.")
            if item["synthesis_diagnostics"]["possible_source_listing"]:
                lines.append(f"Paragraph {item['paragraph']}: multiple sources may be listed without an explicit synthesis relationship.")
        return "\n".join(lines)


if __name__ == "__main__":
    sample = (
        "Jodhka (2004) examines caste and land relations. "
        "This suggests that land relations cannot be separated from caste. "
        "However, other studies identify regional variation.\n\n"
        "This study examines how these relations are reconfigured."
    )
    print(LiteratureReviewAnalyzer().summary(sample))
