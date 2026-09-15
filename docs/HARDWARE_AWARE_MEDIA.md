# Hardware-aware local media planning

The media pipeline can now read ComfyUI's local `/system_stats` endpoint and derive a conservative render budget without installing a GPU vendor SDK.

## Budget tiers

The probe classifies the currently reported device as `cpu`, `low`, `medium`, `high`, or `unknown`. It uses free VRAM when available, falls back to total VRAM, and also records free system RAM when ComfyUI reports it.

The tier is only a ceiling. It may reduce spatial megapixels, motion frame count, or a requested render quality when the local machine is constrained. It never silently raises a workflow profile above the profile's requested quality.

## Still vs motion

The visual planner receives the current hardware summary. On CPU/low tiers it is asked to prefer a still image unless the current user explicitly requests motion. A direct request for video/GIF/animation remains authoritative; in that case the render calculator keeps the request but constrains pixels and frames to the local budget.

## Transparency

Every generated media event stores the hardware tier, reported device, free VRAM when available, calculated render plan and the numeric parameters actually injected into ComfyUI. `Medien → Historie & Render` displays this alongside the normal render target.

## Privacy and OSS boundary

Hardware probing is local and uses the already configured ComfyUI HTTP endpoint. No telemetry, cloud service, proprietary GPU SDK, additional Python dependency, model download or vendor-specific installer is required.
