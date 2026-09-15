# Automatic standard ComfyUI workflow

The media setup wizard can now build a usable image workflow even when the user has not exported an API workflow from ComfyUI manually.

## Flow

1. Start local ComfyUI.
2. Open `media_setup_windows.cmd` or the media setup wizard in the app.
3. Press **Installierte Checkpoints erkennen**.
4. The wizard reads ComfyUI's local `/object_info` metadata and lists checkpoint names exposed by the standard `CheckpointLoaderSimple` node.
5. Select one checkpoint and explicitly confirm that its license has been checked separately for the project's Open-Source requirements.
6. Press **Standard-Bildworkflow erzeugen**.
7. The wizard writes a local API-format workflow under `data/generated_workflows/` (relative to the configured media output parent), analyzes it with the existing capability system and can perform the existing real smoke render.
8. On successful setup, the generated workflow/profile is stored in the normal local media configuration.

No checkpoint, model, LoRA, or custom node is downloaded by this feature.

## Generated core graph

The builder deliberately uses only ordinary ComfyUI core node types:

`CheckpointLoaderSimple -> CLIPTextEncode (+/-) -> EmptyLatentImage -> KSampler -> VAEDecode -> SaveImage`

The resulting workflow exposes literal `width`, `height`, `seed`, `steps`, `cfg`, and `denoise` fields, so the existing media render calculator can adapt those values to scene design and local hardware.

Sampler and scheduler choices are read from the local ComfyUI `KSampler` object metadata. The builder prefers common core choices such as `euler` and `normal` when available and otherwise uses a locally reported choice.

## License boundary

ComfyUI `object_info` is a technical node/model inventory, not a trusted license registry. A checkpoint name is therefore **never** interpreted as proof that its weights are Open Source. The UI requires an explicit license confirmation before it generates a workflow from a discovered checkpoint.

This preserves the project rule that required components must be Open Source while avoiding false license claims about user-installed checkpoints.

## Privacy

Discovery talks only to the configured local ComfyUI endpoint. The workflow is generated and stored locally. No cloud service, telemetry, proprietary SDK, or new Python dependency is introduced.
