# ScholarFlow implementation status — repository PR snapshot

**Status:** first-pass repository integration. Windows acceptance, real Zotero acceptance and REA browser observations are not claimed.

## Included
- SQLite-based local research catalogue with FTS5 where available, metadata normalization/deduplication, notes, documents, source links, access/licence status and candidate literature-matrix rows.
- CSL JSON import and read-only Zotero Desktop/Web API metadata import.
- Local PDF/TXT/Markdown/HTML/DOCX extraction with candidate passages and extracted PDF page numbers.
- User-triggered Crossref/OpenAlex discovery, local cache and offline settings.
- Evidence-brief endpoint with explicit insufficient-evidence warning.
- Research library UI at `/library`.
- Native pywebview desktop entry point, loopback-only Uvicorn, Windows one-folder build script/spec and CI workflow.
- Dry-run-first REA readiness script, synthetic passages, and evidence/report templates.

## Validation status
The PR's GitHub Actions workflow is the source for actual CI status. Do not repeat test counts from a previous local session as if this branch ran the same suite.

These items require separate verification:
- Native desktop launch/shutdown on Windows 11 with WebView2.
- Import from a real researcher-approved Zotero library.
- REA setup/doctor in a supported local coding-agent environment.
- Actual Grammarly Free and QuillBot Free observations.
- CORE API integration is not implemented.

## Current limitations
- OCR for scanned-only PDFs is not bundled.
- Semantic embeddings are not included in this first pass.
- Zotero integration is read-only; CSL rendering and Zotero write-back are not included.
- Metadata records are not full-text evidence. Researchers must verify candidate passages and interpretations in the original source.
