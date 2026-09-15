# Workflow Profile & Routing Manager

`workflow_profiles_windows.cmd` opens a local GUI for managing which already-configured ComfyUI workflow should be preferred for different visual jobs.

The manager exposes:

- enable/disable per profile
- deterministic base priority from `-100` to `100`
- render quality (`draft`, `balanced`, `high`)
- explicit preference for recurring Character scenes
- routing tags for portrait, full body, detail/material, environment, Character continuity and motion
- technical workflow capability summary
- checkpoint provenance and the existing explicit checkpoint-license confirmation flag
- learned per-focus routing scores derived only from local explicit media feedback

## Non-destructive catalog management

The manager never edits the currently configured source catalog in place. When a change is saved, the current catalog is copied into the app-owned file:

`workflow_profiles.managed.json`

next to the configured generated-media directory, and the local runtime settings are updated to point at that managed copy. Relative workflow paths are resolved before the copy is written, so the managed file remains valid independently of the original catalog location.

This means imported catalogs, generated setup catalogs and user-authored JSON files remain unchanged and can be returned to manually if desired.

## Routing behavior

The base priority and explicit routing tags combine with the existing local workflow selector. User feedback remains a bounded soft signal and cannot make a disabled, missing or technically invalid workflow runnable.

A checkpoint filename is provenance only. The manager never derives a license, adult-content capability or visual quality claim from it. The displayed license-confirmation state is only the explicit local user assertion already stored by the media setup flow.

## Windows

Run:

```powershell
.\workflow_profiles_windows.cmd
```

The launcher self-heals a missing project `.venv` using the existing Windows setup path. It does not install Ollama, ComfyUI, checkpoints, LoRAs, custom nodes or models.

No cloud service, telemetry, proprietary SDK or new dependency is introduced.
