# Verifying inline diagnostics in the packaged Windows application

This is the procedure for checking the writing workspace's inline diagnostics in
the **packaged application on Windows 11**, which is the only place where the
markers, the anchored pop-up, the caret, scrolling, focus and keyboard
navigation can be seen for real. DOM checks run in a layout engine that measures
nothing, and the backend tests never render anything.

## Status of the results in this document

| Layer | Verified here | How |
|---|---|---|
| Rules, offsets, classifications, profiles | **Yes** | `pytest` (323 tests), `tools.repository_check` (171 files, 0 failures), `flake8` |
| Text integrity (the document is the same text before and after a check, an accept changes only its own range, a save does not wipe the analysis, save/reopen is byte-identical, typing during a check survives, text with an emoji is stored and re-read byte-for-byte) | **Yes, in jsdom and at the data level** | the "Text integrity under diagnostics and refinement" and "Text representation oracle" stages in `tests/gui/workspace_dom_check.mjs`, `tests/test_workspace_text_integrity.py`, `tests/test_workspace_save_paths.py` |
| Which document a response belongs to (a late load, a late save, a switch during a save, two saves in a row, restore over unsaved edits) | **Yes, in jsdom** | the "Document identity under in-flight requests" and "Two presses of Save" stages in `tests/gui/workspace_dom_check.mjs` |
| Corrections in text that contains an emoji (the highlight covers the flagged characters and Accept changes exactly its own word) | **Yes, in jsdom** | the "Corrections in a document that contains an emoji" stage; `tests/test_workspace_save_paths.py` pins the engine's side of the offset contract |
| Interface behaviour (markers exist, labels, filters, Accept, Dismiss, stale refusal, anchored-pop-up maths, undo-preserving edits, a check that never ran is not reported as clean) | **Yes, in jsdom** | `tests/gui/workspace_dom_check.mjs`, 312 checks, three runs |
| Packaged build starts, serves the workspace, and its API answers | **Yes, in the Windows CI smoke gate** | `desktop_app.py --smoke-test`, 58 checks |
| **What a human sees in the packaged window** | **Not yet observed** | this procedure — nobody has run it yet, and no result below may be reported as passing until someone does |

Everything in the last row is written as a step with the expected observation
and a checkbox. Do not mark a step done from a CI log: the smoke gate runs
headless and cannot see a marker move.

## 0. Get the build

1. Open the pull request **#32** on the repository and find the check run named
   `build-windows-desktop` for the commit you are testing.
2. Download the artifact **`ScholarFlow-Windows-onedir`** from that run.
3. Extract it to a folder of your choice, for example
   `C:\Users\<you>\ScholarFlow\`. The application is `ScholarFlow.exe` in the
   extracted folder (`_internal\` next to it holds the bundled runtime,
   dictionary and licence notices).
4. Keep `scholarflow-smoke-log` from the same run: it is the packaged smoke
   gate's own log and should say 58 passes and 0 failures.

> Windows SmartScreen may warn about an unsigned executable. Choosing "More
> info" → "Run anyway" is expected for an unsigned internal build; it is not a
> defect of the application.

## 1. The passage to test

Paste this into a new document in the workspace (it contains one obvious
spelling error, one subject–verb agreement error, one punctuation fault, one
long and wordy sentence, a proper noun, an unfamiliar caste term, a citation and
a quotation):

```
# Caste and commons — field notes

There is many studies about this tehnique (Gupta, 2000), and the analysys is
inconclusive ,but the authors dont agree about the mechanism.

It is important to note that, in order to understand how caste plays a crucial
role in shaping access to land in the villages of Chamarajanagar district where
the Vokkaliga and Dalit households were surveyed by the team between June and
August of the fieldwork year, a number of additional interviews would have been
necessary.

