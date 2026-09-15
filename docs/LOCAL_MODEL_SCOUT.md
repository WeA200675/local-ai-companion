# Local Model Scout

The Local Model Scout compares the Ollama models that are already installed on the machine. It is intended for cases where one model crashes, refuses the desired adult tone, or behaves inconsistently and the user wants to find a better local option without guessing.

## What it checks

For each model reported by the configured local Ollama endpoint, the scout runs the same local capability path used by the app:

- a short technical chat inference;
- a non-graphic erotic-tone probe;
- a non-graphic consensual Adult-/Kink power-play probe.

The resulting compatibility reports are stored in the same local compatibility repository used by the Settings readiness view. A failed model does not abort the whole comparison; it is recorded as unavailable and the scout continues with the remaining installed models.

The recommendation prefers technically operational models in this order: `compatible`, `limited`, then `unclear`, followed by the compatibility score. Models classified as `blocked` or `unavailable` are never recommended for the intended Adult-/Kink companion mode.

## Windows one-click use

From the repository root, double-click or run:

```powershell
.\model_scout_windows.cmd
```

The scout only evaluates already installed models. It does not download a model, install Ollama, use a cloud API, or change the selected app model by default.

To explicitly apply the recommendation after the comparison:

```powershell
.\model_scout_windows.cmd --apply-recommended
```

Optional examples:

```powershell
.\model_scout_windows.cmd --max-models 2
.\model_scout_windows.cmd --url http://127.0.0.1:11434
```

`--apply-recommended` is intentionally explicit because switching the active model changes later chat behavior. All other runtime settings, media configuration, Persona state and memories are preserved.

## Limits

The Adult-/Kink score is a local heuristic, not a guarantee that every later conversation will behave identically. It deliberately uses non-graphic adult prompts. Hardware stability can also vary between models and model sizes, so a model that fails during the scout is reported as technically unavailable rather than being treated as an adult-content refusal.
