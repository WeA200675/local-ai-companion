# Local AI Companion

Private-first local desktop companion with configurable persona, controlled learning, non-destructive snapshots, persistent chat history, and a local media pipeline.

## Current v0.1.0-alpha status

Implemented:

- PySide6 desktop UI with Chat, Persona Lab, Media History, and Settings tabs
- Local Ollama-compatible model adapter
- Persistent SQLite chat history and runtime settings
- Persona traits with user-controlled current value, min/max bounds, learning rate, and locks
- User-configured preference tags
- Feedback-driven persona learning with bounded trait updates
- Automatic `pre_learning` and `learning` snapshots around feedback-driven learning
- Persistent learning audit trail in the Persona Lab
- Immutable persona snapshots
- Non-destructive restore: every restore first creates a `pre_restore` snapshot
- Optional ComfyUI-compatible local image/GIF/video generation backend
- Autonomous media planning after assistant replies
- Character/seed continuity memory for recurring generated companion visuals
- Inline preview for generated images, GIFs, and short videos
- Persistent local media history with per-image positive/negative feedback
- In-app configuration for model endpoint, ComfyUI workflow, node ids, output path, continuity, and history limits
- Automated tests for model requests, persistence, learning, snapshots, media workflow injection, settings, continuity, and media feedback

## Privacy model

Chats, preferences, generated media, photos, model files, logs, runtime settings, and local databases should stay on the local machine and must not be committed to the repository.

The default database is written to `data/companion.sqlite3`. Generated media defaults to `data/generated_media/`. The `data/` directory is gitignored. Ollama and ComfyUI endpoints default to loopback addresses, so the reference configuration does not require a cloud model service.

## Quick start

Create a virtual environment:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -e ".[dev]"
```

Start your local Ollama service and make sure the configured model is available. The current first-run default is `qwen2.5:7b`.

Run the app:

```bash
python -m app.main
```

Tests:

```bash
pytest
```

## In-app settings

The **Einstellungen** tab is the preferred way to configure the app after first launch. It stores settings locally in SQLite and can reconfigure the local backends without editing source code.

Configurable values include:

- local language-model name and endpoint
- ComfyUI endpoint and API-format workflow path
- positive-prompt, negative-prompt, and seed node ids
- local media output directory
- media generation on/off
- visual character continuity on/off and continuity key
- automatic learning snapshots
- media-history size

Environment variables remain available as first-run defaults, for example:

```powershell
$env:LOCAL_AI_MODEL="your-model"
$env:LOCAL_AI_URL="http://127.0.0.1:11434"
$env:LOCAL_MEDIA_WORKFLOW="C:\AI\workflows\companion-api.json"
python -m app.main
```

## Controlled persona learning

Each assistant response can be rated with **Mehr davon** or **Weniger davon**. A local learning analyzer proposes bounded signals for the seven persona traits. The application then applies only the changes allowed by each trait's learning rate, lock state, and user-defined min/max bounds.

The Persona Lab exposes all of those controls. Learning stays outside the underlying model weights, so changes remain visible, auditable, and reversible.

When automatic learning snapshots are enabled, every feedback-driven learning step creates this history:

```text
current persona
    ↓
pre_learning snapshot
    ↓
apply bounded learning update
    ↓
learning snapshot
```

That makes even small behavior changes easy to inspect and roll back later.

## Local visual generation with ComfyUI

Media generation is optional. Without an enabled workflow, the app behaves as a normal local chat companion.

1. Start ComfyUI locally.
2. Build and test a workflow in ComfyUI.
3. Export the workflow in **API format** to a local JSON file.
4. Select that file in the app's Settings tab.
5. Configure the node ids containing the positive prompt, negative prompt, and seed.
6. Enable local media generation.

After each assistant reply, the local language model can decide whether a visual adds something to the scene. If so, it produces a structured media intent, the visual prompt compiler converts that intent into backend-neutral prompts, and the configured ComfyUI workflow generates the file locally. The result is shown inline in the desktop UI and added to the local Media History tab.

The media planner and prompt compiler keep depicted people clearly adult and the reference pipeline is designed for provocative/fetish-inspired but non-graphic visual output.

## Character continuity

When a generated scene depicts the recurring companion character, the planner can attach a continuity key. The app stores a local character profile for that key with a stable seed and continuity prompt. Future generations reuse those values so the character has a better chance of remaining visually recognizable across sessions.

This is intentionally backend-neutral. A later version can extend the same character profile with reference-image embeddings, LoRAs, IP-Adapter/ControlNet state, or other local identity-preservation methods without changing the chat/persona layer.

The Media History tab records the generated file, seed, intent, continuity key, and user feedback. Positive/negative image feedback is also associated with the corresponding continuity profile for future media-learning work.

## Persona and snapshots

The Persona Lab lets you change personality traits, min/max limits, per-trait learning rates, lock individual traits, edit preference tags, inspect learning events, create manual snapshots, and restore older states.

A restore is intentionally non-destructive:

```text
current state
    ↓
pre_restore snapshot
    ↓
load selected historical state
    ↓
write restored state as a new revision
```

This means a rollback can itself be undone later.

## Architecture

```text
app/
├── ai/       persona state, prompt compilation, local model adapter, learning analyzer
├── memory/   SQLite chat/state storage, settings, media history, learning audit, snapshots
├── media/    media intent, visual prompting, continuity profiles, ComfyUI adapter/service
├── ui/       Chat, Persona Lab, Media History, Settings, inline media preview
└── settings.py
```

## Versioning

Application releases use Semantic Versioning. Persona state is versioned independently through immutable snapshots. Model choice, media workflows, continuity profiles, media feedback, and generated files are local runtime state rather than repository content.
