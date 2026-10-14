# Feature status — first repository integration

Statuses describe this repository change, not local Windows acceptance.

| Feature | Status | Notes |
|---|---|---|
| Existing academic web editor | Existing | FastAPI/static web editor preserved. |
| Writing workspace (documents, autosave, revisions, recovery) | Implemented | `/workspace`. API, DOM-level GUI and packaged smoke checks; the window itself still needs a Windows PC. |
| Inline diagnostics (32 local rules, profiles, Accept/Dismiss) | Implemented | Deterministic and offline; spelling dictionary bundled (MIT). Marker alignment, the anchored pop-up and native undo still need a real rendering engine — see `docs/WINDOWS_DIAGNOSTICS_TEST.md`. |
| Local research library | Implemented; Windows UI acceptance untested | SQLite + optional FTS5 catalogue. Includes a manual "Add a reference" form wired to POST /api/library/work. |
| CSL JSON import | Implemented in this PR | Other citation export formats are future work. |
| Zotero Desktop/Web import | Implemented; real library untested | Read-only. Web imports require user-provided local credentials. |
| Local PDF/TXT/Markdown/HTML/DOCX indexing | Implemented; local file acceptance untested | OCR for image-only scans is not bundled. |
| Crossref/OpenAlex discovery | Implemented; live provider acceptance untested | User-triggered and cached. |
| Evidence briefs and literature matrix | First pass implemented | Search matches are candidates; not proof. |
| Native desktop runtime | Implemented; window rendering untested | pywebview + loopback-only Uvicorn. Packaged exe passes the headless smoke test in CI; window, file pickers and clipboard still need a Windows PC. |
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

## Automated verification added after the desktop repair

`ScholarFlow.exe --smoke-test` (also run by `scripts/build_windows_desktop.ps1`
and the Windows workflow) starts the packaged loopback server without opening a
window and checks bundled assets, the three editor profiles, AI-fallback
behaviour, library health/settings, adding and searching a reference, CSL JSON
import, TXT indexing, passage search, the literature matrix and on-disk
persistence. It runs against an isolated temporary data directory and prints
only check names and HTTP status codes.

Still requires the researcher's Windows PC: the pywebview window itself, file
pickers (TXT/JSON/PDF/DOCX selection), clipboard copy, downloads, Zotero
Desktop's local API, and the optional external AI provider.
