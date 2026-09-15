# Windows setup

The project remains a local, open-source-first desktop application. The Windows helper scripts only orchestrate software already chosen by the user; they do not install Ollama, download models, enable cloud services, or change repository visibility/licensing.

## First setup

The preferred Windows entry points now self-heal a missing project environment. If `.venv` is absent, `run_windows.cmd`, `model_scout_windows.cmd` and `media_setup_windows.cmd` automatically invoke the repository setup in `-NoRun` mode, create `.venv`, install the project and run the OSS audit before continuing with the requested tool.

No Ollama model is downloaded by that bootstrap. A model download still requires an explicit action in the model catalog or a manual `ollama pull` command.

Manual setup remains available from PowerShell in the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

The setup script:

1. looks for Python 3.12 or 3.11 through the Windows `py` launcher,
2. creates `.venv` if needed,
3. installs the project (including dev tools unless `-SkipDevTools` is supplied),
4. runs the OSS registry audit,
5. reports whether the local `ollama` command exists and lists installed models when available,
6. starts the desktop app unless `-NoRun` is supplied.

It never runs `ollama pull` automatically. If `qwen2.5:7b` is absent, it prints the manual command and leaves the decision to the user.

## Normal launch

Double-click `run_windows.cmd` or run it from a terminal:

```powershell
.\run_windows.cmd
```

The launcher uses `.venv\Scripts\python.exe`. If the environment is missing, it creates it first and then continues into the first-run/readiness flow and desktop app.

The same behavior applies to the local model catalog:

```powershell
.\model_scout_windows.cmd
```

and the media setup helper:

```powershell
.\media_setup_windows.cmd
```

This avoids the previous dead-end message telling the user to run another setup command first.

## Useful options

```powershell
# Setup only; do not start the GUI afterward
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -NoRun

# Install runtime dependencies only
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -SkipDevTools
```

The PowerShell launcher messages deliberately avoid non-ASCII umlauts so Windows PowerShell 5.1 cannot render UTF-8 source text as strings such as `FÃ¼hre` on older console/code-page combinations.

Ollama and ComfyUI remain separate local applications. Text chat only needs the configured Ollama-compatible endpoint. ComfyUI is optional and only required when local media generation is enabled.
