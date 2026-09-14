# Local AI Companion

Private-first local desktop companion with configurable persona, learning state, non-destructive snapshots, persistent chat history, and a model-agnostic local media pipeline.

## Current v0.1.0-alpha status

Implemented on the bootstrap branch:

- PySide6 desktop UI with Chat and Persona Lab tabs
- Local Ollama-compatible model adapter
- Persistent SQLite chat history
- Persona traits with user-controlled values and locks
- User-configured preference tags
- Immutable persona snapshots
- Non-destructive restore: every restore first creates a `pre_restore` snapshot
- Optional ComfyUI-compatible local image/GIF/video generation backend
- Autonomous media planning after assistant replies
- Inline preview for generated images, GIFs, and short videos
- Automated tests for model requests, persistence, snapshots, and media workflow injection

## Privacy model

Chats, preferences, generated media, photos, model files, logs, and local databases should stay on the local machine and must not be committed to the repository.

The default database is written to `data/companion.sqlite3`. Generated media defaults to `data/generated_media/`. The `data/` directory is gitignored.

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

Start your local Ollama service and make sure the configured model is available. The current default is `qwen2.5:7b`.

Run the app:

```bash
python -m app.main
```

Tests:

```bash
pytest
```

## Local model configuration

The model and endpoint can be changed without editing source code.

Windows PowerShell:

```powershell
$env:LOCAL_AI_MODEL="your-model"
$env:LOCAL_AI_URL="http://127.0.0.1:11434"
python -m app.main
```

macOS/Linux:

```bash
LOCAL_AI_MODEL="your-model" LOCAL_AI_URL="http://127.0.0.1:11434" python -m app.main
```

## Local visual generation with ComfyUI

Media generation is optional. Without a workflow configured, the app behaves as a normal local chat companion.

1. Start ComfyUI locally.
2. Build and test a workflow in ComfyUI.
3. Export the workflow in **API format** to a local JSON file.
4. Configure the node ids containing the positive prompt, negative prompt, and seed.
5. Point the app at that local workflow.

Example for Windows PowerShell:

```powershell
$env:LOCAL_MEDIA_URL="http://127.0.0.1:8188"
$env:LOCAL_MEDIA_WORKFLOW="C:\AI\workflows\companion-api.json"
$env:LOCAL_MEDIA_POSITIVE_NODE="6"
$env:LOCAL_MEDIA_NEGATIVE_NODE="7"
$env:LOCAL_MEDIA_SEED_NODE="3"
python -m app.main
```

Example for macOS/Linux:

```bash
LOCAL_MEDIA_URL="http://127.0.0.1:8188" \
LOCAL_MEDIA_WORKFLOW="$HOME/AI/workflows/companion-api.json" \
LOCAL_MEDIA_POSITIVE_NODE="6" \
LOCAL_MEDIA_NEGATIVE_NODE="7" \
LOCAL_MEDIA_SEED_NODE="3" \
python -m app.main
```

After each assistant reply, the local language model can decide whether a visual adds something to the scene. If so, it produces a structured media intent, the visual prompt compiler converts that intent into backend-neutral prompts, and the configured ComfyUI workflow generates the file locally. The result is shown inline in the desktop UI.

The workflow itself remains outside the repository so model files, custom nodes, checkpoint names, and personal visual preferences can stay fully local.

## Persona and snapshots

The Persona Lab lets you change personality traits, lock individual traits, edit preference tags, create manual snapshots, and restore older states.

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
├── ai/       persona state, prompt compilation, local model adapter
├── memory/   SQLite chat/state storage and immutable snapshots
├── media/    media intent, prompt compiler, ComfyUI adapter, generation service
└── ui/       Chat, Persona Lab, and inline media preview
```

## Versioning

Application releases use Semantic Versioning. Persona state is versioned independently through immutable snapshots. Model choice and media workflows are local configuration rather than application version state.
