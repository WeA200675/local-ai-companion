# Intimacy-aware media direction

The conversation-scoped `AdultIntensityConfig` now contributes directly to the local visual-design path.

## What changes with the intimacy level

The current sexuality and kink levels add temporary visual styling cues such as adult flirtation, sensual atmosphere, provocative adult styling, fetish-inspired fashion, power-dynamic staging, posture, camera language and dark editorial atmosphere. These cues are soft overlays: the current user request, explicit creative selections, Character identity and workflow capability remain authoritative.

The levels do **not** force media generation. The media planner still decides whether a visual would improve the exchange.

## Hard boundaries

User-authored boundaries are converted into `avoid:<term>` tags. The media prompt compiler recognizes that prefix and routes those terms only to the negative prompt. They are never inserted into the positive prompt as desired content.

## Visual boundary

This layer intentionally remains non-graphic. It may direct clearly adult, sensual, erotic, fetish-inspired or dominant visual styling, but it does not turn the intimacy level into permission for graphic sexual acts, genital-focused imagery or explicit nudity. Existing adult/minor/violence guardrails remain active.

## Persistence and learning

The visual direction is derived from the current conversation's temporary intimacy state. It does not mutate Persona, Core Memory, adaptive memory or Character identity. It introduces no new dependency, cloud service, model download, telemetry or proprietary component.
