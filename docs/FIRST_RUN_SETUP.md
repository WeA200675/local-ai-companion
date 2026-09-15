# First-run local readiness setup

The recommended Windows launcher now opens a one-time local setup dialog before the desktop app starts.

## What the setup checks

The wizard is intentionally local-only. It:

1. checks the configured Ollama endpoint;
2. loads the models already installed in Ollama;
3. lets the user select the local model used by the companion;
4. performs a real `/api/chat` mini-inference instead of trusting model inventory alone;
5. shows actionable backend errors when inference fails;
6. optionally runs the existing non-graphic Adult-/Kink model compatibility probe;
7. stores the selected model/endpoint only when the user completes setup successfully.

The wizard does **not** install Ollama, download models, contact a cloud service, upload conversation history, or send Persona/Memory content anywhere.

## Windows flow

Run the normal launcher:

```powershell
.\run_windows.cmd
```

`scripts/run_windows.ps1` first executes:

```powershell
.\.venv\Scripts\python.exe -m app.first_run
```

After successful setup, completion is stored as a dedicated local `first_run_setup` app-state record. It is deliberately separate from the normal runtime settings, so later edits to model/media settings cannot accidentally make the first-run wizard reappear.

To reopen the setup manually:

```powershell
.\.venv\Scripts\python.exe -m app.first_run --force
```

Choosing **Später** closes the dialog without changing the completion state, so it appears again on the next normal Windows launch. Choosing **Nicht mehr automatisch anzeigen** leaves the previous backend settings unchanged but marks first-run setup as completed.

## Media setup

ComfyUI remains optional and does not block the text companion. The first-run dialog deliberately tests the text/model path with media disabled so a broken optional workflow cannot hide an Ollama problem.

Local media can then be configured separately with:

```powershell
.\media_setup_windows.cmd
```

That media assistant performs workflow inspection and a real local smoke render before saving the generated workflow profile.

## Adult-/Kink compatibility

Once the real model inference succeeds, the first-run wizard enables the existing Adult-/Kink compatibility check. Its prompts are local, non-graphic adult capability probes. The result is stored locally and remains a heuristic: it can identify obvious refusal or backend problems but cannot guarantee identical behavior in every later conversation.
