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

**Re-evaluated after stage 3 (when the markers, the anchored pop-up and the
profile picker were in place): the textarea stays.** The three things that would
have justified CodeMirror 6 were in-canvas rendering, decoration management and
viewport performance. Markers over a measured mirror cover the first two without
a bundler, a vendored bundle or a second text model, and the viewport cost is
bounded because the marker layer is rebuilt from the visible findings rather than
per character. Two costs of staying are real and recorded: programmatic edits
must go through `document.execCommand("insertText")` to keep the browser's undo
history (a framework would own the history itself), and marker alignment depends
on the mirror sharing the textarea's metrics exactly, which the CSS documents.
Migrating later remains open, because nothing in the diagnostics contract — text
plus offsets — is specific to the editing surface.

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

**Stage 2 — diagnostics (implemented).** Findings are computed server-side with
exact offsets and returned by `POST /api/workspace/diagnostics`; the editor
renders them as inline markers over the text, grouped in a categorised sidebar
with error/style filters, a suggestion card with Accept/Dismiss, a stale-range
guard and a personal dictionary. See `docs/STAGE2_DIAGNOSTICS_PLAN.md` for the
rules, the offset contract and the limitations. Categories are split into
*error* (spelling, agreement, punctuation, capitalisation, fragments, run-ons)
and *style* (wordiness, repetition, readability, tone) so a stylistic preference
is never presented as an error; the one convention-based agreement rule
("data is") is deliberately reported as style, not as an error.

**Stage 3 — inline suggestions (implemented).** Clicking a marker opens a pop-up
anchored to the range with the original text, proposed correction, category and
group, explanation, confidence, rule id and version, Accept, Dismiss and
alternatives. Acceptance applies at the stored offsets and is refused if the text
at those offsets changed (stale guard). The sidebar groups findings by category
with counts, a plain total, error/style filters and next/previous navigation.
Three academic profiles (Academic Standard, Formal Academic Writing, Concise
Academic Writing) enable, withhold and reprioritise the optional style rules;
spelling and the reliable grammar rules run in all of them. See
`docs/STAGE3_INLINE_DIAGNOSTICS_PLAN.md` for the rules, the assembly, the
measurements and the false positives.

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
- Stage 2 adds unit tests per rule, API tests for the endpoints and their
  privacy guarantees, and DOM-level checks for markers, the sidebar, filters,
  navigation, Accept/Dismiss/stale handling, the dictionary and the failure
  surfaces.
- Stage 3 adds rule tests for the new families, tests for the profile contract
  and its "never rewrites the text" invariant, performance budgets for long and
  adversarial documents, failure-mode tests for a missing dictionary, and DOM
  checks for the total, the profile effects, the anchored pop-up (against a
  stubbed layout), the exact range handed to `document.execCommand`, autosave
  races and save/reopen integrity.

## 6. Known limitations after Stage 3

- Spelling is US-English with British variants accepted; other scripts are not
  checked, and the protected-vocabulary list is a curated start rather than a
  complete ontology (see section 9 of `docs/STAGE3_INLINE_DIAGNOSTICS_PLAN.md`).
- Fragment, run-on and part-of-agreement findings are heuristic and stay at
  medium confidence; profiles change which style rules run, never the text.
- Marker pixel alignment and the browser's own undo after an accepted correction
  are verified against stubbed measurements in the automated checks; a real
  rendering engine is needed to observe them (see
  `docs/WINDOWS_DIAGNOSTICS_TEST.md`).

## 7. Known limitations after Stage 2 (kept for the record)

- The bundled dictionary is US-English; British spellings are accepted through
  the variant rules in `diagnostics.py`, and field terms go in the personal
  dictionary. Words in other scripts (for example Devanagari) are not checked,
  because the dictionary is English.
- Fragment, run-on and agreement rules are heuristic and are reported at
  `medium` confidence; they never rewrite anything on their own.
- Repetition rules can be noisy in text that deliberately repeats a passage;
  findings are capped at 600 per document.
- Marker alignment over the characters is measured in the browser. jsdom has no
  layout engine, so the automated DOM checks verify marker identity, labels,
  ordering and behaviour, but not pixel alignment; that needs WebView2 on
  Windows or a real browser.
