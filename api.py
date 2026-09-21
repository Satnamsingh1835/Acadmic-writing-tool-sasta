from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from academic_engine import AcademicWritingEngine

MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "500000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "2000000"))

app = FastAPI(
    title="Academic Literature Review Assistant API",
    version="1.3.0",
)
engine = AcademicWritingEngine()


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


def review_text(
    text: str,
    profile: str,
    include_refined_text: bool,
) -> ReviewResponse:
    if not text.strip():
        raise HTTPException(400, "Text is empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            413,
            f"Text exceeds the {MAX_TEXT_CHARS}-character limit.",
        )

    try:
        result = engine.review(
            text,
            profile=profile,
            include_refined_text=include_refined_text,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return ReviewResponse(
        refined_text=result.refined_text,
        suggestions=result.suggestions,
        grammar_and_style=result.grammar_and_style,
        literature_review=result.literature_review,
        safeguards=result.safeguards,
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "academic-literature-review-assistant",
        "max_text_chars": MAX_TEXT_CHARS,
    }


@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest):
    return review_text(
        request.text,
        request.profile,
        request.include_refined_text,
    )


@app.post("/review/file", response_model=ReviewResponse)
async def review_file(
    file: UploadFile = File(...),
    profile: str = "standard",
    include_refined_text: bool = True,
):
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            400,
            "This endpoint accepts UTF-8 .txt files only.",
        )

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte limit.",
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            400,
            "The uploaded file must be UTF-8 encoded.",
        ) from exc

    return await run_in_threadpool(
        review_text,
        text,
        profile,
        include_refined_text,
    )
