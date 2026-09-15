# Automatic local media setup

The automatic media setup helper reduces the manual ComfyUI wiring needed for Local AI Companion while staying fully local.

## What it does

Given an exported ComfyUI workflow in **API JSON** format, the helper:

1. inspects the graph locally;
2. traces the positive and negative prompt paths back from a sampler;
3. detects the sampler seed input;
4. infers common output kinds such as image, GIF, or video when the workflow exposes recognizable output nodes;
5. records the render controls that can safely be changed (`width`, `height`, `steps`, `cfg`, `denoise`, `frames`, `fps`);
6. creates or merges an app-owned workflow profile catalog;
7. optionally runs a real local ComfyUI smoke render and downloads the result into the configured local output folder.

The helper does not install ComfyUI, models, LoRAs, custom nodes, or proprietary SDKs. It does not contact a cloud service.

## One-command setup

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\setup_media.py "C:\path\to\workflow_api.json"
```

Optional arguments:

```text
--comfy-url http://127.0.0.1:8188
--output-dir data/generated_media
--catalog data/workflow_profiles.generated.json
--no-render
```

Without `--catalog`, the generated catalog is stored next to the configured app media output folder. Existing generated catalogs are merged by profile id instead of being silently replaced.

The smoke test uses a deliberately simple, non-personal studio still-life prompt. Its purpose is only to prove that the workflow can be queued, executed, and downloaded through the configured local ComfyUI endpoint.

## Result

A successful run prints the detected node mapping, media kinds, render controls, generated catalog path, local hardware tier, and the path of the downloaded smoke-test result.

The resulting catalog can be used through either the app setting `Workflow-Profile` or the environment variable:

```text
LOCAL_MEDIA_PROFILE_CATALOG=data/workflow_profiles.generated.json
```

Set `LOCAL_MEDIA_ENABLED=1` when using environment configuration.

## Limits

Automatic inspection is intentionally conservative. Very unusual custom nodes can hide prompt, seed, output, or render controls in ways that cannot be inferred reliably from static JSON alone. In that case the helper reports the ambiguity rather than guessing. The existing Media Capability Matrix remains the authoritative runtime check for profile usability.

The generated profile only covers what can be established from the workflow itself. Reference-image continuity still requires a workflow with a known image-input mapping. User-installed models, LoRAs, custom nodes, and workflows remain the user's responsibility to license and configure appropriately.
