[CmdletBinding()]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python Launcher 'py' was not found. Install Python 3.12 and reopen PowerShell." }
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required for the first reproducible Windows build." }
$Venv = Join-Path $Root ".venv-desktop"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) { & py -3.12 -m venv $Venv; if ($LASTEXITCODE -ne 0) { throw "Could not create the desktop virtual environment." } }
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $Python -m pip install -r requirements-desktop.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
if (-not $SkipTests) { & $Python -m pytest -q; if ($LASTEXITCODE -ne 0) { throw "Tests failed; refusing to build an unverified package." } }
& $Python -m PyInstaller --noconfirm --clean ScholarFlowDesktop.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
$ExePath = Join-Path $Root "dist\ScholarFlow\ScholarFlow.exe"
if (-not (Test-Path $ExePath)) { throw "Build ended without expected executable: $ExePath" }
& $ExePath --smoke-test
if ($LASTEXITCODE -ne 0) { throw "Packaged ScholarFlow smoke test failed. See the SMOKE FAIL lines above; refusing to treat this build as verified." }
Write-Host "Build folder: $(Join-Path $Root 'dist\ScholarFlow')"
Write-Host "Executable:   $ExePath"
Write-Host "Next test: launch it on this Windows PC and verify editor, Research Library, file indexing and clean shutdown."
Write-Host "Microsoft Edge WebView2 Runtime is required. This is an onedir build, not an MSI installer."
