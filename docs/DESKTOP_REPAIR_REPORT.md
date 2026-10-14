# ScholarFlow desktop repair — findings and verification

Branch: `arena/883f6125-acadmic-writing-tool-sasta`
**Code commit verified by the packaged Windows smoke test:
`62585396f1e3882c2487fbe92c8c1240c86f9568`**
Pull request: [#32](https://github.com/Satnamsingh1835/Acadmic-writing-tool-sasta/pull/32)

## Provenance of the tested build

| Item | Value |
|---|---|
| Tested code commit | `62585396f1e3882c2487fbe92c8c1240c86f9568` |
| Workflow run (Windows desktop build) | <https://github.com/Satnamsingh1835/Acadmic-writing-tool-sasta/actions/runs/38515140216> |
| Run head SHA (verified via API) | `62585396f1e3882c2487fbe92c8c1240c86f9568` — identical to the tested commit |
| Result | `success` (tests → PyInstaller build → packaged smoke test all passed) |
| Application artifact | `ScholarFlow-Windows-onedir` (27,593,125 bytes, built 2026-10-14T05:11:14Z) — its `workflow_run.head_sha` is `62585396…9568`, so the artifact was built from this commit |
| Smoke-test log artifact | `scholarflow-smoke-log` (668-byte zip, same run and head SHA) |
| PyInstaller log artifact | `pyinstaller-logs` (same run) |

To download: open the run page linked above, scroll to the **Artifacts** section at
the bottom and click the artifact name (`ScholarFlow-Windows-onedir` for the
application, `scholarflow-smoke-log` for the Windows check results). GitHub only
serves artifacts to a signed-in user, so direct artifact URLs cannot be opened
anonymously — always go through the run page.

A copy of the same 28-check report, produced locally by the identical code path,
is kept outside the repository at `scholarflow-smoke-log-6258539.txt` in the
workspace root. Downloading artifacts *from this sandbox* is not possible
because GitHub redirects artifact and log downloads to
`*.blob.core.windows.net`, which is outside this environment's network allowlist;
the artifacts above are present, unexpired (verified through the API) and
downloadable from a normal browser.

Commit `6258539` is the last commit that changes application code. Any later
commit on this branch contains documentation or CI reporting only; check
`git log --oneline` for the current head.

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

Test counts are reported once and separated by where they ran. Earlier revisions
of the pull request quoted "123 passed"; that count predated the two regression
tests added by this repair and is superseded by the numbers below.

### A. Local checks in this Linux sandbox (same code as the tested commit)

| Check | Result |
|---|---|
| `pytest` (full repository suite, `tests/` + root `test_*.py`) | **125 passed** |
| `python -m tools.repository_check` | **145 files, 0 failures** |
| `flake8 --select=E9,F63,F7,F82` | clean (0 findings) |
| `python desktop_app.py --smoke-test --smoke-report …` | **28 checks PASS, 0 FAIL**, exit 0 |
| Desktop startup simulation (listener → health → window URL → editor/asset/library requests → `/editor/rewrite`) | PASS |
| Editor driven end-to-end in a DOM against a live server: sample, all three modes, results, tabs, receipts, TXT upload, copy, clear, error toast, AI-disabled fallback | PASS |
| Library driven end-to-end in a DOM: status, add reference, duplicate detection, listing, search, CSL import, TXT indexing, passage search, matrix, settings, Zotero failure message | PASS |
| API probes: PDF indexing with extracted page numbers, Markdown indexing, search filters (type/year/sort/author) | PASS |
| Persistence across a full process restart (fresh library instance on the same database file) | PASS |
| PyInstaller analysis build: `web/` assets and every Python module present in the bundle | PASS |

### B. Windows CI (GitHub Actions, `windows-latest`, run 38515140216 at `62585396…`)

| Step | Result |
|---|---|
| `Run tests` (`python -m pytest -q`, same suite as above) | **pass** |
| `Build one-folder desktop distribution` (PyInstaller) | pass |
| **`Smoke-test the packaged application`** (`ScholarFlow.exe --smoke-test`) | **pass** — 28 checks, no `SMOKE FAIL` lines |
| `Upload build artifact` | pass (`ScholarFlow-Windows-onedir`) |
| Other workflows on the same commit: Python CI, Research Synthesist CI, R, CodeQL | all pass |

The 28 packaged checks are: six bundled assets, six page/script/style routes,
`/health`, editor capabilities, three editor profiles producing refined text with
receipts and safeguards, the AI-requested local fallback, library health,
library settings, adding a reference, finding that reference by search, CSL JSON
import, TXT document indexing, passage search, matrix add, matrix list, and
reopening the SQLite database from disk to prove persistence.

Notes on what these results do and do not cover:

- The Windows `Run tests` step ran the identical suite that reports **125 passed**
  locally. The number printed inside that CI job is not quoted here because this
  sandbox cannot read the job log: GitHub redirects log downloads to
  `*.blob.core.windows.net`, which is outside this environment's allowlist, so
  `gh run view --log` fails with an EOF error. The step's pass/fail status and
  the artifact metadata were taken from the GitHub API, which is reachable.
- The packaged smoke test passed *after* the windowed-build fix. Before that fix
  the same gate failed on Windows, which is how the missing-output-path defect
  was found; that failure is genuine test evidence, not a flake.
- Everything in section B was executed on Windows. Everything in section A was
  executed on Linux against the same commit.

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

Open the run listed in the provenance table above
(<https://github.com/Satnamsingh1835/Acadmic-writing-tool-sasta/actions/runs/38515140216>),
scroll to the **Artifacts** section at the bottom of the page, and click
`ScholarFlow-Windows-onedir` (or the newest green **Windows desktop build** run for
this branch, reachable from
<https://github.com/Satnamsingh1835/Acadmic-writing-tool-sasta/pull/32/checks>).
Artifacts expire after 14 days; every new run rebuilds them.

The same run also uploads `scholarflow-smoke-log` with the per-check results the
packaged executable produced on Windows.

Or build it yourself: install Python 3.12 (`py -3.12` must work), then in the
repository root:

```powershell
.\scripts\build_windows_desktop.ps1
```

The script runs the tests, builds, and then runs the packaged smoke check — if the
check fails, treat the build as broken and send the printed `SMOKE FAIL` lines.

### Install or replace (beginner steps, Windows 11)

1. Close ScholarFlow if it is already running.
2. In your browser, sign in to GitHub as the repository owner, open the run link
   above, scroll to **Artifacts**, and click **ScholarFlow-Windows-onedir.zip**.
   Your browser saves it in the **Downloads** folder.
3. Right-click the downloaded **ScholarFlow-Windows-onedir.zip** → **Extract All…**
   → choose a permanent place such as `C:\Users\<you>\Apps\ScholarFlow` → **Extract**.
   Windows 11 can also open the file and use the **Extract all** button at the top.
4. Open the extracted folder. Inside it you will see `ScholarFlow.exe` next to an
   `_internal` folder. Keep them together — do not move `ScholarFlow.exe` out on
   its own, and do not run it from inside the zip.
5. To replace an older copy: rename the existing `ScholarFlow` folder (for example
   to `ScholarFlow-old`) instead of deleting it, then put the new folder in its
   place. If the new version misbehaves you can rename the old folder back.
6. Your work is **not** inside the app folder. It is stored in
   `%LOCALAPPDATA%\ScholarFlow` (`research-library.sqlite3`, `documents`, `logs`).
   Paste `%LOCALAPPDATA%\ScholarFlow` into File Explorer's address bar to see it,
   and copy that folder somewhere safe before a big change.
7. Double-click `ScholarFlow.exe`.
   - If Windows shows a blue "Windows protected your PC" box, click **More info**
     → **Run anyway** (the app is unsigned).
   - The first launch can take a few seconds while the local server starts.
   - ScholarFlow needs the Microsoft Edge WebView2 Runtime; it is preinstalled on
     Windows 11, so normally nothing extra is required.

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

Send the file `%LOCALAPPDATA%\ScholarFlow\logs\desktop.log`. Copy the path
`%LOCALAPPDATA%\ScholarFlow\logs` into File Explorer's address bar to open the
folder, then attach `desktop.log` to your message. It records diagnostics only —
no credentials and no manuscript or document text.
