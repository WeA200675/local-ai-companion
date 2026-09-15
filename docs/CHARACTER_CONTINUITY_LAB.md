# Character Continuity Lab

The Character Studio can open a local continuity calibration dialog when a fixed Character reference image exists.

The lab is meant to answer a practical question that workflow structure alone cannot answer: does this local reference-enabled ComfyUI workflow keep the recurring companion visually recognizable when the framing and scene change?

## Test sequence

The suite renders three small deterministic local images with the same pinned Character reference and the same stored visual identity:

- close portrait
- full-body / head-to-toe
- environmental scene change

The render calculator still applies the configured hardware budget, workflow quality and maximum megapixel rules. The reference image is uploaded only to the configured local ComfyUI endpoint.

## Feedback and routing

The app deliberately does not use an opaque vision classifier to decide whether identity was preserved. The user marks each result as either good identity preservation or identity drift.

Each probe is stored in normal media history with:

- continuity key
- workflow profile
- checkpoint provenance when known
- `character` plus the specific visual focus tag
- pinned reference media id
- render plan and applied ComfyUI parameters

The existing workflow-performance learner therefore receives the same explicit feedback signal and can prefer workflows that perform better for Character scenes and the relevant framing.

Ratings remain reversible through normal Media History feedback.

## Safety and privacy

Probe scenes are intentionally non-graphic and depict only clearly adult characters. The lab does not change the application's normal media-content boundaries.

Nothing is downloaded automatically. No checkpoint, model, LoRA or custom node is installed. No cloud service, telemetry, proprietary SDK or new dependency is introduced.
