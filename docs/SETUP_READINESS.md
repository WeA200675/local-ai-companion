# Setup & Readiness

The desktop app keeps configuration separate from diagnosis. The **Einstellungen** area now contains two inner tabs:

- **Konfiguration**: model, Ollama endpoint, chat/runtime options, ComfyUI/media settings, continuity and memory settings.
- **Setup & Diagnose**: a compact readiness summary, the Adult-/Kink model compatibility report, and the raw local connection/file checks.

The configuration page is scrollable so smaller desktop windows do not need to fit every advanced option at once.

## Readiness model

The readiness summary combines existing local-only checks. It does not contact a cloud service and does not install or modify software automatically.

It reports four independent areas:

1. **Local language model** — whether the configured Ollama-compatible endpoint reports the selected model.
2. **Adult-/Kink model compatibility** — the latest locally stored compatibility probe for the selected model and endpoint.
3. **Local media output** — whether the configured output directory is writable.
4. **Local image/motion pipeline** — whether ComfyUI and a usable API workflow/profile catalog are ready when media generation is enabled.

The text/Adult companion and the media pipeline are deliberately shown separately. A missing ComfyUI installation must not make a working text companion look broken.

## Guided next steps

Every non-ready item exposes a concrete next action. Typical media setup guidance is:

- start ComfyUI locally and verify the configured loopback endpoint (default `http://127.0.0.1:8188`);
- configure either a ComfyUI API workflow JSON or a workflow profile catalog;
- keep the output directory locally writable;
- rerun **Lokale Verbindungen testen**.

If the language model is installed but the Adult-/Kink report is missing, the readiness view points directly to **Adult-/Kink-Modelltest**. If the report is blocked or unavailable, the view distinguishes content incompatibility from technical model/backend failure.

## Privacy and open-source rule

Readiness checks use only configured local endpoints and local files. Results remain local in the existing SQLite state. No telemetry, hosted setup service, proprietary SDK, automatic model download, or silent software installation is introduced.

ComfyUI remains optional for text-only use. Any user-added checkpoint, LoRA, custom node, or workflow retains its own license and must be reviewed before it is treated as part of an open-source-only deployment.
