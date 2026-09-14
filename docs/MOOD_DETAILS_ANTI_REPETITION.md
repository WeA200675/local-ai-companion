# Mood, Detail Accents, and Anti-Repetition

This feature set adds three local-only variation layers designed to keep long-running companion sessions from feeling visually or conversationally repetitive.

## Mood Grades

Mood Grades are conversation-scoped temporary color, light, and tonal directions. They can influence both chat framing and local media planning while leaving stable Character Studio identity untouched.

Built-in grades include Amber Noir, Cool Steel, Silver Monochrome, Neon Night, Soft Film, Editorial Punch, and Faded Vintage.

## Detail Accents

Detail Accents add one small temporary staging cue at a time, such as gloves and hardware detail, rain on glass, chair geometry, a controlled mirror edge, footwear reflections, metallic accents, fabric texture, or a neutral hand prop.

They are intentionally non-explicit and composition-oriented. Their purpose is to produce new hand positions, textures, props, reflections, and framing details without rewriting the persona or learning them as permanent preferences.

## Creative Director integration

Mood Grades and Detail Accents are full Creative Director layers. They can be rotated automatically or by `Überrasch mich`, and each layer can be locked independently. Automatic direction remains opt-in.

Creative Recipes also capture and restore the active Mood Grade and Detail Accent when those repositories are available.

## Anti-Repetition tracker

The Anti-Repetition tracker is enabled by default per conversation and works completely locally. It stores only compact pattern traces for a small recent window:

- a normalized opening pattern from completed assistant replies
- a compact signature of the temporary creative layers used for that reply

If recent replies reuse the same opening pattern too often, or the same creative combination has remained unchanged for several replies, the next prompt receives a soft variation hint. The hint never overrides the current user message, explicit creative selections, or locks.

The tracker is not adaptive memory and does not modify persona traits. Its local pattern history can be reset at any time from the `Mood & Details` tab.

## Privacy and open-source boundary

No new dependency, network service, telemetry endpoint, cloud API, or proprietary component is introduced. State is persisted through the existing local application state. The project's open-source-only CI policy remains in force.
