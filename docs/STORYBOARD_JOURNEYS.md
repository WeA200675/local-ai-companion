# Storyboard Journeys

Storyboard Journeys extend Session Studio from a single coherent session seed into a longer, multi-chapter local dramaturgy.

## Design goals

A Journey coordinates the creative layers that already exist in the application instead of inventing a second persona or memory system. Each chapter applies one compatible Session Studio template, which can in turn coordinate Look, Variety, Session Arc, Scene Mixer, Visual Motif, Mood Grade, Detail Accent, Scene Evolution and Ritual.

Journeys are conversation-scoped and temporary. They do not write Persona traits, Core Memory, adaptive memory, stable Character identity, adult-intensity preferences, maxima or boundaries. The user's current request and configured boundaries always take precedence over the chapter plan.

## Built-in journeys

The initial built-ins are:

- **Rain to Dawn** — Rain Noir → Mirror Mystery → Motion Night → Minimal Focus.
- **Studio Presence** — Studio Command → Minimal Focus → Mirror Mystery → Soft Lounge Pulse.
- **Velvet Afterhours** — Retro Afterhours → Soft Lounge Pulse → Mirror Mystery → Minimal Focus.
- **Mystery Loop** — Mirror Mystery → Rain Noir → Studio Command → Soft Lounge Pulse.
- **Cinematic Presence** — Minimal Focus → Studio Command → Motion Night → Retro Afterhours.

Each chapter also provides a compact high-level instruction and style tags. The instruction is added to the local chat prompt as temporary dramaturgy. It is never permission to exceed intimacy settings or ignore a correction, boundary or stop signal.

## Progression

A Journey can be advanced manually or automatically after a configurable number of completed assistant replies. Automatic progression is based only on the local conversation's assistant-message count. A small UI timer observes that count; it does not use a cloud scheduler or background service.

Scene Evolution and Ritual can optionally continue automatically inside each chapter. At the final chapter, automatic Journey progression stops and marks the Journey completed. It does not abruptly restore or replace the final creative state.

The base random seed is stored locally. Each chapter derives a deterministic random seed from it, so moving back to an earlier chapter reproduces the same Session Studio choices unless explicit locks or available creative definitions have changed.

## Reversibility

Starting a Journey captures the complete temporary creative state immediately before its first chapter. It also remembers an existing Session Studio seed marker if one was active.

Two endings are available:

- **Journey beenden & Ursprung wiederherstellen** restores the temporary creative state from before Journey start and reinstates the prior Session Studio marker when one existed.
- **Journey lösen · aktuellen Zustand behalten** stops Journey coordination but intentionally leaves the current temporary creative layers in place.

The restore path reuses Session Studio's existing reversible state restoration rather than rewriting Persona or memory data.

## Interaction with manual changes

Creative locks remain authoritative because every chapter is applied through the compatibility-aware Scenario Seed engine. A manually selected Session Seed from the Session Studio UI detaches an active Journey, because an explicit current user action outranks automatic Journey direction.

Other manual creative changes remain possible while a Journey is active. A later automatic chapter transition may replace unlocked temporary layers as part of the next chapter, while locked layers are preserved by the Scenario Seed engine.

## Media

Each Journey chapter inherits its Session Studio template's local media preference. Motion-oriented chapters prefer a configured local motion workflow only when one is available and useful; otherwise the existing local image fallback remains in control.

The media planner keeps its separate adult/non-graphic visual guardrails. A text-side intimacy level or Journey chapter is not permission for graphic imagery.

## Privacy and open-source boundary

Storyboard Journeys add no dependency, telemetry, hosted service or proprietary component. State is stored through the existing local SQLite/AppState path. The required runtime remains the existing open-source-only stack.

User-installed checkpoints, LoRAs, ComfyUI custom nodes and workflows keep their own licenses and are not automatically classified as open source by the application.
