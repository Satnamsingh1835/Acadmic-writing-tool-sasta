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

## 4. Architecture and data flow

```
  textarea (#editor)                    marker mirror + layer
        │  input                                          ▲ positioned markers
        ▼                                                 │ (measured from the mirror)
   markDirty() ──► scheduleAnalysis(700 ms debounce) ─────┤
        │                                                 │
        │ POST /api/workspace/diagnostics                 │
        │   {text, document_id, revision, profile}        │
        ▼                                                 │
  api.workspace_diagnostics ──► DiagnosticEngine.analyse ─┘
        │                        (deterministic, local)
        │  mask → prose view → rules → findings (offsets in the
        │  caller's own string) → counts, metrics, notes
        ▼
  editor state: findings, counts, categories, metrics, notes
        │
        ├─► renderMarkers()          one per range, focusable, labelled
        ├─► renderDiagnosticsPanel() sidebar grouped by category, filters, totals
        └─► anchored suggestion pop-up (Accept / Dismiss / alternatives)

  Accept ──► validate (analysed text unchanged AND the characters at those
             offsets still equal `original`) ──► applyEdit() ──► re-analyse
  Dismiss ─► remember the finding id per document; the text is not touched
```

The engine is a pure function of (text, profile, categories): it reads no
document store, contacts no service, and the API tests assert that a check
cannot change a stored document. The editor keeps its own text; a finding is
only ever data about that text, which is what makes "never silently rewrite"
checkable rather than a promise.

**Markdown and offsets.** `_Mask` marks fenced code, inline code, YAML front
matter, link targets and the reference list; `_ViewBuilder` then produces the
prose with structural markers (heading hashes, bullets, quote markers, table
pipes) removed while keeping a segment table back to the original indices.
Findings are reported in the caller's string, so `text[start:end] == original`
always holds — that identity is asserted in the unit tests, in the API tests and
in the GUI checks, and the packaged smoke gate re-checks it inside the Windows
build.

**Rule families (32 rules).**

| Group | Rules | Kind |
|---|---|---|
| Spelling | `spelling.misspelling`, `spelling.unknown-word` | error |
| Grammar | `agreement.plural-subject`, `agreement.indefinite-pronoun`, `agreement.latin-plural-convention`, `agreement.demonstrative`, `agreement.article-with-plural`, `grammar.article-an`, `grammar.mass-noun-plural`, `grammar.redundant-preposition` | error (`agreement.latin-plural-convention` is style) |
| Punctuation | `punctuation.missing-space`, `punctuation.space-before-mark`, `punctuation.doubled-mark`, `punctuation.unclosed-bracket`, `punctuation.unmatched-bracket`, `punctuation.missing-apostrophe` | error |
| Capitalisation | `capitalization.sentence-start`, `capitalization.pronoun-i`, `capitalization.proper-adjective` | error |
| Sentence structure | `fragment.no-main-clause`, `run_on.comma-splice` | error, medium confidence |
| Clarity | `readability.long-sentence`, `readability.long-paragraph`, `clarity.ambiguous-this` | style |
| Concision | `wordiness.longer-phrase`, `wordiness.formulaic-opener` | style |
| Academic style | `tone.contraction`, `tone.vague-quantifier`, `tone.overclaim` | style |
| Repetition | `repetition.repeated-word` (a doubled word is an error) | error |
| Repetition | `repetition.overused-word`, `repetition.overused-phrase` | style |

## 5. Academic profiles

| Profile | Style categories reported | Length thresholds | Rule |
|---|---|---|---|
| Academic Standard | clarity, concision, academic style, repetition | 35-word sentences, 220-word paragraphs | `academic_standard` |
| Formal Academic Writing | clarity, academic style, repetition | 45-word sentences (formal prose is allowed to run longer) | `formal_academic` |
| Concise Academic Writing | clarity, concision, repetition | 28-word sentences, 170-word paragraphs | `concise_academic` |

Spelling and every reliable grammar, punctuation and capitalisation rule run in
all three; the tests assert that, and the profile is returned in the report so a
client can show what was actually checked. A profile only chooses findings and
their sidebar priority — the response carries the same `text_sha256` whichever
profile produced it, which is the machine-checkable form of "a profile never
rewrites the text".

## 6. Dependency and licence decisions

