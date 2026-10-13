[CmdletBinding()]
param([switch]$RunSetup)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutDir = Join-Path $Root ".rea-local"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
function Save-Text($Path, $Text) { Set-Content -LiteralPath $Path -Value $Text -Encoding utf8 }
$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm -ErrorAction SilentlyContinue
$NodeText = if ($Node) { (& node -v 2>&1 | Out-String).Trim() } else { "node unavailable" }
$NpmText = if ($Npm) { (& npm -v 2>&1 | Out-String).Trim() } else { "npm unavailable" }
Save-Text (Join-Path $OutDir "node-version.txt") $NodeText
Save-Text (Join-Path $OutDir "npm-version.txt") $NpmText
$NodeSupported = $false
if ($NodeText -match '^v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)') {
    $major = [int]$Matches.major; $minor = [int]$Matches.minor; $patch = [int]$Matches.patch
    $NodeSupported = (($major -eq 22 -and ($minor -gt 19 -or ($minor -eq 19 -and $patch -ge 0))) -or ($major -eq 24 -and ($minor -gt 11 -or ($minor -eq 11 -and $patch -ge 0))) -or ($major -ge 26))
}
$MetadataPath = Join-Path $OutDir "rea-package-metadata.json"
if ($Node -and $Npm) {
    $metadata = (& npm view rea-agents@6.4.0 version license repository.url engines --json 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0) { Save-Text $MetadataPath $metadata }
    else { Save-Text $MetadataPath (@{ status = "registry_unavailable"; detail = $metadata } | ConvertTo-Json -Depth 4) }
} else {
    Save-Text $MetadataPath (@{ status = "node_or_npm_unavailable" } | ConvertTo-Json -Depth 3)
}
$Plan = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    mode = if ($RunSetup) { "interactive_setup_requested" } else { "readiness_only" }
    node_version = $NodeText
    npm_version = $NpmText
    node_version_supported = $NodeSupported
    package_version_requested = "6.4.0"
    setup_executed = $false
    agent_configuration_changed_by_this_script = $false
    competitor_observations_performed = $false
    requires_user_review = $true
    note = "The previous audit did not detect Arena as a supported client. Choose only a client listed by the current official REA setup."
}
Save-Text (Join-Path $OutDir "rea-setup-plan.json") ($Plan | ConvertTo-Json -Depth 4)
Write-Host "REA readiness output: $OutDir"
Write-Host "Node: $NodeText"
Write-Host "npm:  $NpmText"
Write-Host "Supported Node version: $NodeSupported"
Write-Host "Default mode does not change agent configuration or observe Grammarly/QuillBot."
if ($RunSetup) {
    if (-not $NodeSupported -or -not $Npm) { throw "Install a supported Node.js release and npm before requesting setup." }
    Write-Host "The official interactive setup may propose agent configuration changes."
    $confirmation = Read-Host "Type RUN_SETUP to invoke REA setup"
    if ($confirmation -cne "RUN_SETUP") { Write-Host "Setup cancelled."; exit 0 }
    & npx --yes rea-agents@6.4.0 setup
    if ($LASTEXITCODE -ne 0) { throw "REA setup did not complete successfully. Inspect terminal output; do not assume connection is configured." }
    Write-Host "Setup command completed. Restart the selected agent and run its documented doctor command."
} else {
    Write-Host "Dry run only. To request interactive setup later: .\scripts\rea-readiness.ps1 -RunSetup"
}
