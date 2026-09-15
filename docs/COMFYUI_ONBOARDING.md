# Guided ComfyUI Onboarding

The Local AI Companion can use ComfyUI as an optional local image/GIF/video backend. The app does not silently install ComfyUI, download checkpoints, or modify a user's ComfyUI installation.

## Media Setup tab

Inside **Einstellungen → Medien-Setup** the app shows the currently configured ComfyUI endpoint and workflow state. The intended setup flow is:

1. Run an open-source ComfyUI installation locally.
2. Build and verify a workflow in ComfyUI.
3. Export the working graph in ComfyUI API JSON format.
4. Select that JSON file as the app's **Standard-Workflow**.
5. Use **Workflow prüfen & Nodes erkennen**.
6. Review the detected positive prompt, negative prompt and seed nodes.
7. Use **Erkannte Nodes übernehmen** and then **Einstellungen speichern**.
8. Run **ComfyUI/Workflow testen**.

The helper only changes the three local node-id fields after an explicit user action. It never rewrites the workflow JSON itself.

## Automatic node detection

The inspector follows a sampler's graph connections instead of assuming the historical default node ids `6`, `7`, and `3`.

It searches for a KSampler-like node with:

- a `positive` connection,
- a `negative` connection,
- and either a `seed` or `noise_seed` input.

The connected nodes are checked for a `text` or `prompt` input. If more than one sampler is present, the app picks the best matching candidate and displays a warning so the user can verify it before applying anything.

If the graph is valid JSON but cannot be determined unambiguously, the app leaves the current configuration untouched and shows candidate information instead of guessing silently.

## Workflow profile catalogs

The automatic helper is aimed at the single **Standard-Workflow**. Workflow profile catalogs already contain their own prompt/seed node mapping per profile and remain authoritative when configured.

## Licensing

ComfyUI is part of the project's registered open-source local stack. User-added checkpoints, LoRAs, custom nodes and workflow dependencies keep their own licenses. The onboarding helper does not claim that an arbitrary user-installed model or custom node is open source merely because it runs inside ComfyUI.
