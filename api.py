"""HTTP API for the Academic Literature Review Assistant.

The API is deliberately conservative: it diagnoses structure, returns editorial
suggestions, and applies language-level revisions. It does not claim to determine
scholarly quality, verify sources, or generate an author's argument.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from academic_analyser import AcademicAnalyzer
from academic_suggestions import AcademicSuggestionEngine
from advanced_humanize import AdvancedHumanizer
from literature_review import LiteratureReviewAnalyzer


app = FastAPI(
    title="Academic Literature Review Assistant API",
    version="1.1.0",
    description=(
        "Tools for reading text files, identifying grammar and academic-language "
        "issues, diagnosing literature-review structure, and producing a conservative draft."
    ),
)

editor = AdvancedHumanizer()
analyser = AcademicAnalyzer()
suggestion_engine = AcademicSuggestionEngine()
lr_analyser = LiteratureReviewAnalyzer()


class ReviewRequest(BaseModel):
    text: str = Field(min_length=1)
    profile: str = Field(default="standard")
    include_refined_text: bool = True


class ReviewResponse(BaseModel):
    refined_text: Optional[str]
    suggestions: list[dict]
    grammar_and_style: dict
    literature_review: dict
    safeguards: dict


def review_text(text: str, profile: str, include_refined_text: bool) -> ReviewResponse:
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text is empty.")
    try:
        refined = editor.humanize_literature_review(text, profile)
        suggestions = suggestion_engine.suggest(text, profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ReviewResponse(
        refined_text=refined if include_refined_text else None,
        suggestions=suggestions,
        grammar_and_style=analyser.analyse(text),
        literature_review=lr_analyser.analyse(text),
        safeguards=editor.language_only_diagnostics(text, refined),
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "academic-literature-review-assistant"}


@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest) -> ReviewResponse:
    """Review pasted text and optionally return a language-refined version."""
    return review_text(request.text, request.profile, request.include_refined_text)


@app.post("/review/file", response_model=ReviewResponse)
async def review_file(
    file: UploadFile = File(...),
    profile: str = "standard",
    include_refined_text: bool = True,
) -> ReviewResponse:
    """Read a UTF-8 .txt file and return suggestions, diagnostics, and a refined draft."""
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="This endpoint currently accepts UTF-8 .txt files only.",
        )

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file must be UTF-8 encoded.",
        ) from exc

    return review_text(text, profile, include_refined_text)
