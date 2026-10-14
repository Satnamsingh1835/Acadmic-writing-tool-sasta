# ScholarFlow writing workspace — architecture and staged plan

Status: plan plus implementation log. Stage 1 is implemented on branch
`arena/883f6125-acadmic-writing-tool-sasta`; later stages are described but not
yet built.

## 1. What already exists and must be reused

| Layer | Existing component | Reuse decision |
|---|---|---|
| Local API | FastAPI app in `api.py` (editor, library, documents, discovery) | Extend with a document store and `/api/documents*`; no second server |
| Deterministic analysis | `academic_engine.py`, `academic_analyser.py`, `academic_suggestions.py`, `argument_diagnostics.py`, `literature_review.py`, `advanced_humanize.py`, `text_parser.py` | The diagnostics and rewrite stages call these; they are deterministic, offline and already unit-tested |
| Revision contract | `editor_service.py` + `revision_receipt.py` | Every proposal keeps its receipt, citation safeguards and statistics |
| Optional AI | `llm_tools.py` (`configured_provider`) | Stays optional and off by default; local checks never depend on it |
| Persistence | `research_library/store.py` (SQLite + FTS5), `default_data_dir()` | Same pattern and same user-data directory for the new document store |
| Desktop shell | `desktop_app.py` loopback Uvicorn + pywebview, `--smoke-test` gate | The workspace is served by the same app and covered by the same gate |
| Library | `research_library/*`, `/library` | Untouched; citations and matrix stay available for the workspace later |

No existing feature is removed. The quick single-passage editor at `/` stays.

## 2. Editor framework evaluation

| Option | Licence | Offline packaging | Offset mapping for markers | Integration effort | Verdict |
|---|---|---|---|---|---|
| Plain `<textarea>` + overlay layer | n/a (browser built-in) | none needed | exact (`selectionStart`/`End` are character offsets) | low | **Chosen for stages 1–3** |
| CodeMirror 6 | MIT | vendored bundle (~400 KB, needs a bundler step) | excellent (decorations) | medium–high | Upgrade path for stage 3 if inline markers feel cramped |
| ProseMirror / TipTap | MIT | vendored bundle | through document positions, needs mapping to text offsets | high | Rejected for now: rich-text model complicates "never silently rewrite" verification |
| Quill 2 | BSD-3 | vendored bundle | Delta-based, offset conversion needed | medium–high | Rejected: heavier than needed, weaker text-offset story |
| Custom `contenteditable` | n/a | none | fragile (DOM ranges, IME, paste) | high risk | Rejected |

Decision: build stage 1–3 on a plain text editing surface with a Markdown-style
structure model (headings, lists, quotes are real text with markers). This gives
native selection, undo/redo, IME, keyboard shortcuts and exact character offsets,
needs no build step, works offline inside the packaged app, and is the only option
that can be verified end-to-end in the repository's automated GUI harness. If
in-canvas marker rendering becomes the limiting factor, CodeMirror 6 is the
planned upgrade, and the diagnostics API (text + offsets) would not change.

## 3. Grammar engine evaluation

| Engine | Licence | Offline | Fit | Verdict |
|---|---|---|---|---|
| Existing deterministic analyzers (`text_parser`, `academic_analyser`, `academic_suggestions`, `literature_review`, `argument_diagnostics`) | repository (MIT-licensed project) | yes | citation safety, tone, wordiness, structure, repetition — already tested | **Primary engine** |
| Local spell checker (pure-Python dictionary, e.g. `pyspellchecker`, MIT) | MIT | yes | spelling + suggestions | Planned for stage 2, adds one dependency and a bundled dictionary |
| LanguageTool (local server) | LGPL-2.1 | yes but needs Java + a separate process | very broad grammar coverage | Considered as an optional local backend; not bundled by default |
| Harper | Apache-2.0 | needs a Rust build/native binary | good grammar coverage | Tracked as a future option |
| Vale | MIT | Go binary | style rules, not grammar | Not suitable |
| Cloud grammar APIs (Grammarly, LanguageTool cloud, OpenAI) | proprietary | no | broad | **Never required**; only ever called after explicit user consent and never for the basic workflow |

Decision: keep the deterministic analyzers as the engine of record. Stage 2 adds
spelling from a bundled MIT dictionary plus the missing rule families implemented
in `text_parser`-style code so every finding is reproducible and offline. Optional
AI assistance stays a separate, clearly-labelled switch that never blocks local
checking and never sends text without consent.

## 4. Staged plan

**Stage 1 — document editing (implemented here).** Document-based workspace at
`/workspace`: real editing surface, Markdown structure with toolbar and
shortcuts, documents list, create/rename/save/delete, autosave with crash
recovery, revision history and restore, outline, statistics, status/error
surfaces, reviewable refine of a selection or paragraph using the existing
endpoint. Plus the fix for the reported Refine/Ctrl+Enter defect.

**Stage 2 — diagnostics.** Compute findings server-side with offsets
(`start`, `end`, `category`, `severity`, `message`, `replacements`), render them
as an overlay layer under the text, and expose:
`POST /api/workspace/diagnostics {document_id, text}`. Categories are grouped as
*error* (spelling, agreement, punctuation, capitalization, fragments, run-ons)
and *recommendation* (wordiness, structure, tone, repetition, readability) so a
stylistic preference is never presented as an error. Local spelling lands here.

**Stage 3 — inline suggestions.** Clicking a marker opens a pop-up anchored to
the range with the original text, proposed correction, category, explanation,
Accept, Dismiss and alternatives. Acceptance applies at the stored offsets and is
refused if the text at those offsets changed (stale guard). Sidebar with totals,
grouping and next/previous navigation.

**Stage 4 — academic enhancements.** Profiles (Academic standard, Concise,
Formal/minimal), terminology and citation preservation checks, quotation
protection, per-change accept/reject, bulk review with receipts, and an optional
"AI enhance" path that is off by default and requires explicit consent per action.

**Stage 5 — packaging and verification.** Extend `desktop_app.py --smoke-test`
with workspace checks, keep the packaged-window acceptance test on Windows, and
keep the GUI harness in CI.

## 5. Verification strategy

- Unit tests for the document store (create/save/conflict/autosave/revisions/
  restore/soft delete, persistence across reopen), API tests for the endpoints.
- An in-repository GUI harness (`tests/gui/`) drives the real page in a DOM
  against a live server: typing, toolbar edits, save, reload, recovery, refine
  accept/dismiss/stale-guard, and error rendering. `tests/test_workspace_gui.py`
  runs it from pytest and skips only when Node or jsdom is unavailable.
- The packaged application keeps its headless smoke gate; the Windows window
  itself still needs the researcher's PC.
