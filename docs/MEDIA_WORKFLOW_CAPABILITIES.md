# Media workflow capability inspection

A workflow profile now has two separate concepts: what the catalog **declares** and what the local workflow can be **validated** to accept.

## Validation

For every enabled profile the app reads the local ComfyUI API workflow and checks the configured positive-prompt, negative-prompt and seed mappings. Only profiles with usable required mappings are considered runnable by automatic media routing.

The inspector also reports:

- declared media kinds (`image`, `gif`, `video`)
- conservative output-node evidence when common ComfyUI save/combine nodes can be recognized
- whether the configured reference-image input actually exists
- render controls that can be set safely (`width`, `height`, `steps`, `cfg`, `denoise`, `frames`, `fps`)
- values that will remain under the workflow's own defaults
- broken explicit render bindings and other warnings

Custom output nodes are intentionally treated conservatively. Missing output-node evidence is a warning, not automatic rejection, because a user-owned custom node may use an unfamiliar class name. The profile declaration remains authoritative after its required prompt/seed mappings validate.

## Routing

When a profile catalog is configured, the visual planner receives only media kinds backed by runnable profiles. Automatic routing cannot queue a broken profile. If the model asks for an unavailable kind, a still image may be used only when an image workflow is runnable and the current user did not explicitly request motion. An explicit motion request with no validated motion workflow is skipped instead of silently running the wrong workflow.

Reference-image routing receives a bonus only when the reference mapping is actually validated. A configured-but-broken reference input is not uploaded to that profile.

## Diagnostics

`Setup & Diagnose` now includes a `Medien-Fähigkeiten` entry showing a compact capability matrix for the active workflow catalog.

All inspection is local file analysis. It adds no dependency, cloud service, telemetry, model download or proprietary component.
