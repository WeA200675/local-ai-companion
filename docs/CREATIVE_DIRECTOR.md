# Creative Director

The Creative Director is an optional, local-only variation layer. It exists to keep longer companion sessions from becoming visually and conversationally repetitive without modifying the stable persona, Core Memory, adaptive memory, Character identity, or model weights.

## Manual surprise

`Überrasch mich` rotates every creative layer that is not locked for the active conversation:

- Look preset
- Variety / impulse card
- Session Arc
- Scene Mixer
- Visual Motif
- Mood Grade
- Detail Accent

The change is conversation-scoped. A different conversation keeps its own creative state.

## Automatic direction

Automatic direction is disabled by default. When enabled, it runs after a completed assistant response and prepares temporary context for a later turn. The response that just finished, including any media planning launched from it, keeps the context that produced it.

Controls are local and per conversation:

- interval: 2–20 completed assistant responses
- gentle: rotate one unlocked layer
- balanced: rotate three unlocked layers
- wild: rotate up to seven unlocked layers
- layer locks for Look, Impulse, Arc, Scene Mixer, Visual Motif, Mood Grade, and Detail Accent

An active Session Arc normally advances to its next phase when automatic direction selects the Arc layer. When the final phase has completed, a new Arc can be selected.

## Favorites

Look, Arc, and Visual Motif favorites are preference hints for the Creative Director. If at least one favorite exists in a category, random selection prefers that favorite pool. Favorites do not change persona learning or long-term memory.

## Scene Mixer dimension locks

Scene Mixer has finer-grained locks for:

- setting
- lighting
- composition
- atmosphere

For example, the current setting and composition can remain fixed while lighting and atmosphere continue to change. These locks are persisted locally per conversation.

## Mood and detail accents

Mood Grades alter only temporary color, tonal, and lighting direction. Detail Accents add small material, prop, reflection, hand-position, or fashion cues. Both layers can feed the local media planner and effective style tags, but neither becomes persona learning or memory.

## Transparency

The Context Inspector shows whether automatic direction is enabled, its interval and intensity, whole-layer Director locks, Scene Mixer dimension locks, and all currently active creative accents. Creative overlays remain explicitly temporary prompt context.

## Privacy and open-source boundary

The Creative Director introduces no network call and no proprietary dependency. Selection is performed locally with Python's standard random facilities and persisted in the existing local SQLite application state. The repository's open-source-only CI audit therefore remains authoritative and unchanged.
