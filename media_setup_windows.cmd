@echo off
setlocal
set ROOT=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\media_setup_wizard.ps1"
if errorlevel 1 pause
