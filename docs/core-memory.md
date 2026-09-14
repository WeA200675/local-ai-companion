# Core Memory

Core Memory is the deliberate, user-authored memory layer of Local AI Companion. It is intentionally separate from adaptive memory learned from conversation feedback.

## Why two memory layers?

Adaptive memory is useful for patterns the app infers over time, but those observations are probabilistic and can be wrong. Core Memory is for information the user explicitly wants the companion to keep available as stable context.

The Memory tab therefore contains two sections:

- **Core Memory** — created and edited by the user. Each entry has a title, content, active flag, and priority from 0 to 100.
- **Adaptive observations** — learned locally by the app, confidence-scored, reviewable, and reversibly enabled or disabled.

An adaptive observation can be copied into Core Memory with `Als Core Memory übernehmen`. The copy becomes an independent user-controlled entry; future adaptive learning cannot rewrite it.

## Prompt precedence

Active Core Memory is passed to the local language model before adaptive observations. Higher-priority Core Memory entries are listed first. The current user message and explicit corrections still override both memory layers.

The model is instructed not to claim that it edited Core Memory. Only explicit user actions in the Memory UI create, edit, disable, or delete Core Memory entries.

## Persistence and privacy

Core Memory is serialized into the existing local SQLite-backed app-state store. That means it is included automatically in the app's local backup/restore lifecycle and remains behind the optional local privacy lock. No cloud service is required.
