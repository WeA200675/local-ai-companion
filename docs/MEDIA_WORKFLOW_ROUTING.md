# Feedback-aware media workflow routing

The media service can route one visual intent across multiple validated local ComfyUI workflow profiles.

Routing stays deterministic and local. A profile must first pass the existing workflow capability inspection; learned feedback can never make an invalid workflow runnable.

## Visual focus

The already-decided visual direction is mapped to conservative routing tags:

- `portrait`
- `full_body`
- `detail`
- `environment`
- `character`
- `motion`

Profiles may optionally declare `routing_tags`. Older catalogs remain valid because the field defaults to an empty list.

## Learned suitability

When the user gives positive or negative feedback to generated media, the existing local media history now also becomes a soft workflow-performance signal. Feedback for the same focus category is weighted more strongly than generic feedback. The learned score is bounded before it is added to the normal profile priority.

This is deliberately not a vision classifier and does not pretend to know image quality from filenames. Unrated media does not affect routing.

The media history stores the selected workflow profile, derived focus tags, checkpoint name when technically discoverable, and the feedback score that existed before the render. This makes later routing explainable.

## Checkpoint provenance

Automatic workflow inspection records the technical `CheckpointLoader` checkpoint name when present. This is provenance only. A checkpoint filename is never treated as license evidence and the new profile field `checkpoint_license_confirmed` defaults to `false`.

No model, checkpoint, LoRA, custom node, cloud service, telemetry component, or new dependency is added by this feature.
