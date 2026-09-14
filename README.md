# Local AI Companion

Private-first local desktop companion with configurable persona, controlled learning, reversible long-term memory, non-destructive snapshots, persistent conversation branches, and a local media pipeline.

## Current v0.2.0-alpha status

Implemented:

- PySide6 desktop UI with Chat, Conversations, Variety, Context Inspector, Persona Lab, Memory, Character Studio, Media History, Settings, Privacy, and Backup areas
- Local Ollama-compatible model adapter
- Persistent SQLite runtime state with separate conversation histories and non-destructive conversation forks
- Persona traits with user-controlled current value, min/max bounds, learning rate, and locks
- Feedback-driven persona learning with `pre_learning` / `learning` snapshots and an audit trail
- Adaptive local long-term interaction memory with confidence filtering, deduplication, review, and reversible enable/disable controls
- User-authored Core Memory separated from fallible adaptive memory
- Immutable persona snapshots with non-destructive restore (`pre_restore` is always written first)
- Optional ComfyUI-compatible local image/GIF/video generation backend
- Autonomous media planning after assistant replies
- Character/seed continuity memory for recurring generated companion visuals
- Persistent local media history with per-image feedback and reversible visual-preference learning
- Conversation-scoped variety cards, look presets, multi-stage Session Arcs, and a local Scene Mixer
- Read-only Context Inspector showing the effective prompt layers and approximate context pressure
- Encrypted portable backups plus staged non-destructive restore
- Open-source-only component registry and CI audit
- Local diagnostics for Ollama, model availability, ComfyUI, workflow node ids, and output paths
- Automated tests across model requests, persistence, learning, memory, snapshots, media, conversations, variety layers, settings, continuity, diagnostics, and feedback

## Privacy model

Chats, adaptive memory, preferences, generated media, model files, logs, runtime settings, and local databases stay on the local machine by default and must not be committed to the repository.

The default database is `data/companion.sqlite3`; generated media defaults to `data/generated_media/`. The `data/` directory is gitignored. Ollama and ComfyUI default to loopback addresses.

## Open-source-only rule

Required application components must remain open source and locally usable. Direct dependencies and default external components are registered in `oss_components.json` and checked by `python -m app.oss_audit` plus CI. Proprietary SDKs, mandatory cloud services, and closed-source runtime dependencies are not accepted into the required stack.

User-installed models, checkpoints, LoRAs, ComfyUI custom nodes, and workflows retain their own licenses and are not automatically claimed to be open source merely because they run locally.

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
python -m app.oss_audit
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

## Conversations and replayability

Each conversation has an isolated transcript while the base persona, Core Memory, adaptive long-term memory, and stable Character identity remain shared. Conversations can be created, renamed, archived, restored, and forked. A fork copies the selected transcript into a new branch so the same starting point can develop in a different direction without destroying the original.

The old single-chat history is migrated non-destructively into an initial main conversation.

## Variety Deck and Creative Variety Studio

The **Impulse** deck provides short-lived conversation nudges such as slower pacing, stronger visual framing, playful dialogue, a mystery beat, or a calmer afterglow. Recent cards are avoided when possible to reduce repetition. Custom cards remain local.

The **Abwechslung** area adds three deeper temporary layers:

- **Look presets** vary wardrobe and visual styling while preserving the stable Character identity. Built-ins cover noir latex, structured leather, elegant monochrome, soft lounge, studio minimal, retro glamour, and rainy noir directions.
- **Session Arcs** provide multi-stage progression such as a tension curve, mystery sequence, playful pulse, or cinematic sequence. The user advances phases explicitly; completing the final phase returns the conversation to its base state.
- **Scene Mixer** combines setting, lighting, composition, and atmosphere locally. Recent mixes are avoided when practical. A mix supplements an active Scene Preset instead of overwriting it.

All three are conversation-scoped. They influence chat and local media planning through temporary context and style tags, but they do not rewrite persona traits, Core Memory, adaptive memory, or the stable Character profile.

## Context Inspector

The **Kontext** tab exposes the effective local layers used for the next request: active conversation, base/effective persona values, locked traits, Session Mode, Scene Preset, variety spark, Look preset, Session Arc phase, Scene Mixer layer, Core Memory, adaptive memory, included transcript messages, and the generated system prompt. Token counts are intentionally approximate and require no additional tokenizer dependency.

## Local visual generation with ComfyUI

Media generation is optional. Configure an exported ComfyUI API-format workflow in **Einstellungen**, choose the positive/negative prompt and seed node ids, run diagnostics, then enable media generation.

After an assistant reply, the local model can decide whether a visual improves the exchange. A backend-neutral prompt compiler turns the structured media intent into prompts and the configured local workflow creates the file. Temporary scene, variety, look, arc, and mixer layers are passed into media planning without replacing stable character continuity.

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
├── ai/          persona, prompting, local model, learning, scenes, looks, arcs, variety
├── memory/      SQLite conversations/state, adaptive memory, settings, audits, snapshots
├── media/       intent, visual preferences, continuity profiles, ComfyUI adapter/service
├── ui/          Chat, Conversations, Variety, Context, Persona, Memory, Media, Settings
├── diagnostics.py
└── settings.py
```

## Versioning

Application releases use Semantic Versioning. Persona snapshots, adaptive memory, model choice, media workflows, continuity profiles, visual preference memory, conversation branches, temporary creative overlays, feedback, and generated files are local runtime state rather than repository content.
