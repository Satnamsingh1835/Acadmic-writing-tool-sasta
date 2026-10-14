# ScholarFlow desktop repair — findings and verification

Branch: `arena/883f6125-acadmic-writing-tool-sasta` · Commit: `2bb8de9`
Pull request: [#32](https://github.com/Satnamsingh1835/Acadmic-writing-tool-sasta/pull/32)

This report separates what was reproduced and fixed from what still requires
the researcher's own Windows computer.

## 1. What was actually wrong

### 1.1 Research Library: references could not be added from the page

`POST /api/library/work` existed and worked, but `web/library.html` had no form
and `web/library.js` never called it. The only ways to add records were CSL/Zotero
import. Opening `/library` also showed an empty result area until a search was
submitted, so a working local database looked blank after a restart.

The database layer itself was verified working and was not changed: schema
creation, work/DOI/title de-duplication, FTS5 with LIKE fallback, search filters
(author, year, item type, access status, sort), CSL JSON import, TXT/Markdown/PDF
indexing with PDF page numbers, passage search, evidence-brief warnings, the
literature matrix, settings, and persistence across a full process restart.

### 1.2 The packaged application was never executed

`scripts/build_windows_desktop.ps1` and `.github/workflows/windows-desktop.yml`
only compiled the bundle and uploaded it. A package whose local server failed to
start, whose web assets were missing, or whose database could not be written
still produced a green build and a downloadable artifact — which is how a
broken desktop application could be reported as "built successfully". Nothing
in the repository could detect that class of failure.

A third, smaller defect was found while fixing this: the spec used
`Path.cwd()`, so a build launched from another working directory would resolve
resources incorrectly.

## 2. Changes made

| File | Change |
|---|---|
| `web/library.html`, `web/library.js`, `web/library.css` | "Add a reference" form wired to `POST /api/library/work`; the page now lists existing records on load and reports duplicates instead of doing nothing. |
| `desktop_app.py` | Server startup factored into `_start_server`/`_stop_server`; new headless `--smoke-test` (+ `--smoke-report PATH`) mode that starts the real server without importing `pywebview`; `ensure_standard_streams()` so a windowed build (`console=False`, where `sys.stdout`/`sys.stderr` are `None`) can never crash on output. |
| `ScholarFlowDesktop.spec` | `Path(SPECPATH)` instead of `Path.cwd()`. |
| `scripts/build_windows_desktop.ps1` | Runs the packaged smoke check after building and fails the build when it fails. |
| `.github/workflows/windows-desktop.yml` | New "Smoke-test the packaged application" step (with `::error` annotations and an uploaded `smoke-test.log`); the build artifact is only uploaded for a build that passes it. |
| `tests/test_desktop_app.py`, `tests/test_research_library_api.py` | Regression tests: smoke path, "never imports webview", isolated temp data directory, windowed build with no `sys.stdout`, add-reference form/endpoint and persistence in a freshly opened store. |
| `README.md`, `docs/FEATURE_STATUS.md`, `docs/REA_WINDOWS_RUNBOOK.md` | Documented the new verification path and status. |

Safety properties of the smoke run: it uses an isolated temporary data directory
unless `SCHOLARFLOW_DATA_DIR` is already set, it creates only synthetic records,
and it writes only check names and HTTP status codes — never passage text,
document content or credentials.

## 3. Verification: what passed, where

### Verified locally in this sandbox

| Check | Result |
|---|---|
| `pytest` (full repository suite) | 125 passed |
| `python -m tools.repository_check` | 144 files, 0 failures |
| `flake8 --select=E9,F63,F7,F82` | clean |
| `python desktop_app.py --smoke-test` | 28/28 checks PASS |
| Desktop startup simulation (listener → health → window URL → editor/asset/library requests → `/editor/rewrite`) | PASS |
| Editor driven end-to-end in jsdom against a live server: sample, all three modes, results, tabs, receipts, upload, copy, clear, error toast, AI disabled fallback | PASS |
| Library driven end-to-end in jsdom: status, add reference, duplicate detection, listing, search, CSL import, TXT indexing, passage search, matrix, settings, Zotero failure message | PASS |
| PDF indexing with extracted page numbers, Markdown indexing, search filters (type/year/sort/author) via API | PASS |
| Persistence across a full server restart | PASS |
| PyInstaller analysis build: `web/` assets and all Python modules present in the bundle | PASS |

### Verified in CI (GitHub Actions, real Windows)

| Check | Result |
|---|---|
| Python CI, Research Synthesist CI, R, CodeQL on commit `2bb8de9` | pass |
| Windows job: tests, PyInstaller one-folder build | pass |
| Windows job: **packaged `ScholarFlow.exe --smoke-test`** | pass (this gate failed before the windowed-mode fix, which is how the missing output path was confirmed) |

The packaged check covers: bundled assets, `/health`, editor capabilities, all
three editor profiles producing refined text with receipts and safeguards, the
no-provider fallback, library health/settings, adding a reference and finding it,
CSL JSON import, TXT indexing, passage search, matrix add/list, and reopening the
SQLite database from disk.

### Not covered anywhere — requires your Windows computer

- The pywebview window itself (WebView2 rendering of both pages).
- File pickers: TXT upload in the editor, CSL JSON and PDF/DOCX/TXT selection in the library.
- Clipboard copy and download-to-disk behaviour.
- Zotero Desktop's local API and the private Zotero Web API.
- An external AI provider, if you configure one.

## 4. External configuration vs software defects

These are configuration requirements, not defects:

- **AI enhance** needs `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`. With no key the
  toggle is disabled and the local deterministic editor is used — this is by design.
- **Zotero Desktop import** requires Zotero to be running with
  Settings → Advanced → "Allow other applications on this computer to communicate
  with Zotero" enabled.
- **Zotero Web import** requires `ZOTERO_USER_ID` and `ZOTERO_API_KEY` in the local
  environment; never commit them.
- **Crossref/OpenAlex discovery** needs network access; offline mode returns cached
  or empty results by design.
- **Microsoft Edge WebView2 Runtime** is required for the desktop window
  (preinstalled on Windows 11).
- **Scanned PDFs** are not OCR-processed; the app says so instead of failing silently.

## 5. Windows 11: install or replace, then test

### Get the build

Download the artifact from the latest green **Windows desktop build** run for this
branch: <https://github.com/Satnamsingh1835/Acadmic-writing-tool-sasta/pull/32/checks>
→ the `build-windows-desktop` check → **Artifacts** → `ScholarFlow-Windows-onedir.zip`
(14-day retention). The same run also uploads `scholarflow-smoke-log` with the
per-check results produced by the packaged executable.

Or build it yourself: install Python 3.12 (`py -3.12` must work), then in the
repository root:

```powershell
.\scripts\build_windows_desktop.ps1
```

The script runs the tests, builds, and then runs the packaged smoke check — if the
check fails, treat the build as broken and send the printed `SMOKE FAIL` lines.

### Install or replace

1. Close ScholarFlow if it is running.
2. Extract the zip anywhere (for example `C:\Users\<you>\Apps\ScholarFlow`).
   Keep the whole folder together; do not move `ScholarFlow.exe` out on its own.
3. Replace: rename the old `ScholarFlow` folder (for example to
   `ScholarFlow-old`) and extract the new folder in its place — renaming instead
   of deleting lets you roll back.
4. Your data is not inside the app folder. It lives in
   `%LOCALAPPDATA%\ScholarFlow` (`research-library.sqlite3`, `documents`, `logs`)
   and survives replacement. Copy that folder somewhere safe before a big change.

### Test the Writing Editor

1. Launch `ScholarFlow.exe`.
2. The header should read **Engine ready**; **AI enhance** should be disabled and
   say "Provider not configured" unless you configured a model.
3. Click **Try sample**, keep **Standard**, click **Refine passage**.
4. Confirm refined text appears on the right, and that the report below shows
   suggestions, structure prompts, safeguards, and a revision receipt.
5. Click **Light** and **Polish** and refine again — each should still return text.
6. Try **Copy**, **Download**, **Clear**, and **Upload .txt**, then close the window.

### Test the Research Library

1. In the app click **Research library** (or open `/library`).
2. Status should read "Local database ready · N records…".
3. Fill **Add a reference** (title is enough) and click **Add reference**.
4. The record should appear in the list immediately.
5. Close the app completely, relaunch, open the library — the record must still
   be listed. This is the persistence test.
6. Also try: search by keyword, a CSL JSON import, indexing a small TXT or PDF,
   passage search for a word you indexed, and saving a literature-matrix row.
7. Zotero import with Zotero closed should show a readable message, not a blank page.

### If something fails

Send the file `%LOCALAPPDATA%\ScholarFlow\logs\desktop.log` (and `smoke-test.log`
from the project root if you built locally). Both contain diagnostics without
credentials or manuscript contents.
