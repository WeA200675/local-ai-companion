# Ollama reconnect fallback

Interactive and helper model calls now use a conservative local reconnect layer.

## Default behavior

When a request fails because the local Ollama endpoint disappears, the HTTP transport breaks, or Ollama returns a retryable 5xx/backend crash, the client keeps the original request and performs up to **three fresh reconnect attempts** after the initial failure.

The default delay is short exponential backoff: about 0.75 s, 1.5 s and 3 s. For an owned HTTP client, pooled sockets are discarded before each retry so a restarted Ollama daemon/model runner is contacted with a fresh connection.

The fallback does **not** automatically replay:

- a long inference timeout;
- a missing model / 404;
- ordinary non-retryable 4xx errors;
- invalid model output that is not a backend/transport failure.

## Streaming safety

Streaming chat is automatically retried only before the first assistant token reaches the UI. If Ollama fails after partial text has already been emitted, the app preserves that partial reply and surfaces the interruption instead of replaying the whole request and risking duplicate/mixed text.

## Scope

The policy lives in `OllamaClient`, so the same local resilience applies to normal chat and model-backed helper operations that use the shared client. It does not restart Windows services, install Ollama, download models, switch models, or contact any cloud service.

After all three reconnect attempts fail, the final error explicitly states that automatic Ollama reconnection was exhausted; the existing manual retry path remains available.
