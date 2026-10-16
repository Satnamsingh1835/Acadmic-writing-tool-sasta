from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from research_library.store import ResearchLibrary, default_data_dir
from research_library.discovery import DiscoveryError, DiscoveryService
from research_library.documents import DocumentIndexError, index_document
from research_library.importers import import_csl_records
from research_library.zotero import ZoteroConnectionError, import_zotero_items

from academic_engine import AcademicWritingEngine
from document_store import (
    REASON_AUTOSAVE,
    REASON_MANUAL,
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentStore,
    DocumentValidationError,
)
from diagnostics import (
    DEFAULT_PROFILE,
    ENGINE_NAME,
    ENGINE_VERSION,
    MAX_DOCUMENT_CHARS,
    RULESET_VERSION,
    DiagnosticEngine,
    PersonalDictionary,
)
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


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Answer a rejected request with a message the server can always encode.

    FastAPI's default handler echoes the offending input back to the client. A
    lone surrogate — the low half of an emoji, as an ill-formed paste can produce
    — cannot be encoded into that response at all, so a rejected save came back as
    an internal server error. Naming the field is enough for the caller to act
    on, and it never puts document text into an error response.
    """
    fields: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        if location and location not in fields:
            fields.append(location)
    detail = "That request was rejected by validation"
    detail = f"{detail}: {', '.join(fields)}." if fields else f"{detail}."
    return JSONResponse(status_code=422, content={"detail": detail})


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


# Writing workspace. Documents are stored locally in SQLite; the service never
# contacts an external provider on its own.
_document_store: DocumentStore | None = None
_document_store_path: str | None = None


def get_document_store() -> DocumentStore:
    global _document_store, _document_store_path
    db_path = str(default_data_dir() / "writing-documents.sqlite3")
    if _document_store is None or _document_store_path != db_path:
        _document_store = DocumentStore(db_path)
        _document_store_path = db_path
    return _document_store


class DocumentCreateRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    text: str = Field(default="", max_length=2_000_000)


class DocumentSaveRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    text: Optional[str] = Field(default=None, max_length=2_000_000)
    expected_revision: Optional[int] = Field(default=None, ge=1)
    reason: str = Field(default=REASON_MANUAL, max_length=32)


@app.get("/workspace", include_in_schema=False)
def writing_workspace_home():
    return FileResponse(WEB_DIR / "workspace.html")


@app.get("/api/documents")
def workspace_list_documents(q: str = "", limit: int = 200):
    if len(q) > 200:
        raise HTTPException(422, "Search text must be 200 characters or fewer.")
    store = get_document_store()
    return {"documents": store.list(query=q, limit=max(1, min(limit, 500)))}


@app.post("/api/documents")
def workspace_create_document(request: DocumentCreateRequest):
    try:
        return get_document_store().create(title=request.title or None, text=request.text)
    except DocumentValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/documents/{document_id}")
def workspace_get_document(document_id: str):
    try:
        return get_document_store().get(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/documents/{document_id}")
def workspace_save_document(document_id: str, request: DocumentSaveRequest):
    if request.reason not in {REASON_MANUAL, REASON_AUTOSAVE}:
        raise HTTPException(400, "Clients may save with reason 'manual' or 'autosave'.")
    store = get_document_store()
    try:
        return store.save(
            document_id,
            title=request.title,
            text=request.text,
            expected_revision=request.expected_revision,
            reason=request.reason,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except DocumentConflictError as exc:
        raise HTTPException(
            409,
            "This document was changed in another window. Reload it before saving.",
        ) from exc
    except DocumentValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/documents/{document_id}")
def workspace_delete_document(document_id: str):
    try:
        document = get_document_store().delete(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"id": document["id"], "archived": document["archived"]}


@app.post("/api/documents/{document_id}/restore")
def workspace_restore_document(document_id: str):
    try:
        return get_document_store().restore_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/documents/{document_id}/revisions")
def workspace_document_revisions(document_id: str):
    try:
        revisions = get_document_store().revisions(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"revisions": revisions}


@app.post("/api/documents/{document_id}/revisions/{revision}/restore")
def workspace_restore_document_revision(document_id: str, revision: int):
    try:
        return get_document_store().restore_revision(document_id, revision)
    except DocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


# Inline diagnostics for the writing workspace. Everything runs locally: the
# rules are deterministic, the dictionary ships with the application, and no
# document text is logged or sent anywhere.
class DiagnosticsRequest(BaseModel):
    # The length limit is enforced by the engine on purpose: a pydantic
    # max_length error echoes a snippet of the document back to the client,
    # which would put academic text into an error response.
    text: str = Field(default="")
    document_id: Optional[str] = None
    revision: Optional[int] = None
    categories: Optional[list[str]] = None
    # A profile name is short and fixed, so validating it here is safe: an
    # invalid one never echoes document text. The engine still resolves aliases.
    profile: Optional[str] = Field(default=None, max_length=32)


class DictionaryRequest(BaseModel):
    word: str = Field(min_length=1, max_length=64)


_personal_dictionary: PersonalDictionary | None = None
_personal_dictionary_path: str | None = None
_diagnostics_engine: DiagnosticEngine | None = None
_diagnostics_engine_key: tuple[str, ...] | None = None


def get_personal_dictionary() -> PersonalDictionary:
    global _personal_dictionary, _personal_dictionary_path
    path = str(default_data_dir() / "writing-dictionary.json")
    if _personal_dictionary is None or _personal_dictionary_path != path:
        _personal_dictionary = PersonalDictionary(path)
        _personal_dictionary_path = path
    return _personal_dictionary


def get_diagnostics_engine() -> DiagnosticEngine:
    """One engine per personal dictionary, so a new word takes effect at once."""
    global _diagnostics_engine, _diagnostics_engine_key
    words = tuple(get_personal_dictionary().words())
    if _diagnostics_engine is None or _diagnostics_engine_key != words:
        _diagnostics_engine = DiagnosticEngine(words)
        _diagnostics_engine_key = words
    return _diagnostics_engine


@app.get("/api/workspace/diagnostics/categories")
def workspace_diagnostic_categories():
    return {
        "categories": DiagnosticEngine.categories(),
        "groups": DiagnosticEngine.groups(),
        "profiles": DiagnosticEngine.profiles(),
        "default_profile": DEFAULT_PROFILE,
        "limits": {"max_characters": MAX_DOCUMENT_CHARS},
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "ruleset_version": RULESET_VERSION,
        },
        "privacy": (
            "Diagnostics run locally with a bundled dictionary and deterministic "
            "rules. No document text leaves this computer and nothing is logged."
        ),
    }


@app.get("/api/workspace/diagnostics/profiles")
def workspace_diagnostic_profiles():
    return {
        "profiles": DiagnosticEngine.profiles(),
        "default_profile": DEFAULT_PROFILE,
    }


@app.post("/api/workspace/diagnostics")
def workspace_diagnostics(request: DiagnosticsRequest):
    try:
        report = get_diagnostics_engine().analyse(
            request.text,
            categories=request.categories,
            profile=request.profile,
            document_id=request.document_id,
            revision=request.revision,
        )
    except ValueError as exc:
        # Messages describe the request, never the document contents.
        raise HTTPException(422, str(exc)) from exc
    return report


@app.get("/api/workspace/dictionary")
def workspace_dictionary():
    return {"words": get_personal_dictionary().words()}


@app.post("/api/workspace/dictionary")
def workspace_dictionary_add(request: DictionaryRequest):
    try:
        words = get_personal_dictionary().add(request.word)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"words": words}


@app.delete("/api/workspace/dictionary/{word}")
def workspace_dictionary_remove(word: str):
    try:
        words = get_personal_dictionary().remove(word)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"words": words}


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