As Deshpande wrote, "caste is not static", and the Adivasi households in
Hulikere reported different tenurial arrangements.
```

Expected findings, in the writer's terms:

| Where | What should be marked | Group |
|---|---|---|
| `There is many studies` | agreement (plural subject, singular verb) | Grammar |
| `tehnique` | spelling, with "technique" offered | Spelling |
| `analysys` | spelling, with "analysis" offered | Spelling |
| `inconclusive ,but` | space before the comma, missing space after it | Punctuation |
| `dont` | missing apostrophe → `don't` | Punctuation |
| the long sentence | "this sentence is N words long" (style) | Clarity |
| `It is important to note that` | formulaic opener (style) | Concision |
| `in order to` | wordier than "to" (style) | Concision |
| `Chamarajanagar`, `Vokkaliga`, `Dalit`, `Adivasi`, `Deshpande`, `Hulikere` | **nothing** — protected vocabulary | — |
| `"caste is not static"` and `(Gupta, 2000)` | nothing reported inside them for spelling | — |

## 2. What to check, and what to write down

### 2.1 Markers appear over the exact characters

- [ ] Errors are visibly marked **under the exact words** listed above, not a
      line away and not shifted by one character.
- [ ] A marker over a multi-character range (the long sentence) spans the whole
      sentence.
- [ ] Markers stay over their words while typing, scrolling and resizing the
      window.
- [ ] **Not by colour alone:** each marker also carries a letter badge (S for
      spelling, G for grammar and so on) and its `aria-label` names the kind.

### 2.2 The suggestion pop-up

- [ ] Clicking a marker opens the suggestion card **next to the marked text**,
      with its caret pointing at it, not far away at the bottom of the page.
- [ ] A finding near the bottom of the visible area opens the card **above**
      the text instead of running off the pane.
- [ ] The card shows: your original text, the proposed correction, the group and
      category, the confidence, the rule id and version, and the character
      range.
- [ ] For a finding with no safe replacement (the long sentence, the formulaic
      opener) the **Accept button is disabled** and the explanation says why.
- [ ] Pressing `Tab` moves to Accept, Dismiss, the alternatives and Close;
      `Escape` closes the card.

### 2.3 Keyboard navigation

- [ ] `Alt`+`↓` / `Alt`+`↑` move to the next / previous finding and the editor
      scrolls to it.
- [ ] `Enter` on a focused marker opens its card.
- [ ] The sidebar's Next and Previous buttons move the same way.
- [ ] Typing, `Ctrl+A`, `Ctrl+C`, `Ctrl+V` and IME input all still work in the
      editor with a card open.

### 2.4 Accept applies only the intended change

- [ ] Open `tehnique`, press **Accept**. Only that word changes: the rest of the
      sentence, the citation, the quotation, the Markdown heading and the
      paragraph breaks are byte-identical afterwards.
- [ ] The document is marked unsaved, and the sidebar re-checks and no longer
      lists that finding.
- [ ] **Press `Ctrl+Z`.** The correction is undone and `tehnique` returns. (This
      is the native-undo path the DOM checks can only approximate.)
- [ ] `Ctrl+Y` (or `Ctrl+Shift+Z`) redoes it.

### 2.5 Dismiss leaves the text alone

- [ ] Open `analysys`, press **Dismiss**. The word is unchanged and the finding
      disappears from the sidebar and the markers.
- [ ] The dismissed count appears in the sidebar summary.
- [ ] Re-checking (the **Re-check** button) does not bring it back.
- [ ] Closing and reopening this document keeps it dismissed; a *different*
      document is unaffected.

### 2.6 Stale suggestions are refused

- [ ] Open the card for `dont`, then type a word earlier in the paragraph
      without accepting anything, then press **Accept**. The text must not
      change: the card explains that the suggestion no longer matches and
      re-checks instead.

### 2.7 Corrections survive save and reopen

> Automated equivalent: the integrity stage accepts a correction, saves, reloads
> the page and compares the reopened text with what was stored, character for
> character. It also checks that the autosave which runs 2.5 s after typing does
> not empty the findings panel — that was a real defect, fixed in
> `f8714a9`, and it is worth a look here because it is the interaction a person
> notices first.


