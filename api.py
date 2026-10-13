from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from research_library.store import ResearchLibrary, default_data_dir
from research_library.discovery import DiscoveryError, DiscoveryService
from research_library.documents import DocumentIndexError, index_document
from research_library.importers import import_csl_records
from research_library.zotero import ZoteroConnectionError, import_zotero_items

from academic_engine import AcademicWritingEngine
from editor_service import AcademicEditorService

MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "500000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "2000000"))
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB_DIR = APP_DIR / "web"
MAX_LIBRARY_UPLOAD_BYTES = int(os.getenv("MAX_LIBRARY_UPLOAD_BYTES", str(20 * 1024 * 1024)))

app = FastAPI(
    title="Academic Literature Review Assistant API",
    version="2.1.0",
)
engine = AcademicWritingEngine()
editor_service = AcademicEditorService(engine=engine)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


class ReviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    profile: str = Field(default="standard", min_length=1, max_length=32)
    include_refined_text: bool = True


class ReviewResponse(BaseModel):
    refined_text: Optional[str]
    suggestions: list[dict]
    grammar_and_style: dict
    literature_review: dict
    safeguards: dict


class EditorRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    profile: str = Field(default="standard", min_length=1, max_length=32)
    use_llm: bool = False


class EditorResponse(BaseModel):
    original_text: str
    refined_text: str
    profile: str
    provider: str
    used_llm: bool
    notices: list[str]
    stats: dict[str, int | float]
    suggestions: list[dict]
    grammar_and_style: dict
    literature_review: dict
    safeguards: dict
    receipt: dict[str, object]


def review_text(
    text: str,
    profile: str,
    include_refined_text: bool,
) -> ReviewResponse:
    if not isinstance(text, str):
        raise HTTPException(400, "Text must be a string.")
    if not text.strip():
        raise HTTPException(400, "Text is empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            413,
            f"Text exceeds the {MAX_TEXT_CHARS}-character limit.",
        )
    if not isinstance(profile, str):
        raise HTTPException(400, "Profile must be a string.")

    try:
        result = engine.review(
            text,
            profile=profile,
            include_refined_text=include_refined_text,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

    return ReviewResponse(
        refined_text=result.refined_text,
        suggestions=result.suggestions,
        grammar_and_style=result.grammar_and_style,
        literature_review=result.literature_review,
        safeguards=result.safeguards,
    )


@app.get("/", include_in_schema=False)
def editor_home():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "academic-literature-review-assistant",
        "version": app.version,
        "max_text_chars": MAX_TEXT_CHARS,
    }


@app.get("/editor/capabilities")
def editor_capabilities():
    return {
        **editor_service.capabilities(),
        "max_text_chars": MAX_TEXT_CHARS,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }


@app.post("/editor/rewrite", response_model=EditorResponse)
async def editor_rewrite(request: EditorRequest):
    try:
        result = await run_in_threadpool(
            editor_service.rewrite,
            request.text,
            request.profile,
            request.use_llm,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return EditorResponse(**asdict(result))


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


# Local research-library endpoints. They operate on a user-local SQLite database;
# discovery providers are called only after an explicit user request.
_library_instance: ResearchLibrary | None = None
_library_instance_path: str | None = None


def get_research_library() -> ResearchLibrary:
    global _library_instance, _library_instance_path
    db_path = str(default_data_dir() / "research-library.sqlite3")
    if _library_instance is None or _library_instance_path != db_path:
        _library_instance = ResearchLibrary(db_path)
        _library_instance_path = db_path
    return _library_instance


class CSLImportRequest(BaseModel):
    records: list[dict] = Field(min_length=1, max_length=1000)


class WorkRequest(BaseModel):
    record: dict


class WorkUpdateRequest(BaseModel):
    fields: dict


class LibrarySettingsRequest(BaseModel):
    crossref_enabled: bool = True
    openalex_enabled: bool = True
    offline: bool = False


class MatrixEntryRequest(BaseModel):
    work_id: str
    research_question: str = Field(min_length=1, max_length=2000)
    claim: str = Field(default="", max_length=5000)
    method: str = Field(default="", max_length=1000)
    supporting_passage: str = Field(default="", max_length=5000)
    page_number: Optional[int] = Field(default=None, ge=1)
    evidence_level: str = Field(default="candidate", max_length=40)


class EvidenceBriefRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


@app.get("/library", include_in_schema=False)
def research_library_home():
    return FileResponse(WEB_DIR / "library.html")


@app.get("/api/library/health")
def research_library_health():
    library = get_research_library()
    return {
        "status": "ok",
        "database": "local",
        "schema_version": library.schema_version,
        "fts5_available": library.fts5_available,
        "work_count": library.count_works(),
        "document_count": library.count_documents(),
    }


@app.get("/api/library/search")
def research_library_search(
    q: str = "",
    author: str = "",
    year: Optional[int] = None,
    item_type: str = "",
    access_status: str = "",
    subject: str = "",
    sort: str = "relevance",
    limit: int = 50,
):
    if len(q) > 500:
        raise HTTPException(422, "Search text must be 500 characters or fewer.")
    library = get_research_library()
    return {
        "results": library.search_works(
            q=q,
            author=author,
            year=year,
            item_type=item_type,
            access_status=access_status,
            subject=subject,
            sort=sort,
            limit=max(1, min(limit, 100)),
        )
    }


@app.post("/api/library/import/csl-json")
def research_library_import_csl_json(request: CSLImportRequest):
    library = get_research_library()
    try:
        result = import_csl_records(library, request.records)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@app.post("/api/library/work")
def research_library_add_work(request: WorkRequest):
    library = get_research_library()
    try:
        return library.add_work(request.record)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/library/work/{work_id}")
def research_library_update_work(work_id: str, request: WorkUpdateRequest):
    library = get_research_library()
    try:
        result = library.update_work(work_id, request.fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "Research record not found.")
    return result


@app.post("/api/library/import/zotero")
def research_library_import_zotero(
    source: str = "local",
    collection_key: str = "",
    limit: int = 100,
):
    if source not in {"local", "web"}:
        raise HTTPException(400, "Source must be 'local' or 'web'.")
    library = get_research_library()
    try:
        return import_zotero_items(
            library,
            source=source,
            collection_key=collection_key.strip() or None,
            limit=max(1, min(limit, 100)),
        )
    except ZoteroConnectionError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/library/discovery/{provider}")
def research_library_discovery(
    provider: str,
    q: str,
    limit: int = 10,
):
    if provider not in {"crossref", "openalex"}:
        raise HTTPException(404, "Supported providers are crossref and openalex.")
    if len(q.strip()) < 2 or len(q) > 500:
        raise HTTPException(422, "Query must contain 2–500 characters.")
    library = get_research_library()
    settings = library.get_settings()
    if settings.get(provider + "_enabled", True) is False:
        return {"provider": provider, "status": "disabled", "results": []}
    service = DiscoveryService(library)
    try:
        result = service.search(
            provider, q.strip(), limit=max(1, min(limit, 25)),
            offline=bool(settings.get("offline", False)),
        )
    except (DiscoveryError, ValueError) as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        service.close()
    return result


@app.get("/api/library/doi/{doi:path}")
def research_library_verify_doi(doi: str):
    service = DiscoveryService(get_research_library())
    try:
        return service.verify_doi(doi)
    except (DiscoveryError, ValueError) as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        service.close()


@app.post("/api/library/documents")
async def research_library_index_document(
    file: UploadFile = File(...),
    work_id: str = "",
    source_url: str = "",
    licence: str = "",
):
    if not file.filename:
        raise HTTPException(400, "A filename is required.")
    raw = await file.read(MAX_LIBRARY_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw) > MAX_LIBRARY_UPLOAD_BYTES:
        raise HTTPException(413, "Document exceeds the configured upload-size limit.")
    try:
        result = index_document(
            get_research_library(),
            file.filename,
            raw,
            work_id=work_id.strip() or None,
            source_url=source_url.strip(),
            licence=licence.strip(),
        )
    except DocumentIndexError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@app.get("/api/library/passages")
def research_library_search_passages(q: str, limit: int = 10):
    if len(q.strip()) < 2 or len(q) > 500:
        raise HTTPException(422, "Query must contain 2–500 characters.")
    return {
        "results": get_research_library().search_passages(
            q.strip(), limit=max(1, min(limit, 20))
        )
    }


@app.post("/api/library/evidence-brief")
def research_library_evidence_brief(request: EvidenceBriefRequest):
    passages = get_research_library().search_passages(
        request.query.strip(), limit=request.limit
    )
    if not passages:
        return {
            "status": "insufficient_evidence",
            "query": request.query,
            "warning": (
                "No indexed passage matched this query. This is not proof "
                "that the literature lacks evidence or that a research gap exists."
            ),
            "evidence": [],
        }
    return {
        "status": "candidate_evidence",
        "query": request.query,
        "warning": (
            "These are text matches for researcher review, not proof that a source "
            "supports a claim. Verify each passage and its context in the original."
        ),
        "evidence": passages,
    }


@app.get("/api/library/matrix")
def research_library_matrix():
    return {"results": get_research_library().list_matrix_entries()}


@app.post("/api/library/matrix")
def research_library_add_matrix_entry(request: MatrixEntryRequest):
    library = get_research_library()
    if library.get_work(request.work_id) is None:
        raise HTTPException(404, "Research record not found.")
    return library.add_matrix_entry(request.model_dump())


@app.get("/api/library/settings")
def research_library_settings():
    return get_research_library().get_settings()


@app.put("/api/library/settings")
def research_library_update_settings(request: LibrarySettingsRequest):
    return get_research_library().update_settings(request.model_dump())
