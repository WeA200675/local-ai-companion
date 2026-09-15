# Local media suitability lab

The suitability lab compares one configured local ComfyUI image workflow across four practical visual jobs:

- portrait
- full body
- material/detail
- environment

The suite renders small draft images with deterministic seeds and the existing hardware-aware render calculator. The prompts are non-graphic and keep any depicted person clearly adult.

The app does **not** use a vision classifier and does not pretend to infer visual quality automatically. After the renders finish, the user explicitly marks each result as good or bad for that image type. Those ratings are stored through the existing media-feedback path and therefore feed the adaptive workflow router introduced in `MEDIA_WORKFLOW_ROUTING.md`.

Every probe result is also written to normal media history with the workflow profile, checkpoint provenance when known, focus tag, render plan, applied ComfyUI parameters and probe id. The Media History inspector shows this routing provenance, including the learned workflow score that existed before a normal render.

## In the desktop app

Open **Medien → Historie & Render** and choose **Medien-Eignungslabor**. The lab reuses the desktop app's local StateStore, so new probe media and good/bad ratings appear in Media History immediately and affect later workflow routing without restarting the database layer.

## Windows standalone entry point

After normal setup the same lab can still be opened directly:

```powershell
.\media_suitability_windows.cmd
```

The launcher is self-healing in the same way as the other Windows entry points: if `.venv` is missing it invokes the normal local Python bootstrap first. It does not install or download checkpoints, models, LoRAs or custom nodes.

No cloud service, telemetry, proprietary SDK or new dependency is used.
