# Automatic character reference mapping

Local AI Companion can now detect a safe ComfyUI reference-image input for imported or generated workflow profiles without requiring the user to type a node id manually.

## What is detected

The workflow inspector looks for filename-style `LoadImage` / `ImageLoader` nodes that:

- expose a literal file-name input such as `image`, `image_name`, `filename`, or `file`
- are actually connected downstream to the selected sampler
- are unambiguous: exactly one connected candidate must exist

If one safe candidate is found, the generated workflow profile stores its node id and input key. The profile is also marked as preferred for character continuity and receives the `character` routing tag.

If multiple connected image loaders exist, no automatic choice is made. The workflow remains usable for ordinary generation, but reference continuity must be configured explicitly.

Unrelated image loaders that do not feed the selected sampler are ignored.

## Runtime behavior

Older local workflow catalogs are enriched non-destructively when they are loaded. If a profile has no explicit reference mapping and one safe candidate can be detected, the app creates an ephemeral runtime mapping. The user's catalog file is not rewritten.

Explicit catalog mappings always win and are never replaced by automatic detection.

When a compatible profile is selected and a pinned Character reference exists, the existing ComfyUI adapter uploads that local image and replaces only the detected loader's file-name input. The app never sends the reference image to a cloud service.

## Limits

This is structural workflow detection, not visual quality analysis. It cannot prove that a custom workflow uses the reference image strongly or preserves identity well. The existing Media Suitability Lab and explicit image feedback remain the quality signal.

No checkpoint, LoRA, custom node, model, or workflow is downloaded by this feature. No new dependency, cloud service, telemetry component, or proprietary SDK is introduced.