- [ ] Accept one more correction, save (`Ctrl+S`), close the application.
- [ ] Reopen the application. The Workspace restores the document **with the
      accepted corrections and without the dismissed ones coming back as new
      errors**.
- [ ] The revision history lists the saves.

### 2.8 Profiles

- [ ] The profile picker shows **Academic standard**, **Concise academic
      writing** and **Formal academic writing**.
- [ ] Switching to Formal removes the concision findings (`It is important to
      note that`, `in order to`) and keeps the spelling, agreement and
      punctuation ones.
- [ ] Switching to Concise questions the long sentence earlier.
- [ ] Switching profiles never edits the text: the editor contents are identical
      before and after, byte for byte.

### 2.9 The degraded and empty states

- [ ] A document with clean prose shows "No issues found in this document." and
      no markers — but only **after** a check has run. Before any check, the
      panel must say **"Not checked yet."** and the message "Nothing has been
      checked in this window yet…". It must not claim the text is clean: a check
      can be ended before it runs (for example by opening the same document
      again), and the panel may not turn that into a verdict. Typing one more
      character starts a check, after which findings or the clean verdict
      appear.
- [ ] An empty document says there is nothing to check yet.
- [ ] With the volume pulled out (or on a machine with no network at all), every
      check above still works: **nothing here needs the internet.**

### 2.10 A document that contains an emoji

Offsets are counted in characters by the engine and in UTF-16 code units by the
textarea. That mismatch was a real defect — every finding after an emoji pointed
one unit short, the highlight covered the wrong characters and Accept refused —
and it is fixed by converting the offsets once, where the report arrives. It is
worth looking at in the packaged window because the conversion is invisible in
ordinary prose.

- [ ] Paste this passage into the editor (the emoji is U+1F642):

      The tehnique 🙂 used here is the analysys of caste, and the evidence dont
      support it.

- [ ] After the check, the marker and the highlight are over **tehnique**,
      **analysys**, **dont** and **is**, not one character to the left or right
      of them.
- [ ] Clicking a finding moves the caret into the marked word, not the space
      before it.
- [ ] Accept the **analysys** suggestion. The word becomes **analysis**; the
      emoji, the spacing and the rest of the sentence are untouched. In a
      textarea, Accept replaces the selected range, so the browser's own undo
      (Ctrl+Z) should put the original spelling back in one step.
- [ ] Save, close, reopen: the emoji is still a single character and the
      corrected spelling is there.

### 2.11 The rest of the application still works

- [ ] The quick editor at the same window's start page still refines a passage
      and still keeps its citations.
- [ ] The **Research library** page still lists, searches and opens records, and
      the existing library workflows are unchanged.
- [ ] Creating, renaming and deleting documents still works.

## 3. How to report back

For each section above, record either the observed result or "not run". Useful
detail for a failure:

- the exact text and which word was marked (a screenshot of the editor pane with
  the marker visible is the most useful thing);
- the rule id, confidence and character range from the card;
- the contents of `%LOCALAPPDATA%\ScholarFlow\` (or the data directory shown in
  the sidebar) if a save or reopen behaved unexpectedly.

## 4. What this procedure deliberately does not claim

- It does not claim the anchoring is pixel-perfect on every DPI scaling level;
  fractional scaling can move a caret by a pixel.
- It does not claim clicking the document that is already open is harmless: that
  click ends a pending check (the stored text is adopted and the panel reset), so
  the panel says "Not checked yet." until the next keystroke. Nothing is lost —
  the text is untouched and the draft still holds any edit — but the check has to
  be started again.
- It does not claim text the store cannot represent can be saved. A lone
  surrogate (half an emoji, as an ill-formed paste can leave behind) is refused
  with the message "That request was rejected by validation: text."; the editor
  keeps the text and this browser keeps the draft, but the document on disk is
  not updated until the stray half is removed. Before the fix this answer was a
  server error, which said nothing about what to do.
- It does not claim the automated checks observed any of the above: they run in
  jsdom (no layout, no undo stack) and in a headless smoke gate (no window).
- It does not claim Windows 11 verification has happened yet. That is what this
  checklist is for.
