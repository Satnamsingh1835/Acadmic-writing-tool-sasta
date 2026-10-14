# Stage 3 — production-quality inline diagnostics: plan and log

Status: implementation log for the milestone requested as *"ScholarFlow Stage 2 —
Production-Quality Inline Writing Diagnostics"*. It continues the work recorded
in `docs/STAGE2_DIAGNOSTICS_PLAN.md`; nothing from Stage 1 or Stage 2 was reset,
reverted or rewritten. PR #32 stays open.

## 0. Starting point (verified, not assumed)

| Item | Value |
|---|---|
| Branch | `arena/883f6125-acadmic-writing-tool-sasta` |
| HEAD before this milestone | `1c4ed53b9cd0f5b0ca408d648891ce53c6cce1b5` (11 commits; stage 2 already implemented on this branch) |
| Pull request | #32, open, merge state CLEAN, not merged |
| Baseline suite | `python -m pytest -q` → 216 passed |
| Editor surface | `<textarea id="editor">` with a `<div id="marker-mirror">` metrics mirror and `<div id="marker-layer">` for markers — character offsets, no framework migration |

The requested base commit `882f744a…` is Stage 1; Stage 2 has since been built on
top of it on the same branch, so this milestone extends the current head instead
of restarting from the older commit.

## 1. What already existed and what this milestone adds

Stage 2 already delivered: ten rule families with exact offsets, a Markdown mask
and prose view, inline markers with a text mirror, a categorised sidebar with
error/style filters, a suggestion card with Accept/Dismiss/alternatives and a
stale-range guard, a personal dictionary, debounced analysis, and an
accept-then-reanalyse loop. This milestone keeps all of that and adds the parts
the request asks for that were missing:

1. **A canonical, versioned diagnostic contract** — engine/ruleset/rule versions,
   the requested higher-level category taxonomy (spelling, grammar, punctuation,
   sentence structure, clarity, concision, academic style, repetition) alongside
   the precise rule category, and a documented offset convention.
2. **Spelling precision** — a confirmed misspelling (an unknown word with a
   dictionary neighbour) is now distinguished from an unknown word with no
   candidate, and an unfamiliar word is never auto-replaced.
3. **False-positive protection for research vocabulary** — names, caste and
   community terms, place names, specialist concepts, abbreviations and acronyms
   are protected by a bundled lexicon plus structural rules (consistent
   capitalisation, acronym shape, digit-bearing tokens, hyphenated compounds).
4. **Rule families that were missing** — `a`/`an` before a vowel sound, missing
   apostrophes in contractions, mass nouns wrongly pluralised, a small
   high-precision redundant-preposition set, and an ambiguous `This` sentence
   opener.
5. **Academic profiles** — Academic Standard, Formal Academic Writing and Concise
   Academic Writing, which enable, disable or reprioritise the *style* rules while
   spelling and the reliable grammar rules stay on in every profile.
6. **Anchored suggestion pop-up** — the suggestion card is positioned next to the
   marker it belongs to, with the inline card kept as the fallback when the
   surface cannot be measured (jsdom, very small panes).
7. **Undo/redo that survives a correction** — programmatic edits go through
   `document.execCommand("insertText")` so the browser's native undo stack keeps
   working, with a direct-assignment fallback for environments without it.
8. **A Windows verification procedure** for the packaged app, marked for what was
   actually observed here and what still needs the researcher's Windows 11 PC.

## 2. Files to change

| File | Change |
|---|---|
| `diagnostics.py` | taxonomy, versions, profiles, protection layer, new rules |
| `api.py` | profile parameter, `GET /api/workspace/diagnostics/profiles`, engine cache key |
| `web/workspace.html` | profile select wiring, total-count element, pop-up container semantics |
| `web/workspace.js` | anchored pop-up, totals, unavailable state, undo-safe edits, profile change |
| `web/workspace.css` | pop-up positioning and focus styles |
| `tests/test_diagnostics.py`, `tests/test_diagnostics_rules.py` (new) | rule and contract tests |
| `tests/test_workspace_diagnostics_api.py` | profile and privacy tests |
| `tests/gui/workspace_dom_check.mjs` | DOM checks for the new interaction |
| `docs/*` | this file, the workspace plan, the Windows test procedure |

## 3. Offset convention (unchanged, restated for the contract)

Offsets are Python string indices into the text exactly as submitted, which is
also JavaScript's unit for `selectionStart`/`slice`, so no conversion happens in
either direction. Newlines count as one character even when the file later uses
CRLF. Em dashes, curly quotes and non-BMP characters are single indices in both
languages because JavaScript strings and Python `str` are both sequences of code
points. Text outside the analysed prose (heading markers, list bullets, block
quote markers, table pipes, link destinations, front matter, code fences and the
reference list) is *masked*: findings are only reported on the prose view, and
every range is mapped back through the view's segment table before it leaves the
engine, so a finding can never point at a character it did not inspect.

## 4. Verification

Unit tests per rule, API tests for the endpoints and their privacy guarantees,
DOM checks for the interface, the packaged smoke gate, and the Windows procedure
in `docs/WINDOWS_DIAGNOSTICS_TEST.md`. Results are recorded in section 6 as they
are produced; a result is only written down once it has actually been observed.
