# Quality and test protocol

## Repository checks
Run from the repository root after installing pinned dependencies:

```powershell
python -m pip install -r requirements-dev.txt -r requirements-research.txt
python -m pytest -q
python -m compileall -q .
python -m tools.repository_check
python -m flake8 --select=E9,F63,F7,F82 .
git diff --check
```

Build the Windows desktop package with:

```powershell
.\scripts\build_windows_desktop.ps1
```

The script reruns tests before PyInstaller unless `-SkipTests` is deliberately provided.

## Manual acceptance
1. Start FastAPI on `127.0.0.1`.
2. Confirm `/health`, `/`, and `/library` load.
3. Add a synthetic catalogue record, search it, import a synthetic CSL JSON record and index a synthetic TXT file.
4. Confirm a missing passage returns an insufficient-evidence warning, not a claimed research gap.
5. Simulate provider failures using mocked tests; live calls must fail visibly.
6. On Windows, launch and close the native desktop window and ensure its local server exits.
7. Test a researcher-approved Zotero collection and re-import duplicate checks.
8. Verify REA setup/doctor only for a supported local client; record competitor observations separately.

A repository CI pass cannot verify the user's Windows installation, active Zotero profile or local agent setup.
