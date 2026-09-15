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

& $venvPython .\scripts\media_setup_wizard.py
