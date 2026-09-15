# Media design and render calculation

The media pipeline is intentionally split into two local stages before ComfyUI is called.

## 1. Visual design

The local language model produces a `MediaIntent`. Besides deciding whether a visual is useful and whether it should be an image, GIF, or video, the intent now contains concrete visual-direction fields:

- mood and theme
- visual style
- wardrobe/material cues
- framing
- camera angle
- lighting
- composition
- motion direction for GIF/video
- continuity key for the recurring adult character

These fields are compiled into the backend-neutral positive prompt. The current user request and explicitly selected creative layers remain authoritative. Media planning does not create new permissions, memories, identity changes, or adult-intensity settings.

## 2. Local render calculation

`MediaRenderCalculator` converts the visual intent into a deterministic `MediaRenderPlan` before generation. The plan contains:

- width and height
- aspect ratio
- sampling steps
- CFG/guidance target
- denoise target
- frame count and FPS for motion
- calculated duration
- megapixel count
- a transparent estimated work value

The default calculation is bounded for local hardware. Still images use a larger spatial budget than motion. Full-body/silhouette cues favor a 2:3 frame, environmental/wide cues favor 16:9, centered cues can use 1:1, and the default portrait frame is 4:5. All dimensions are aligned to multiples of 64.

The work estimate is not a benchmark or promised render time. It is a comparable local planning value based on megapixels, sampling steps, and a motion factor.

## ComfyUI parameter injection

For common ComfyUI API workflows the app automatically looks for safe literal numeric inputs and applies calculated values where possible:

- `width`
- `height`
- `steps`
- `cfg` or `guidance`
- `denoise`
- `length`, `frames`, `frame_count`, or `num_frames`
- `fps` or `frame_rate`

The app does not rewrite linked graph inputs. If a value is not safely detectable, that workflow keeps its own default.

Workflow profiles can define explicit mappings when a custom node uses other input names:

```json
{
  "id": "local-motion",
  "workflow": "workflows/motion_api.json",
  "kinds": ["video"],
  "render_quality": "balanced",
  "max_megapixels": 0.7,
  "render_bindings": {
    "frames": {"node": "90", "input_key": "custom_frames"},
    "fps": {"node": "91", "input_key": "custom_rate"}
  }
}
```

Supported explicit keys are `width`, `height`, `steps`, `cfg`, `denoise`, `frames`, and `fps`. A broken explicit binding fails the generation instead of silently writing to the wrong place.

## Transparency

Every successful media event stores the complete render plan and the list of numeric parameters actually applied to ComfyUI. The **Medien → Historie & Render** view shows the visual direction, calculated target, estimated work, and applied parameter names. Older media history remains readable and simply reports that no render calculation was stored.

## Open-source and privacy boundary

This feature adds no dependency, model, cloud service, telemetry, proprietary SDK, or automatic download. Calculation happens locally in Python and generation remains on the configured local ComfyUI installation. User-supplied checkpoints, LoRAs, custom nodes, and workflows still require their own license review before redistribution or recommendation as part of a public package.
