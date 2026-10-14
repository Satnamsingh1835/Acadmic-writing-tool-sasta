# Stage 2 — inline diagnostics: implementation plan and log

Status: **implemented** on branch `arena/883f6125-acadmic-writing-tool-sasta`
(Stage 1 baseline `882f744a…`). Test results and the exact commands are at the
end of this file.

Stage 1 (document editing) is implemented and green at `882f744a2579f388843978919d16d5ab6668ab97`.
This plan covers Stage 2 only and is updated as the work lands.

## 1. Current diagnostic capability (audited before writing code)

| Component | What it already does | Reuse in Stage 2 |
|---|---|---|
| `text_parser.py` | paragraph/sentence splitting (abbreviation- and decimal-aware), Unicode word tokens, author-year citation extraction | Sentence and word primitives, abbreviation guard for the punctuation rules |
| `academic_analyser.py` | formulaic phrases, absolutes/overclaims, repetitive openings, long sentences, citation diagnostics | Source of the phrase tables for wordiness, tone and readability rules |
| `humanize.py` | `DEFAULT_WORDINESS`, `AI_MARKER_REPLACEMENTS`, `AI_MARKERS_TO_REMOVE`, `DEFAULT_BRITISH`, `language_only_diagnostics()` | The wordiness replacements are reused verbatim so diagnostics and the refine path agree on wording |
| `academic_suggestions.py` | sentence-level suggestions, but only as whole-sentence rewrites | Not used for markers: its granularity is a sentence, not an exact range |
| `argument_diagnostics.py` | paragraph-level rhetorical questions | Untouched; it is paragraph advice, not a range-based finding |
| `editor_service.py` / `POST /editor/rewrite` | full-passage rewrite with receipt | Untouched; remains the Stage 1 refine path |
| `document_store.py` | documents, revisions, conflict guard | Untouched; the diagnostics endpoint is stateless |

Conclusion: **no range-based, categorised diagnostic layer exists**. Stage 2 adds one; it reuses the tables and primitives above rather than duplicating them.

## 2. Files to change

| File | Change |
|---|---|
| `diagnostics.py` *(new)* | Offsets-aware mask + prose layer and the ten rule families |
| `api.py` | `POST /api/workspace/diagnostics`, `GET /api/workspace/diagnostics/categories`, `GET/POST/DELETE /api/workspace/dictionary` |
| `web/workspace.html` | marker layer over the editor, suggestion card, diagnostics sidebar with filters, accessible live regions |
| `web/workspace.css` | marker styles (shape + underline style, never colour alone), sidebar groups, error vs style treatment |
| `web/workspace.js` | debounced analysis, marker rendering/navigation, accept/dismiss with the stale guard, keyboard support |
| `tests/test_diagnostics.py` *(new)* | rule-by-rule unit tests, offsets for Unicode/Markdown/multiline, overlapping diagnostics |
| `tests/test_workspace_diagnostics_api.py` *(new)* | endpoint contract, dictionary endpoints, validation, privacy |
| `tests/gui/workspace_dom_check.mjs` | Stage 2 GUI checks |
| `tests/test_workspace_gui.py` | unchanged (wrapper already runs the harness) |
| `desktop_app.py` | smoke checks for the diagnostics endpoint and the new bundled assets |
| `docs/WRITING_WORKSPACE_PLAN.md` | Stage 2 marked implemented, limitations recorded |
| `requirements-research.txt` | `pyspellchecker==0.8.2` (MIT, pure Python, bundled dictionary) |

## 3. Diagnostic categories and classification

| Category | Kind | Rule examples |
|---|---|---|
| `spelling` | error | token not in the local dictionary, not allow-listed, not a citation/proper noun |
| `agreement` | error | `there is` + plural, `these is`, `each of … are`, `people is` |
| `agreement` *(data is / criteria is)* | **style** | both conventions are used in academic writing, so it is never labelled an error |
| `punctuation` | error | space before `,.!?`, missing space after, doubled punctuation, unclosed bracket |
| `capitalization` | error | lowercase sentence start, standalone `i`, lowercase language/nationality adjectives |
| `fragment` | error | no main clause, or an opening subordinator with no main clause |
| `run_on` | error | comma splice: two finite clauses joined by a comma without a conjunction |
| `wordiness` | style | `in order to`, `due to the fact that`, formulaic openers |
| `repetition` | style | immediate word repetition, overused content words/phrases |
| `readability` | style | sentence ≥ 35 words, paragraph ≥ 220 words |
| `tone` | style | contractions, vague quantifiers, overclaiming absolutes |

Every finding carries: `id` (stable: `rule@start-end#hash(original)`), `rule`, `category`,
`category_label`, `kind`, `severity` (= kind), `confidence`, `message`, `explanation`,
`start`, `end`, `original`, `replacement`, `replacements`.

## 4. Offset handling

The editor's text representation is the source of truth: Python `str` indices, UTF-16 is never
involved because the client uses `selectionStart`/`slice` on the same string.

- **Unicode**: `len()` is code points; combining marks stay attached to their base word
  (`text_parser._WORD_RE` already matches them).
