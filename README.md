# Local AI Companion

Private-first local desktop companion with configurable persona, controlled learning, reversible long-term memory, non-destructive snapshots, persistent chat history, and a local media pipeline.

## Current v0.2.0-alpha status

Implemented:

- PySide6 desktop UI with Chat, Persona Lab, Memory, Media History, and Settings tabs
- Local Ollama-compatible model adapter
- Persistent SQLite chat history and runtime settings
- Persona traits with user-controlled current value, min/max bounds, learning rate, and locks
- Feedback-driven persona learning with `pre_learning` / `learning` snapshots and an audit trail
- Adaptive local long-term interaction memory with confidence filtering, deduplication, review, and reversible enable/disable controls
- Immutable persona snapshots with non-destructive restore (`pre_restore` is always written first)
- Optional ComfyUI-compatible local image/GIF/video generation backend
- Autonomous media planning after assistant replies
- Character/seed continuity memory for recurring generated companion visuals
- Persistent local media history with per-image feedback and reversible visual-preference learning
- In-app configuration for local models, media workflow, continuity, learning snapshots, adaptive memory, and history limits
- Local diagnostics for Ollama, model availability, ComfyUI, workflow node ids, and output paths
- Automated tests across model requests, persistence, learning, adaptive memory, snapshots, media, settings, continuity, diagnostics, and feedback

## Privacy model

Chats, adaptive memory, preferences, generated media, model files, logs, runtime settings, and local databases stay on the local machine by default and must not be committed to the repository.

The default database is `data/companion.sqlite3`; generated media defaults to `data/generated_media/`. The `data/` directory is gitignored. Ollama and ComfyUI default to loopback addresses.

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

Install and run:

```bash
pip install -e ".[dev]"
python -m app.main
```

Tests:

```bash
pytest
```

## In-app settings and diagnostics

The **Einstellungen** tab stores local runtime configuration in SQLite. It controls the language-model endpoint, ComfyUI endpoint/workflow and node ids, output path, media generation, character continuity, automatic learning snapshots, adaptive-memory enablement and analysis interval, and media-history size.

The **Lokale Verbindungen testen** button performs local-only preflight checks for the configured Ollama endpoint/model, ComfyUI workflow/node ids, ComfyUI endpoint, and output directory.

Environment variables remain available as first-run defaults, including `LOCAL_AI_MODEL`, `LOCAL_AI_URL`, `LOCAL_MEDIA_WORKFLOW`, `LOCAL_ADAPTIVE_MEMORY`, and `LOCAL_ADAPTIVE_MEMORY_INTERVAL`.

## Controlled persona learning

Each assistant response can be rated with **Mehr davon** or **Weniger davon**. A local analyzer proposes bounded signals for the seven persona traits. Application-side min/max bounds, per-trait learning rates, and locks remain authoritative.

When automatic learning snapshots are enabled:

```text
current persona
    ↓
pre_learning snapshot
    ↓
apply bounded learning update
    ↓
learning snapshot
```

Learning remains visible, auditable, and reversible rather than silently modifying model weights.

## Adaptive long-term memory

Adaptive memory is separate from persona traits and chat history. At a configurable interval, the local model can extract a small number of high-confidence observations that are likely to remain useful across conversations, such as communication style, explicit interaction preferences, boundaries, or recurring themes.

The learner is instructed not to infer or store sensitive personal facts such as identity, exact location, health, politics/religion, finances, passwords/account data, legal/criminal history, or transient scene details. Low-confidence proposals are discarded.

Accepted observations are deduplicated and stored locally with category, confidence, source count, and timestamps. The **Memory** tab shows every observation. Entries can be disabled and later re-enabled instead of being destructively deleted.

Only active memories are included as soft context in future chat prompts. The current user message and explicit corrections always override stored memory.

## Local visual generation with ComfyUI

Media generation is optional. Configure an exported ComfyUI API-format workflow in **Einstellungen**, choose the positive/negative prompt and seed node ids, run diagnostics, then enable media generation.

After an assistant reply, the local model can decide whether a visual improves the exchange. A backend-neutral prompt compiler turns the structured media intent into prompts and the configured local workflow creates the file. The reference planner keeps depicted people clearly adult and stays in a provocative/fetish-inspired but non-graphic visual lane.

## Character continuity and visual learning

A recurring companion character can use a persistent continuity key, stable seed, and continuity prompt. Media History records the generated file, seed, intent, continuity key, and feedback.

Image ratings are converted into an auditable visual-preference profile. Repeatedly liked or disliked cues such as mood, theme, style, and wardrobe softly influence later media planning. Changing or clearing a rating reverses that contribution. Current scene context and the user's current request always take priority.

## Persona snapshots

Manual and automatic persona snapshots are immutable. Restore is deliberately non-destructive:

```text
current state
    ↓
pre_restore snapshot
    ↓
load selected historical state
    ↓
write restored state as a new revision
```

A rollback can therefore itself be undone later.

## Architecture

```text
app/
├── ai/          persona, prompting, local model, behavior learning, adaptive-memory learner
├── memory/      SQLite chat/state, adaptive memory, settings, media history, audits, snapshots
├── media/       intent, visual preferences, continuity profiles, ComfyUI adapter/service
├── ui/          Chat, Persona Lab, Memory, Media History, Settings, media preview
├── diagnostics.py
└── settings.py
```

## Versioning

Application releases use Semantic Versioning. Persona snapshots, adaptive memory, model choice, media workflows, continuity profiles, visual preference memory, feedback, and generated files are local runtime state rather than repository content.
