param(
    [switch]$NoRun,
    [switch]$SkipDevTools
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Find-PythonLauncher {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) {
        return $null
    }
    foreach ($version in @("3.12", "3.11")) {
        & py "-$version" -c "import sys; print(sys.version_info[:2])" *> $null
        if ($LASTEXITCODE -eq 0) {
            return $version
        }
    }
    return $null
}

Write-Step "Pruefe Python"
$pythonVersion = Find-PythonLauncher
if (-not $pythonVersion) {
    Write-Host "Python 3.11 oder 3.12 wurde ueber den Windows-Python-Launcher nicht gefunden." -ForegroundColor Yellow
    Write-Host "Installiere Python 3.12 (oder 3.11) und starte dieses Skript danach erneut."
    exit 2
}
Write-Host "Verwende Python $pythonVersion"

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Step "Erstelle lokale virtuelle Umgebung (.venv)"
    & py "-$pythonVersion" -m venv .venv
}

Write-Step "Aktualisiere pip"
& $venvPython -m pip install --upgrade pip

Write-Step "Installiere Local AI Companion"
if ($SkipDevTools) {
    & $venvPython -m pip install -e "."
}
else {
    & $venvPython -m pip install -e ".[dev]"
}

Write-Step "Pruefe Open-Source-Komponenten"
& $venvPython -m app.oss_audit
if ($LASTEXITCODE -ne 0) {
    throw "OSS-Audit fehlgeschlagen."
}

Write-Step "Pruefe Ollama"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "Ollama wurde nicht gefunden. Die Desktop-App kann trotzdem starten, Chat funktioniert aber erst nach lokaler Ollama-Installation." -ForegroundColor Yellow
}
else {
    & ollama --version
    Write-Host "Installierte lokale Modelle:"
    & ollama list
    $modelList = (& ollama list | Out-String)
    if ($modelList -notmatch "qwen2\.5:7b") {
        Write-Host "Hinweis: Das Standardmodell qwen2.5:7b ist noch nicht installiert." -ForegroundColor Yellow
        Write-Host "Die App laedt Modelle nicht automatisch. Bei Bedarf manuell: ollama pull qwen2.5:7b"
    }
}

Write-Host "`nSetup abgeschlossen." -ForegroundColor Green
Write-Host "Start spaeter mit: .\run_windows.cmd"

if (-not $NoRun) {
    Write-Step "Starte Local AI Companion"
    & $venvPython -m app.main
}
