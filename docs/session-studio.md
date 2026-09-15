# Session Studio

Session Studio creates coherent temporary session bundles instead of independently randomizing every creative layer.

A generated bundle can coordinate:

- Look preset
- Variety spark
- Session arc
- Scene Mixer setting, lighting, composition, and atmosphere
- Visual motif
- Mood grade
- Detail accent
- Scene Evolution
- Session Ritual
- a local media preference (`auto`, still image, or motion when a compatible local workflow exists)

The built-in compatibility profiles currently include Rain Noir, Studio Command, Soft Lounge Pulse, Mirror Mystery, Retro Afterhours, Motion Night, and Minimal Focus. Each profile contains small candidate pools that were chosen to work together. The final selection remains randomized inside those pools so repeated sessions do not become identical.

## Locks and compatibility

Creative Director locks are respected. Scene Mixer dimension locks are respected independently, so a user can keep the current setting while allowing lighting, composition, and atmosphere to change.

If a lock preserves a choice outside the selected profile's candidate pool, Session Studio does not override it. Instead it lowers the displayed compatibility score and explains which layer was preserved. Favorites for Look, Arc, and Visual Motif are preferred when they also belong to the selected compatibility pool.

## Reversible application

Before a Session Studio bundle is applied, the current temporary creative state is captured locally. The `Vorherigen Zustand wiederherstellen` action restores the previous Look, variety card, Arc stage, Scene Mixer components, Visual Motif, Mood, Detail Accent, Scene Evolution state, and Ritual state.

This restore mechanism is session-layer only. It does not touch Persona state, Core Memory, adaptive memory, Character identity, chat history, or model weights.

## Media preference

Session Studio can mark a profile as image-oriented or motion-oriented. The hint is passed only to the local media planner. Motion remains conditional: if no suitable local GIF/video workflow exists, or motion would not improve the current exchange, the planner can keep using a still image.

## Persistence and privacy

Session Studio state is stored in the existing local SQLite application state. It is conversation-scoped. No cloud service, telemetry, proprietary SDK, or additional dependency is required.

A Session Studio bundle is a temporary creative origin, not a permanent lock. After generation, every individual creative layer can still be changed manually.
