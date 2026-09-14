# Local AI Companion

Private-first local desktop companion with configurable persona, learning state, non-destructive snapshots, and a model-agnostic local media pipeline.

## v0.1.0-alpha goals

- Local desktop UI with PySide6
- Persona traits with user-controlled bounds and locks
- SQLite-backed persona history
- Non-destructive restore: every restore first creates a `pre_restore` snapshot
- Local-model integration layer
- Media planning interface for local image/GIF/video generation backends
- Tests for snapshot/restore behavior

## Privacy model

Chats, preferences, generated media, photos, model files, logs, and local databases should stay on the local machine and must not be committed to the repository.

## Quick start

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

Run:

```bash
python -m app.main
```

Tests:

```bash
pytest
```

## Architecture

```text
app/
├── ai/       persona state and model orchestration
├── memory/   SQLite storage and immutable snapshots
├── media/    model-agnostic visual/media planning
└── ui/       desktop interface
```

## Versioning

Application releases use Semantic Versioning. Persona state is versioned independently through immutable snapshots. A restore never destroys the current state: a `pre_restore` snapshot is written first, then the chosen historical snapshot is restored as a new active revision.
