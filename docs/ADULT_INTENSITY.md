# Adult Intensity Controls

The Local AI Companion supports an explicitly user-controlled adult tone without turning a single intense session into permanent Persona or Memory state.

## Two independent axes

Each conversation stores two temporary 0–4 levels:

- **Sexuality**: Neutral → Flirtend → Sinnlich → Erotisch → Sehr intensiv
- **Kink / Perversitätsintensität**: Konventionell → Experimentell → Kinky → Sehr kinky → Sehr ungewöhnlich / intensiv

For each axis the user chooses both the current level and an allowed maximum. The current level can also be locked so automatic session adaptation cannot move it.

## Dynamic escalation

Dynamic escalation is enabled by default. It reacts only to direct language in the current user message and changes the current conversation level by small bounded steps. It never changes the configured maximum, locks, Persona traits, Core Memory, adaptive memory, Character identity, or model weights.

A direct request for less intensity lowers the session levels. A clear stop signal resets unlocked current levels to neutral while preserving the user's configured maxima.

The heuristic is deliberately simple and local. It is not treated as a consent model, a classifier, or persistent learning. The current user message and explicit boundaries always remain authoritative.

## Preferences and hard boundaries

The **Intimität** tab provides separate local lists for desired kink/themes and hard boundaries. These are conversation-scoped prompt context, not adaptive memory. The effective prompt tells the companion not to infer new permissions from previous sessions, memory, or creative overlays.

## Creative systems

Session Studio, Session Arcs, Rituals, Creative Director and other temporary layers remain subordinate to the current intimacy controls. They can shape pacing, setting and tone, but cannot raise sexuality or kink beyond the configured maxima.

## Visual media

Chat intensity and visual media policy are intentionally separate. The adult-intensity state can influence mood, styling, posture and fetish-inspired visual direction, while the existing local media planner continues to prohibit graphic sexual acts and genital-focused imagery. This preserves the app's non-graphic visual guardrail even when text conversation uses a stronger adult tone.

## Storage and privacy

The controls are stored locally in the existing AppState SQLite storage and are keyed by conversation id. No new dependency, network service, telemetry, cloud account, or proprietary component is introduced.
