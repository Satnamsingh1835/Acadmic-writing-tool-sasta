"""Paragraph-level diagnostics for academic literature reviews.

This module does not write or score scholarship. It identifies common rhetorical
roles and gives the author neutral editorial questions for manual revision.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from academic_analyser import AcademicAnalyzer


class LiteratureReviewAnalyzer:
    """Analyse paragraph logic without repeating document-level analysis."""

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
        "agreement_or_extension": re.compile(r"\b(?:similarly|likewise|also|extends?|builds? on|supports?|reinforces?|complements?)\b", re.I),
        "contrast_or_tension": re.compile(r"\b(?:however|whereas|while|in contrast|by contrast|challenges?|disputes?|differs?|contrasts?|tension|divergence|competing)\b", re.I),
        "qualification_or_condition": re.compile(r"\b(?:qualifies?|complicates?|conditional|contingent|depends? on|varies?|variation|context[- ]dependent)\b", re.I),
        "temporal_reconfiguration": re.compile(r"\b(?:over time|historically|historical(?:ly)?|changes?|transformed?|reconfigured?|reproduced?|reshaped?)\b", re.I),
        "debate_language": re.compile(r"\b(?:debate|disagreement|contested|competing|divergence|tension|controversy|dispute)\b", re.I),
    }
    AUTHOR_SIGNAL = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b|\b(?:argues?|finds?|found|shows?|observes?|documents?|examines?|suggests?)\b", re.I)
    AUTHOR_CONNECTION = re.compile(r"\b(?:this study|this research|the present study|this paper|i argue|i examine|i explore)\b", re.I)
    PARAGRAPH_RE = re.compile(r"\n\s*\n+")
    YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.I)
    # Keep the parenthetical scan bounded so CodeQL cannot classify it as ReDoS-prone.
    PARENTHETICAL_YEAR_RE = re.compile(
        r"\([^()\r\n]{0,500}\b(?:19|20)\d{2}[a-z]?\b[^()\r\n]{0,500}\)",
        re.I,
    )

    def __init__(self, long_sentence_words: int = 35) -> None:
        self.analyzer = AcademicAnalyzer(long_sentence_words=long_sentence_words)

    @classmethod
    def _paragraphs(cls, text: str) -> List[str]:
        return [p.strip() for p in cls.PARAGRAPH_RE.split(text.strip()) if p.strip()]

    @classmethod
    def _source_count(cls, paragraph: str) -> int:
        years = cls.YEAR_RE.findall(paragraph)
        parenthetical = cls.PARENTHETICAL_YEAR_RE.findall(paragraph)
        return max(len(set(years)), len(parenthetical))

    def _synthesis_diagnostics(self, paragraph: str) -> Dict[str, object]:
        source_count = self._source_count(paragraph)
        signals = {name: bool(pattern.search(paragraph)) for name, pattern in self.SYNTHESIS_PATTERNS.items()}
        explicit_synthesis = any(signals.values())
        source_listing = source_count >= 2 and not explicit_synthesis
        return {
            "source_count": source_count,
            "signals": signals,
            "multiple_sources": source_count >= 2,
            "explicit_synthesis_signal": explicit_synthesis,
            "possible_source_listing": source_listing,
            "editorial_prompt": (
                "What relationship exists between the studies cited here? Identify agreement, disagreement, "
                "extension, qualification, or contextual variation rather than only listing their findings."
                if source_listing else None
            ),
        }

    def analyse_paragraph(
        self,
        paragraph: str,
        analysis: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Analyse one paragraph, optionally reusing a precomputed report."""
        report = analysis if analysis is not None else self.analyzer.analyse(paragraph)
        signals = report["literature_review_signals"]
        synthesis = self._synthesis_diagnostics(paragraph)
        return {
            "signals": {
                "source_or_evidence": bool(signals["source_or_evidence"] or self.AUTHOR_SIGNAL.search(paragraph)),
                "interpretation": bool(signals["interpretation"]),
                "comparison_or_synthesis": bool(signals["comparison_or_synthesis"] or synthesis["explicit_synthesis_signal"]),
                "gap": bool(signals["gap"]),
                "author_connection": bool(self.AUTHOR_CONNECTION.search(paragraph)),
            },
            "sentence_roles": report["roles"],
            "possible_overclaims": report["possible_overclaims"],
            "long_sentences": report["long_sentences"],
            "citation_count": report["citation_count"],
            "synthesis_diagnostics": synthesis,
        }

    def analyse(
        self,
        text: str,
        analysis: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Analyse paragraphs and reuse document analysis when it covers one paragraph."""
        paragraphs = self._paragraphs(text)
        results = []
        for number, paragraph in enumerate(paragraphs, 1):
            paragraph_analysis = analysis if analysis is not None and len(paragraphs) == 1 else None
            report = self.analyse_paragraph(paragraph, paragraph_analysis)
            missing = [key for key in self.REQUIRED_FLOW if not report["signals"][key]]
            results.append({
                "paragraph": number,
                "signals": report["signals"],
                "missing": missing,
                "editorial_prompts": [self.PROMPTS[key] for key in missing],
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
            lines.append(
                f"Paragraph {item['paragraph']}: review {', '.join(missing)}."
                if missing
                else f"Paragraph {item['paragraph']}: all tracked literature-review roles detected."
            )
            if item["synthesis_diagnostics"]["possible_source_listing"]:
                lines.append(
                    f"Paragraph {item['paragraph']}: multiple sources may be listed without an explicit synthesis relationship."
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
