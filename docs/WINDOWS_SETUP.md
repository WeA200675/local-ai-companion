# Windows setup

The project remains a local, open-source-first desktop application. The Windows helper scripts only orchestrate software already chosen by the user; they do not install Ollama, download models, enable cloud services, or change repository visibility/licensing.

## First setup

From PowerShell in the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

The script:

1. looks for Python 3.12 or 3.11 through the Windows `py` launcher,
2. creates `.venv` if needed,
3. installs the project (including dev tools unless `-SkipDevTools` is supplied),
4. runs the OSS registry audit,
5. reports whether the local `ollama` command exists and lists installed models when available,
6. starts the desktop app unless `-NoRun` is supplied.

It never runs `ollama pull` automatically. If `qwen2.5:7b` is absent, it prints the manual command and leaves the decision to the user.

## Normal launch

After setup, double-click `run_windows.cmd` or run it from a terminal:

```powershell
.\run_windows.cmd
```

The launcher always uses `.venv\Scripts\python.exe`, so PowerShell activation and execution-policy issues no longer affect normal startup.

## Useful options

```powershell
# Setup only; do not start the GUI afterward
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -NoRun

# Install runtime dependencies only
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -SkipDevTools
```

Ollama and ComfyUI remain separate local applications. Text chat only needs the configured Ollama-compatible endpoint. ComfyUI is optional and only required when local media generation is enabled.