`pyspellchecker` 0.8.2 (MIT) provides the English dictionary and the frequency
table used to rank candidates. It is pure Python, works offline, ships its
dictionary as package data (`resources/en.json.gz`, ~650 KB), and PyInstaller
collects it through `collect_all("spellchecker")`; the packaged smoke gate fails
if the frozen build cannot load it. The MIT notice is vendored in
`packaging/third_party/pyspellchecker-LICENSE.txt`, shipped inside the build, and
listed with every other dependency in `THIRD_PARTY_NOTICES.md`.

Rejected for the reasons recorded in `docs/WRITING_WORKSPACE_PLAN.md` §3:
LanguageTool needs a Java process and LGPL relinking obligations in a frozen
build; Harper needs a Rust toolchain; cloud grammar services are never used.

## 7. Privacy and offline behaviour

Every rule is deterministic Python, the dictionary is bundled, and analysis is a
pure function of the text. The response states `external_services: "none"` and
the engine name and versions; the interface repeats the promise next to the
results. Nothing is logged: the request model deliberately has no `max_length`
on `text`, because a pydantic validation error would echo a snippet of the
document back in the error body (a test pins this). The personal dictionary is
plain JSON in the user's data directory and dismissals are a per-document list
in `localStorage`; neither is uploaded anywhere.

## 8. Test commands and results

```
python -m pytest -q                                   # 310 passed (all 184 GUI checks included)
python -m tools.repository_check                      # 170 files, 0 failures
python -m flake8 . --count --select=E9,F63,F7,F82      # clean
node tests/gui/workspace_dom_check.mjs http://127.0.0.1:8800
                                                      # GUI RESULT: PASS (130/130), twice
python desktop_app.py --smoke-test --smoke-report <f>  # 58 PASS / 0 FAIL
python -m tools.diagnostics_timing                     # 43 shapes, 0 flagged
python -m tools.diagnostics_timing --pastes            # the table below
```

Measured analysis time on this machine (single analysis, warm dictionary):

| Document | Characters | Time | Findings |
|---|---|---|---|
| Short section | 176 | <1 ms after warm-up | 3 |
| Article | 7,040 | 19 ms | 268 |
| Long article | 70,400 | 217 ms | 600 (capped) |
| Adversarial: 20,000 unknown words | 99,999 | 236 ms | 247 |
| Adversarial: 20,000 repeated typos | 79,999 | 198 ms | 243 |
| Adversarial: 5,000 citations | 69,999 | 253 ms | 15 |
| Plan document | 11,216 | 44 ms | 113 |

Performance defects found and fixed by these measurements. Four of them were
only visible on a *paste*, which is how a person notices the editor freezing,
and none of them can be seen in ordinary prose:

| Defect | Before | After |
|---|---|---|
| The mask lookup walked every masked range for every character | 160 ms on 11k / 1.7 s on 112k | 51 ms / 475 ms |
| The protected-span lookup walked every citation for every word | 1.6 s citation-dense | 253 ms |
| The email pattern consumed a whole unbroken token at every offset | 3.5 s on 50,000 characters | 71 ms |
| The abbreviation walk rescanned a run of dots once per full stop | **214 s** on 40,000 dots | 489 ms |
| The whitespace-run pattern retried the run at every offset | 8.3 s on 40,000 spaces | 61 ms |
| The comma-splice rule rebuilt both sides of every comma | 24.1 s on 40,000 commas | 71 ms |
| The Markdown link patterns rescan open brackets | 703 ms on 40,000 brackets | 125 ms |

**The analysis belongs to the text it was made from.** Two defects in that
interaction were found by driving the real page and fixed in `f8714a9`: an
autosave (2.5 s after typing) cleared the findings, so the panel announced "no
issues found" about text nobody had re-checked and the card a person was reading
closed itself; and start-up could write a stored document over text typed while
the document list was still loading, which belonged to no draft and to no
revision. The editor now clears findings only when it writes stored text or
opens another document, keeps text that no document owns, and validates every
range — and the original text at that range — immediately before writing, so a
suggestion that no longer matches is refused instead of spliced.

