from __future__ import annotations
import os
from typing import Optional
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from academic_analyser import AcademicAnalyzer
from academic_suggestions import AcademicSuggestionEngine
from advanced_humanize import AdvancedHumanizer
from literature_review import LiteratureReviewAnalyzer

MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "500000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "2000000"))
app = FastAPI(title="Academic Literature Review Assistant API", version="1.2.0")
editor, analyser, suggestion_engine, lr_analyser = AdvancedHumanizer(), AcademicAnalyzer(), AcademicSuggestionEngine(), LiteratureReviewAnalyzer()

class ReviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    profile: str = "standard"
    include_refined_text: bool = True
class ReviewResponse(BaseModel):
    refined_text: Optional[str]
    suggestions: list[dict]
    grammar_and_style: dict
    literature_review: dict
    safeguards: dict

def _normalize_profile(profile: str) -> str:
    normalized = {"light":"conservative", "medium":"standard", "heavy":"polish"}.get(profile.lower(), profile.lower())
    if normalized not in editor.PROFILES: raise ValueError(f"Unknown profile '{profile}'. Choose from: {', '.join(editor.PROFILES)}.")
    return normalized

def review_text(text: str, profile: str, include_refined_text: bool) -> ReviewResponse:
    if not text.strip(): raise HTTPException(400, "Text is empty.")
    if len(text) > MAX_TEXT_CHARS: raise HTTPException(413, f"Text exceeds the {MAX_TEXT_CHARS}-character limit.")
    try: profile_name = _normalize_profile(profile)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    refined = editor.humanize_literature_review(text, profile_name)
    analysis = analyser.analyse(text)
    suggestions = suggestion_engine.suggest(text, profile_name, revised_text=refined, analysis=analysis)
    return ReviewResponse(refined_text=refined if include_refined_text else None, suggestions=suggestions, grammar_and_style=analysis, literature_review=lr_analyser.analyse(text, analysis=analysis), safeguards=editor.language_only_diagnostics(text, refined))

@app.get("/health")
def health(): return {"status":"ok", "service":"academic-literature-review-assistant", "max_text_chars":MAX_TEXT_CHARS}

@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest): return review_text(request.text, request.profile, request.include_refined_text)

@app.post("/review/file", response_model=ReviewResponse)
async def review_file(file: UploadFile = File(...), profile: str = "standard", include_refined_text: bool = True):
    if not file.filename or not file.filename.lower().endswith(".txt"): raise HTTPException(400, "This endpoint accepts UTF-8 .txt files only.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES: raise HTTPException(413, f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte limit.")
    try: text = raw.decode("utf-8")
    except UnicodeDecodeError as exc: raise HTTPException(400, "The uploaded file must be UTF-8 encoded.") from exc
    return await run_in_threadpool(review_text, text, profile, include_refined_text)
