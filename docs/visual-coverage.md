# Visual Coverage

Visual Coverage is a local anti-repetition layer for generated media. It tracks only compact creative categories associated with successful local generations; it does not inspect image pixels and does not require a vision model.

Tracked categories include media kind, Look, Scene Mixer setting/lighting/composition/atmosphere, Visual Motif, Mood Grade, and Detail Accent when those values can be identified from the creative tags used for the generation.

## Soft guidance

After at least four generated media items in the current conversation, the tracker can provide the local media planner with a soft coverage hint. The hint highlights underused visual treatments and recently frequent choices.

The hint is deliberately subordinate to:

- the user's current request
- explicit creative selections
- Creative Director and Scene Mixer locks
- established scene continuity
- stable Character identity

It never changes Persona traits, Core Memory, adaptive memory, model weights, or Character identity.

## Controls

The existing `Medien` tab now contains a `Visual Coverage` sub-tab. The user can:

- enable or disable coverage guidance per conversation
- choose a recent analysis window between 6 and 60 generated media items
- inspect current category counts and the exact soft guidance produced locally
- reset the coverage history for the active conversation

Coverage data is conversation-scoped and stored in the existing local application state. A reset affects only coverage history, not media files or media feedback.

## Privacy and dependencies

No new dependency, cloud service, telemetry, or proprietary component is used. The feature relies only on the already available creative metadata and local SQLite-backed application state.
