from __future__ import annotations

import hashlib
import html.parser
import io
import re
import uuid
from pathlib import Path
from typing import Iterable

from research_library.store import ResearchLibrary


MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".html", ".htm", ".docx"}


class DocumentIndexError(ValueError):
    """A document could not be stored or indexed safely."""


class _TextHTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.casefold() in {"script", "style", "noscript"}:
            self.suppressed += 1

    def handle_endtag(self, tag: str):
        if tag.casefold() in {"script", "style", "noscript"} and self.suppressed:
            self.suppressed -= 1
        elif tag.casefold() in {"p", "div", "li", "br", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if not self.suppressed:
            self.parts.append(data)


def _extract_pages(extension: str, payload: bytes) -> list[tuple[int | None, str]]:
    if extension in {".txt", ".md"}:
        try:
            return [(None, payload.decode("utf-8-sig"))]
        except UnicodeDecodeError as exc:
            raise DocumentIndexError("Text documents must be UTF-8 encoded.") from exc
    if extension in {".html", ".htm"}:
        try:
            parser = _TextHTMLParser()
            parser.feed(payload.decode("utf-8-sig"))
            return [(None, "".join(parser.parts))]
        except (UnicodeDecodeError, ValueError) as exc:
            raise DocumentIndexError("Could not decode the HTML document as UTF-8.") from exc
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentIndexError(
                "PDF extraction requires the optional research dependencies: "
                "python -m pip install -r requirements-research.txt"
            ) from exc
        try:
            reader = PdfReader(io.BytesIO(payload))
            pages = [(number, page.extract_text() or "") for number, page in enumerate(reader.pages, 1)]
        except Exception as exc:
            raise DocumentIndexError("Could not read this PDF. It may be damaged or encrypted.") from exc
        if not any(text.strip() for _, text in pages):
            raise DocumentIndexError(
                "No selectable text was found. OCR for scanned PDFs is not bundled; index an OCR-text copy."
            )
        return pages
    if extension == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise DocumentIndexError(
                "DOCX extraction requires python-docx. Install requirements-research.txt."
            ) from exc
        try:
            document = Document(io.BytesIO(payload))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        except Exception as exc:
            raise DocumentIndexError("Could not read this DOCX file.") from exc
        return [(None, text)]
    raise DocumentIndexError(
        "Supported formats are PDF, TXT, Markdown, HTML and DOCX."
    )


def _chunks(text: str, maximum: int = 1400) -> Iterable[str]:
    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = re.sub(r"[ \t]+", " ", paragraph).strip()
        if not paragraph:
            continue
        while len(paragraph) > maximum:
            split_at = paragraph.rfind(" ", 0, maximum)
            if split_at < maximum // 2:
                split_at = maximum
            yield paragraph[:split_at].strip()
            paragraph = paragraph[split_at:].strip()
        if paragraph:
            yield paragraph


def index_document(
    library: ResearchLibrary,
    filename: str,
    payload: bytes,
    *,
    work_id: str | None = None,
    source_url: str = "",
    licence: str = "",
) -> dict:
    if not filename or len(filename) > 255:
        raise DocumentIndexError("Filename is missing or too long.")
    extension = Path(filename).suffix.casefold()
    if extension not in _ALLOWED_EXTENSIONS:
        raise DocumentIndexError("Supported formats are PDF, TXT, Markdown, HTML and DOCX.")
    if not payload:
        raise DocumentIndexError("The uploaded document is empty.")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise DocumentIndexError("The document exceeds the 20 MiB indexing limit.")
    if work_id and library.get_work(work_id) is None:
        raise DocumentIndexError("The linked research record does not exist.")
    digest = hashlib.sha256(payload).hexdigest()
    document_id = uuid.uuid4().hex
    folder = library.data_dir / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    stored_path = folder / (document_id + extension)
    try:
        pages = _extract_pages(extension, payload)
        stored_path.write_bytes(payload)
        record = library.add_document(
            work_id=work_id,
            filename=Path(filename).name,
            stored_path=str(stored_path),
            source_url=source_url[:2000],
            licence=licence[:500],
            sha256=digest,
            parser_status="text_extracted",
        )
        if record.get("duplicate"):
            stored_path.unlink(missing_ok=True)
            return {"document_id": record["id"], "duplicate": True, "passages_indexed": 0}
        passage_count = 0
        passage_index = 0
        for page_number, text in pages:
            for chunk in _chunks(text):
                library.add_passage(
                    record["id"], chunk, page_number=page_number,
                    passage_index=passage_index, work_id=work_id,
                )
                passage_count += 1
                passage_index += 1
        return {
            "document_id": record["id"],
            "duplicate": False,
            "passages_indexed": passage_count,
            "page_count": len(pages) if extension == ".pdf" else None,
            "access_status": "local_full_text_indexed",
            "warning": "Text extraction is not OCR; always verify passages in the original document.",
        }
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