`tools/diagnostics_timing.py` sweeps 43 paste shapes at two sizes and prints a
ratio, so a scan that is quadratic (ratio ≈ 4) stands out from one that is
linear (ratio ≈ 2). It reports `0 flagged` now; the test suite keeps loose
ceilings that catch an order-of-magnitude regression without failing on a slow
shared runner.

All of the above was run on the final commit `88be026`, and the same commit is
green in CI: the Ubuntu job (`test`, Python 3.10), the Windows job
(`build-windows-desktop`, Python 3.12, which also runs the packaged smoke test)
and `check (release)`. The earlier red runs were the timing assertion: the
budgets were too tight for a shared runner and the scans behind them were
genuinely quadratic, so the fix was to make the code fast and keep the test as a
coarse regression guard rather than to loosen the test on its own.

## 9. Known false positives and honest limitations

**Text removed from the prose view can create neighbours that do not exist.**
Code spans, link targets, URLs and email addresses are removed before the rules
run, because they must not be checked as prose. The words on either side of the
hole are still emitted, so a rule that compares two neighbouring tokens could
see a pair that was never adjacent in the document. Three cases were found and
fixed by keeping a record of where the document text was elided and consulting
it in the rules that care:

| Text | Was reported as | Now |
|---|---|---|
| ``Use the `code` the way shown.`` | `repetition.repeated-word` ("the the"), high confidence | not reported |
| ``Text with a `code span` inside.`` | `grammar.article-an` ("a inside") | not reported |
| `See [the study](https://example.org/a/b).` | `punctuation.unclosed-bracket` | not reported |

The suppression is bounded: a bracket is only left alone when something was
elided between it and the end of its line, and a doubled word or article pair is
only skipped when the hole sits exactly between the two words. Genuinely
unbalanced brackets, genuinely doubled words and genuine article errors in the
same documents are still reported, and tests pin both directions.

- **Sentence-initial capitalised words with a candidate** are reported at
  `medium` confidence, because "Teh" could in principle be a name. A capitalised
  unknown word with *no* candidate is not reported at all: flagging every
  unfamiliar proper noun is how a checker loses a writer.
- **Names are protected structurally**, not by a complete list: a word the
  author capitalises away from a sentence start anywhere in the document is
  treated as a proper noun. A surname that only ever appears at a sentence start
  and has no dictionary neighbour is silently ignored, which is deliberate.
- **The bundle is not an ontology.** `diagnostic_lexicon.py` is a curated start
  (names, caste and community terms, places, field concepts, survey
  abbreviations, ~1,170 words). The personal dictionary remains the way to
  protect the exact vocabulary of a project.
- **US-English dictionary.** British spellings are accepted through variant
  rules. Words in other scripts are not checked, because the dictionary is
  English; they are never reported as misspellings.
- **Fragment, run-on and agreement rules are heuristic** and reported at medium
  confidence. `agreement.latin-plural-convention` ("the data is") is a style
  option, not an error, because both conventions are in use.
- **Mass-noun and preposition rules are deliberately tiny.** "researches",
  "trainings" and "evidences" are ordinary in Indian and legal English and are
  not flagged.
- **Spelling stops examining a document** after the per-rule cap is reached plus
  40 further unknown words with no finding; the report says so through
  `truncated` and a note, rather than quietly returning a partial list.
- **Marker pixel alignment is not verified by the automated checks.** jsdom has
  no layout engine, so the DOM checks verify marker identity, labels, ordering and
  behaviour, and the anchoring maths is verified against a *stubbed* layout. Real
  alignment needs WebView2 — see `docs/WINDOWS_DIAGNOSTICS_TEST.md`.
- **Undo after an accepted correction** goes through
  `document.execCommand("insertText")`, which is what keeps the browser's own undo
  history. The DOM checks verify that the page selects the finding's exact range
  and hands over the exact text, using a stand-in for the command; whether the
  browser then undoes it is a WebView2 behaviour that has to be seen on Windows.

## 10. Deferred work

- Spell-checking words in other scripts, and an Indian-English variant dictionary.
- Grammar rules that need a parser (articles in complex noun phrases, tense and
  agreement across subordinate clauses).
- Per-change bulk review with receipts (Stage 4 in the workspace plan) and the
  optional, consent-gated AI pass.
- A style-guide selector (Chicago, APA, journal-specific) for punctuation rules.
- Native automated GUI verification on Windows (see the procedure document).
