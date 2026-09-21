"""Neutral diagnostics for paragraph-level literature-review reasoning.

The module identifies observable rhetorical relationships. It does not score,
rank, or certify the scholarly quality of a paragraph.
"""

from __future__ import annotations

import re
from typing import Dict


class ArgumentDiagnostics:
    """Turn literature-review signals into researcher-facing questions."""

    RELATIONSHIPS = {
        "agreement": r"\b(?:similarly|likewise|consistent with|supports?|reinforces?)\b",
        "extension": r"\b(?:extends?|builds? on|develops?|adds? to)\b",
        "contrast": r"\b(?:however|whereas|while|in contrast|by contrast|challenges?|differs?)\b",
        "qualification": r"\b(?:qualifies?|complicates?|conditional|depends? on|context[- ]dependent)\b",
        "temporal_change": r"\b(?:over time|historically|changed?|transformed?|reconfigured?|reshaped?)\b",
    }

    GAP_PATTERNS = (
        r"\b(?:little is known|few studies|limited attention|underexplored|"
        r"unexplored|remains unclear|remains under|gap|yet|however)\b",
    )

    CONNECTION_PATTERNS = (
        r"\b(?:this study|this research|the present study|this paper|"
        r"i argue|i examine|i explore|research question)\b",
    )

    def analyse(self, paragraph: str) -> Dict[str, object]:
        if not isinstance(paragraph, str) or not paragraph.strip():
            raise ValueError("Paragraph must be a non-empty string.")

        relationships = {
            name: bool(re.search(pattern, paragraph, re.IGNORECASE))
            for name, pattern in self.RELATIONSHIPS.items()
        }
        gap_signal = any(
            re.search(pattern, paragraph, re.IGNORECASE)
            for pattern in self.GAP_PATTERNS
        )
        connection_signal = any(
            re.search(pattern, paragraph, re.IGNORECASE)
            for pattern in self.CONNECTION_PATTERNS
        )

        questions = []
        if not any(relationships.values()):
            questions.append(
                "What relationship between the studies should be made explicit: "
                "agreement, extension, contrast, qualification, or temporal change?"
            )
        if not gap_signal:
            questions.append(
                "After synthesising the literature, what remains unresolved or underexplored?"
            )
        if not connection_signal:
            questions.append(
                "How does the unresolved issue connect to the research question?"
            )

        return {
            "relationships": relationships,
            "has_explicit_relationship": any(relationships.values()),
            "has_gap_signal": gap_signal,
            "has_research_connection": connection_signal,
            "researcher_questions": questions,
            "note": "These are editorial prompts based on textual signals, not scholarly-quality scores.",
        }
