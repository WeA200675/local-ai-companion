# Local model fallback chain

The desktop can use an explicit ordered fallback chain for local Ollama models.

## Order of recovery

Interactive chat first uses the configured primary model and the existing Ollama reconnect policy. A transient model-backend crash therefore follows this order:

1. primary model request,
2. up to three fresh Ollama reconnect attempts,
3. first approved fallback model,
4. later approved fallback models in the order selected by the user.

A successful fallback becomes the active runtime model for the rest of that desktop process. The saved primary model is not silently replaced; after an app restart the configured primary is tried again.

## When fallback is allowed

Automatic model switching starts only for model/backend failures such as a local `llama-server` crash that remains after reconnects. It is deliberately not started for:

- an unreachable Ollama endpoint,
- a long inference timeout,
- a missing primary model,
- ordinary non-retryable 4xx responses.

Changing the model cannot repair an Ollama service that is completely offline, and retrying a long timeout with several large models could block the UI for an excessive time.

## Streaming safety

The fallback chain is only used before the first response token appears. If a model fails after partial text has already reached the chat, that text is preserved and the existing interrupted-response workflow is used. The request is never silently replayed with another model after partial output.

## Selecting fallback models

Open the graphical catalog:

```powershell
.\model_scout_windows.cmd
```

A catalog model can be added with **Als Fallback zulassen** only after it is:

- locally installed,
- part of the strict Apache-2.0/MIT catalog,
- technically operational in the local Adult-/Kink compatibility probe,
- not classified as blocked or unavailable by that probe.

The selected order is shown as `Modell A → Modell B → ...`. Removing all entries disables the fallback layer.

The fallback policy is stored in its own local AppState record. Saving unrelated application settings therefore cannot accidentally erase the chain.

## Open-source boundary

The runtime re-validates each saved fallback against the strict catalog and the cached local compatibility report at startup. A manually altered/custom model name that is not in the strict catalog cannot become an automatic fallback through this path.

No model is downloaded, selected, or added to the chain without an explicit user action. No cloud service, telemetry, proprietary SDK, or new dependency is involved.
