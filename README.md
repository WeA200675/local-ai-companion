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
- Media planning interface for future local image/GIF/video generation backends
- Automated tests for model requests, persistence, and snapshot/restore behavior

## Privacy model

Chats, preferences, generated media, photos, model files, logs, and local databases should stay on the local machine and must not be committed to the repository.

The default database is written to `data/companion.sqlite3`. The `data/` directory is gitignored.

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
├── media/    model-agnostic visual/media planning
└── ui/       Chat and Persona Lab desktop interface
```

## Versioning

Application releases use Semantic Versioning. Persona state is versioned independently through immutable snapshots. Model choice is configuration rather than application version state.
