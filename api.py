"""HTTP API for the Academic Literature Review Assistant.

The API is deliberately conservative: it diagnoses structure, returns editorial
suggestions, and applies language-level revisions. It does not claim to determine
scholarly quality, verify sources, or generate an author's argument.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from academic_analyser import AcademicAnalyzer
from academic_suggestions import AcademicSuggestionEngine
from advanced_humanize import AdvancedHumanizer
from google_docs import GoogleDocsIntegration
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
google_integration = GoogleDocsIntegration()


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


class GoogleReviewRequest(BaseModel):
    document_id: str = Field(min_length=1)
    profile: str = Field(default="standard")
    include_refined_text: bool = True
    write_back: bool = False


def _normalize_profile(profile: str) -> str:
    """Accept the documented names and the aliases used by the editor."""
    aliases = {"light": "conservative", "medium": "standard", "heavy": "polish"}
    normalized = aliases.get(profile.lower(), profile.lower())
    if normalized not in editor.PROFILES:
        raise ValueError(
            f"Unknown profile '{profile}'. "
            f"Choose from: {', '.join(editor.PROFILES)}."
        )
    return normalized


def review_text(text: str, profile: str, include_refined_text: bool) -> ReviewResponse:
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text is empty.")
    try:
        profile_name = _normalize_profile(profile)
        refined = editor.humanize_literature_review(text, profile_name)
        suggestions = suggestion_engine.suggest(text, profile_name)
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


@app.get("/google/auth")
def google_auth() -> RedirectResponse:
    try:
        return RedirectResponse(url=google_integration.authorization_url())
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth client_secret.json is missing. Add it before using Google Docs.",
        ) from exc


@app.get("/google/callback")
def google_callback(code: str | None = None, error: str | None = None) -> dict:
    if error:
        raise HTTPException(status_code=400, detail=f"Google authorization failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Google auth callback missing a code parameter.")
    try:
        google_integration.finish_authorization(code)
    except Exception as exc:  # pragma: no cover - external OAuth dependency path
        raise HTTPException(status_code=400, detail=f"Could not complete Google authorization: {exc}") from exc
    return {"status": "authorized", "message": "Google Docs access connected successfully."}


@app.post("/google/review", response_model=ReviewResponse)
def review_google_document(request: GoogleReviewRequest) -> ReviewResponse:
    try:
        source_text = google_integration.read_document(request.document_id)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Google OAuth client file not found: {exc}") from exc
    except Exception as exc:  # pragma: no cover - external API issue
        raise HTTPException(status_code=400, detail=f"Could not read the Google document: {exc}") from exc

    if not source_text.strip():
        raise HTTPException(status_code=400, detail="The Google document is empty.")

    reviewed = review_text(source_text, request.profile, request.include_refined_text)
    if request.write_back and reviewed.refined_text:
        try:
            google_integration.replace_document(request.document_id, reviewed.refined_text)
        except Exception as exc:  # pragma: no cover - external API issue
            raise HTTPException(status_code=400, detail=f"Could not write back to Google Docs: {exc}") from exc
    return reviewed


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
