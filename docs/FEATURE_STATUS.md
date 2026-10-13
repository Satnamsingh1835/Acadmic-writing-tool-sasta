# Feature status — first repository integration

Statuses describe this repository change, not local Windows acceptance.

| Feature | Status | Notes |
|---|---|---|
| Existing academic web editor | Existing | FastAPI/static web editor preserved. |
| Local research library | Implemented in this PR | SQLite + optional FTS5 catalogue. |
| CSL JSON import | Implemented in this PR | Other citation export formats are future work. |
| Zotero Desktop/Web import | Implemented; real library untested | Read-only. Web imports require user-provided local credentials. |
| Local PDF/TXT/Markdown/HTML/DOCX indexing | Implemented; local file acceptance untested | OCR for image-only scans is not bundled. |
| Crossref/OpenAlex discovery | Implemented; live provider acceptance untested | User-triggered and cached. |
| Evidence briefs and literature matrix | First pass implemented | Search matches are candidates; not proof. |
| Native desktop runtime | Implemented; Windows runtime untested | pywebview + loopback-only Uvicorn. |
| Windows one-folder package script | Implemented; build untested here | Requires Windows, Python 3.12 and WebView2. |
| Windows build workflow | Added | Actual result appears in PR checks. |
| REA provenance metadata | Inspected through GitHub API | Local checkout/doctor/browser study untested. |
| Grammarly/QuillBot observations | Not tested | Do not populate reports from guesses. |
| CORE connector | Not implemented | Separate follow-up. |
| Semantic embeddings | Not implemented | Keyword/full-text search remains. |
| OCR for scanned PDFs | Partial | Image-only PDFs produce an actionable warning. |
| Zotero write-back/CSL rendering | Not implemented | Read-only import only. |

## Verification gate
Do not move any feature from untested to verified without relevant CI output, Windows run evidence, returned Zotero item counts, successful REA doctor output, or saved dated UI observations.