- **Markdown**: a mask is computed before analysis — fenced code blocks, inline code,
  YAML front matter, link reference definitions and the reference list are excluded.
  Heading/list/quote/table markers are dropped from the *prose* view and the mapping back to
  original offsets is kept, so a marker never shifts a reported range.
- **Line breaks**: `\n` and `\r\n` are counted as one character range; `\r\n` is normalised
  in the store, so client and server agree.
- **Citations, quotations and protected spans** are analysed for readability but excluded
  from spelling/capitalisation findings.
- **Overlapping diagnostics** are allowed (a long sentence may also contain a wordiness
  finding); they are ordered by `start`, then `end`, then rule id, and the client renders
  them by ascending length so a click never hits the wrong layer.
- Processing is chunked at paragraph boundaries (≤ 4,000 characters per chunk) so a full
  paper is analysed without a long blocking pass; offsets are shifted by the chunk start.

## 5. Regression tests

- Unit: one or more tests per category; offsets for Unicode (Devanagari, accented Latin,
  em dash, curly quotes), Markdown (headings, lists, code fences, inline code, links,
  citations, reference list), multiline text, and overlapping findings.
- API: schema, empty text, oversized text, category filter, dictionary add/remove, no text
  in error responses.
- GUI: markers at exact ranges, marker click → card, accept/dismiss, stale refusal,
  sidebar grouping + counts + filters + navigation, empty state, keyboard access, and the
  Stage 1 workflows unchanged.
- Manual/again-runnable: the Stage 1 checks plus the packaged Windows smoke gate.

## 6. Risks and limitations (documented in the product, not hidden)

- The bundled dictionary is US-English biased (`behaviour`, `analyse` are absent), so a
  curated academic/British allowlist and a user personal dictionary are required; the
  limitation is stated in the sidebar note.
- Fragment, run-on and agreement detection are heuristic and marked `medium` confidence;
  they never rewrite anything on their own.
- No grammar engine can be complete offline; cloud engines are never required and never
  contacted.

## 7. What was implemented

| Piece | Where |
|---|---|
| Offset-aware mask (fenced code, inline code, front matter, link targets, reference list) and prose mapping back to original offsets | `diagnostics.py` (`_Mask`, `_ViewBuilder`, `_View`) |
| Ten rule families, each tagged `error` or `style` | `diagnostics.py` (`spelling.unknown-word`, `agreement.*`, `punctuation.*`, `capitalization.*`, `fragment.no-main-clause`, `run_on.comma-splice`, `wordiness.*`, `repetition.*`, `readability.*`, `tone.*`) |
| Findings that can overlap, ordered by start then end then rule | `_drop_contained`, `Diagnostic.sort_key` |
| Personal dictionary (JSON in the data directory, atomic writes) | `PersonalDictionary` |
| API: analysis, category metadata, dictionary add/list/remove | `api.py` (`/api/workspace/diagnostics`, `/api/workspace/diagnostics/categories`, `/api/workspace/dictionary`) |
| Inline markers with per-category stroke **and** a badge letter, accessible labels, roving focus and arrow-key movement | `web/workspace.js` (`renderMarkers`, `moveMarkerFocus`) |
| Categorised sidebar with counts, error/style filters, navigation, empty state | `web/workspace.js` (`renderDiagnosticsPanel`), `web/workspace.html`, `web/workspace.css` |
| Reviewable suggestion card (original, proposal, category, explanation, alternatives, Accept, Dismiss, Add to dictionary) with the stale guard | `web/workspace.js` (`openSuggestion`, `acceptSuggestion`, `dismissSuggestion`) |
| Debounced analysis (700 ms), in-flight cancellation, and results dropped when the text changed while a request ran | `web/workspace.js` (`scheduleAnalysis`, `analyseNow`) |
| Packaged smoke checks, including "the bundled dictionary works when frozen" | `desktop_app.py` |

Rules that are deliberately **not** errors: the Latin-plural convention
("data is"), heading letter case, deliberate fragments and comma use that style
guides disagree about (reported at medium confidence with an explanation).

## 8. Test commands and results

```
python -m pytest -q                                   # 215 passed
python -m tools.repository_check                      # 0 failures
python -m flake8 . --count --select=E9,F63,F7,F82      # clean
node tests/gui/workspace_dom_check.mjs http://127.0.0.1:<port>
                                                      # GUI RESULT: PASS (101/101)
python desktop_app.py --smoke-test --smoke-report <file>
                                                      # 53 checks PASS / 0 FAIL
```

Measured analysis time on this machine: 10,000 characters in ~120 ms,
200,000 characters in ~100 ms (chunked at paragraph boundaries, dictionary
loaded once per process).

## 9. Verification that is still outstanding

- Marker **pixel alignment** over the characters: measured in a real rendering
  engine, so it needs the packaged app on Windows (WebView2) or a browser. The
  DOM checks in jsdom explicitly do not claim it.
- The frozen-build dictionary check runs in the Windows smoke gate; a Linux
  frozen build was not possible in the build environment (no `libpython3.11.so`
  available and the system library directory is not writable), so the packaged
  proof comes from the Windows CI run recorded in the pull request.
