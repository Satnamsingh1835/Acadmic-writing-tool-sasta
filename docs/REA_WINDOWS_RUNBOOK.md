# Windows 11 runbook: ScholarFlow desktop, Zotero and REA

This separates repository tasks from actions that require the user's Windows computer. Script preparation and CI do not prove local Windows or Zotero behavior.

## A. Start the local website

From the project root in PowerShell:

```powershell
python -m pip install -r requirements.txt -r requirements-research.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` for the editor or `http://127.0.0.1:8000/library` for the research library. Stop with Ctrl+C. Do not bind the application to a public interface.

## B. Build the native desktop package

Requirements: Windows 11, Python 3.12 available as `py -3.12`, Microsoft Edge WebView2 Runtime, and network access for dependencies.

```powershell
.\scripts\build_windows_desktop.ps1
```

Launch `dist\ScholarFlow\ScholarFlow.exe`. Verify that the native window opens, the editor and Research Library load, synthetic text can be reviewed, a TXT document can be indexed, and the app exits cleanly. The output is a one-folder distribution, not an MSI installer. The Windows CI artifact still needs acceptance on the target PC.

If script execution is blocked, inspect the local execution policy. Do not globally disable Smart App Control or weaken system security merely to run a script.

## C. REA readiness check — default is dry-run

Run:

```powershell
.\scripts\rea-readiness.ps1
```

It checks Node/npm and queries package metadata for pinned `rea-agents@6.4.0`, writing non-secret diagnostic files to the Git-ignored `.rea-local` directory. It does not alter agent configuration by default.

The inspected REA 6.4.0 manifest lists Node.js 22.19+, 24.11+ or 26+. Check the current official instructions at https://rea.tools/get-started/ before setup.

## D. Interactive REA setup

After reviewing the dry-run output:

```powershell
.\scripts\rea-readiness.ps1 -RunSetup
```

Type `RUN_SETUP` only if you intend to open the official interactive setup. Review the proposed plan and approve only the intended supported local coding agent. A prior audit did not find Arena as a supported client, so do not assume it can be connected as the REA agent.

After setup, restart the selected agent and run the exact doctor command documented for that client. For example, if you selected Codex:

```powershell
npx -y rea-agents@latest doctor --client codex --json
```

Share only non-sensitive diagnostic summaries. Never share tokens, cookies, complete agent config files, private browser-profile data or Zotero library contents.

## E. Observe public free workflows

Use only public, normally accessible Grammarly Free and QuillBot Free features and original passages from `docs/rea-study/fixtures.md`. Record actual action, page URL, timestamp, visible output, controls, limits and uncertainty. Use the evidence labels directly observed, publicly documented, inferred, or not tested.

Do not bypass authentication, paywalls or usage limits, or inspect private APIs, prompts or model internals. Do not mark product reports complete until actual observations and evidence are saved.

## F. Zotero

Zotero Desktop must be open and the user must enable Settings → Advanced → “Allow other applications on this computer to communicate with Zotero” for its local API. Import is read-only. Start with a small selected collection. For a private Web library, configure `ZOTERO_USER_ID` and `ZOTERO_API_KEY` in the local process environment; never put the key in Git.

Official docs: https://www.zotero.org/support/dev/web_api/v3/local_api and https://www.zotero.org/support/dev/web_api/v3/basics

## G. Acceptance checklist

Mark these items verified only after actual tests: repo suite; Windows package launches and closes; Zotero import returns items; selected REA client passes doctor; competitor UI observations have dated evidence. CORE, semantic embeddings, bundled OCR, CSL rendering and Zotero write-back are not included in this first integration.
