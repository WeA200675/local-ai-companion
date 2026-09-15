@echo off
setlocal
set ROOT=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\media_suitability_windows.ps1" %*
if errorlevel 1 pause
