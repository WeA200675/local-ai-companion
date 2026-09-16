@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lokale Python-Umgebung fehlt. Starte zuerst run_windows.cmd oder scripts\setup_windows.ps1.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m app.voice_studio
endlocal
