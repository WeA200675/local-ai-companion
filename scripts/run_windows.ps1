$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Die lokale .venv fehlt." -ForegroundColor Yellow
    Write-Host "Führe zuerst aus: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1"
    exit 2
}

Set-Location $repoRoot
& $venvPython -m app.main
