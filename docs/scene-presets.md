# Scene Presets

Scene Presets are a temporary, user-controlled context layer for Local AI Companion. They are intended for reusable settings, atmosphere, framing, and visual style without modifying the learned persona or permanent memory.

## What a scene contains

Each local scene has:

- a name,
- a short scene/context description,
- optional comma-separated style tags.

Only one scene can be active at a time. `Basis verwenden` removes the temporary scene overlay immediately.

## Interaction with the companion

The active scene is added to the local system context as temporary framing. The current user message still has priority. The model is explicitly told not to convert the scene into permanent memory merely because it is active.

Scene style tags are merged with normal preference tags and temporary Session Mode tags. This also gives the local media planner useful visual cues. The scene description itself is supplied to media planning as active user-selected context so generated visuals can better match the current setting.

## What Scene Presets do not change

Activating a scene does not mutate:

- learned Persona traits,
- Core Memory,
- adaptive memory,
- Character Studio identity,
- the persistent base preference tags.

This makes scenes suitable for reusable roleplay/atmosphere setups while keeping long-term learning clean and reversible.

## Persistence and privacy

Scene Presets and the selected active scene are stored in the existing local SQLite-backed app state. They therefore participate in local backup/restore and remain hidden behind the optional privacy lock. No cloud service is involved.
