"""Researcher-decision layer for academic-writing suggestions.

Suggestions are proposed actions, not automatic edits. The state model makes
accept/modify/reject explicit so the researcher retains control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


VALID_DECISIONS = ("accept", "modify", "reject", "pending")


@dataclass
class ResearcherDecision:
    suggestion_id: str
    decision: str = "pending"
    revised_text: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in VALID_DECISIONS:
            raise ValueError(
                f"Decision must be one of: {', '.join(VALID_DECISIONS)}."
            )
        if self.decision == "modify" and not (self.revised_text or "").strip():
            raise ValueError("A modified decision requires revised_text.")


class DecisionLayer:
    """Create and apply explicit researcher decisions without hidden edits."""

    @staticmethod
    def proposal(suggestion_id: str, suggestion: Dict[str, object]) -> Dict[str, object]:
        return {
            "suggestion_id": suggestion_id,
            "original": suggestion.get("original"),
            "suggested_revision": suggestion.get("suggested_revision"),
            "why": suggestion.get("why"),
            "manual_check": True,
            "decision": "pending",
            "researcher_note": None,
        }

    @staticmethod
    def decide(
        suggestion_id: str,
        decision: str,
        revised_text: str | None = None,
        note: str | None = None,
    ) -> ResearcherDecision:
        return ResearcherDecision(
            suggestion_id=suggestion_id,
            decision=decision,
            revised_text=revised_text,
            note=note,
        )

    @staticmethod
    def apply(original: str, suggestion: Dict[str, object], decision: ResearcherDecision) -> str:
        if decision.suggestion_id != suggestion.get("suggestion_id"):
            raise ValueError("Decision does not match the suggestion.")

        if decision.decision == "accept":
            return str(suggestion.get("suggested_revision") or original)
        if decision.decision == "modify":
            return str(decision.revised_text)
        return original
