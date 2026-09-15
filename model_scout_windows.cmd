@echo off
setlocal
set ROOT=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\model_scout_windows.ps1" %*
if errorlevel 1 pause
