$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$setupScript = Join-Path $repoRoot "scripts\setup_windows.ps1"

Set-Location $repoRoot

if (-not (Test-Path $venvPython)) {
    Write-Host "Die lokale .venv fehlt. Ich richte sie jetzt automatisch ein." -ForegroundColor Yellow
    Write-Host "Es werden nur Python-Umgebung und Projektabhaengigkeiten eingerichtet; Modelle werden nicht automatisch geladen."
    & $setupScript -NoRun
    if (-not (Test-Path $venvPython)) {
        throw "Die lokale .venv konnte nicht eingerichtet werden."
    }
    Write-Host "Lokale Python-Umgebung ist bereit." -ForegroundColor Green
}

# On the recommended Windows launcher path, the setup module is effectively a
# no-op after it has been completed. On first run it opens the local readiness
# wizard before the main desktop process is started.
& $venvPython -m app.first_run
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

# The runtime launcher applies the explicitly configured, locally tested strict
# Open-Source model fallback chain before constructing the desktop window.
& $venvPython -m app.runtime_launcher
