# Local model inference diagnostics

A reachable Ollama endpoint and an installed model are not enough to prove that the companion can actually generate a reply. The desktop diagnostics therefore perform two separate local checks.

## 1. Model inventory

`Sprachmodell` requests the local Ollama `/api/tags` endpoint and verifies that the configured model name is installed.

This answers only: **Is Ollama reachable and does it know this model?**

## 2. Real mini inference

`Modell-Inferenz` then sends one small non-streaming `/api/chat` request to the configured model. The request uses temperature `0`, a maximum of eight generated tokens, and a short neutral technical prompt. Any non-empty assistant response counts as a successful inference.

The health check is local only. It does not send conversation history, Persona state, memories, adult preferences, media prompts, or user data to the test request.

A cold local model can take time to load, so this probe allows at least 45 seconds before classifying the check as a timeout.

## Actionable failure classes

The diagnostic distinguishes several cases instead of reporting every problem as “model unavailable”:

- endpoint connection failure: Ollama itself is not reachable;
- configured model absent: Ollama is running but the requested model is not installed/selected;
- timeout: the model/backend did not answer in the health-check window;
- HTTP 5xx: Ollama was reached, but its local inference backend failed;
- malformed or empty response: the endpoint answered but did not return a usable chat result.

For a backend failure the UI includes a direct local isolation step such as:

```powershell
ollama run qwen2.5:7b "Hallo"
```

If the same command fails outside Local AI Companion, the error is below the app layer. The diagnostic deliberately does not guess whether GPU drivers, VRAM, RAM, CPU backend, or another Ollama/runtime problem is the root cause unless Ollama itself reports that information.

## Readiness

The app no longer marks the language-model path as technically ready merely because `/api/tags` lists the model. Both inventory and the real mini inference must succeed. Adult/Kink compatibility remains a separate capability check after basic inference is stable.

## Chat errors

The same local Ollama failure classifier is used by interactive model requests. HTTP 500-class backend crashes now preserve a short Ollama error body when available and include a concrete direct-model test instead of only showing a generic connection warning.

No new dependency, telemetry, cloud endpoint, hosted API, or proprietary SDK is required.
