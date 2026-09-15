$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Die lokale .venv fehlt." -ForegroundColor Yellow
    Write-Host "Führe zuerst aus: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1"
    exit 2
}

Set-Location $repoRoot

# On the recommended Windows launcher path, the setup module is effectively a
# no-op after it has been completed. On first run it opens the local readiness
# wizard before the main desktop process is started.
& $venvPython -m app.first_run
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $venvPython -m app.main
