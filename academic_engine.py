from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from academic_analyser import AcademicAnalyzer
from academic_suggestions import AcademicSuggestionEngine
from advanced_humanize import AdvancedHumanizer
from argument_diagnostics import ArgumentDiagnostics
from literature_review import LiteratureReviewAnalyzer
from researcher_decisions import DecisionLayer


@dataclass
class ReviewResult:
    """Structured result for one academic-writing review."""

    refined_text: Optional[str]
    suggestions: list[dict]
    grammar_and_style: dict
    literature_review: dict
    safeguards: dict


class AcademicWritingEngine:
    """Orchestrate the specialist academic-writing components.

    The engine owns workflow composition; individual modules remain
    deterministic and independently testable.
    """

    def __init__(
        self,
        editor: AdvancedHumanizer | None = None,
        analyser: AcademicAnalyzer | None = None,
        suggestion_engine: AcademicSuggestionEngine | None = None,
        literature_review_analyser: LiteratureReviewAnalyzer | None = None,
        argument_diagnostics: ArgumentDiagnostics | None = None,
        decision_layer: DecisionLayer | None = None,
    ) -> None:
        self.editor = editor or AdvancedHumanizer()
        self.analyser = analyser or AcademicAnalyzer()
        self.suggestion_engine = suggestion_engine or AcademicSuggestionEngine()
        self.literature_review_analyser = (
            literature_review_analyser or LiteratureReviewAnalyzer()
        )
        self.argument_diagnostics = argument_diagnostics or ArgumentDiagnostics()
        self.decision_layer = decision_layer or DecisionLayer()

    def normalize_profile(self, profile: str) -> str:
        normalized = {
            "light": "conservative",
            "medium": "standard",
            "heavy": "polish",
        }.get(profile.lower(), profile.lower())

        if normalized not in self.editor.PROFILES:
            choices = ", ".join(self.editor.PROFILES)
            raise ValueError(
                f"Unknown profile '{profile}'. Choose from: {choices}."
            )
        return normalized

    def review(
        self,
        text: str,
        profile: str = "standard",
        include_refined_text: bool = True,
    ) -> ReviewResult:
        if not text.strip():
            raise ValueError("Text is empty.")

        profile_name = self.normalize_profile(profile)
        refined = self.editor.humanize_literature_review(text, profile_name)
        analysis = self.analyser.analyse(text)
        suggestions = self.suggestion_engine.suggest(
            text,
            profile_name,
            revised_text=refined,
            analysis=analysis,
        )
        suggestions = [
            {**item, **self.decision_layer.proposal(str(index), item)}
            for index, item in enumerate(suggestions, 1)
        ]
        literature_review = self.literature_review_analyser.analyse(
            text,
            analysis=analysis,
        )
        safeguards = self.editor.language_only_diagnostics(text, refined)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text.strip()) if p.strip()]
        for item, paragraph in zip(literature_review["paragraphs"], paragraphs):
            item["argument_diagnostics"] = self.argument_diagnostics.analyse(paragraph)

        return ReviewResult(
            refined_text=refined if include_refined_text else None,
            suggestions=suggestions,
            grammar_and_style=analysis,
            literature_review=literature_review,
            safeguards=safeguards,
        )
