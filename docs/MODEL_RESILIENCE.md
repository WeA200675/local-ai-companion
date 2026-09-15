# Local model resilience

Interactive chat uses the configured local Ollama-compatible endpoint only. Slow first-token latency is treated as a local inference problem rather than a missing-server problem.

The Ollama adapter now uses a short connection timeout but a substantially longer inactivity/read timeout for inference. This matters for cold model loads, CPU-only execution and larger local contexts, where the model can need more than two minutes before producing a token. Requests also send a finite `keep_alive` value so Ollama can keep the selected model resident for a while between replies instead of reloading it for every exchange.

Timeouts are classified separately as `LocalModelTimeoutError` and include a practical local diagnostic hint (`ollama ps`, context/response budget, or a smaller model). There is no cloud fallback, telemetry, automatic model download or proprietary service involved.

The keep-alive is finite and can be overridden by callers. It trades RAM/VRAM residency for fewer cold starts. Cooperative Stop behavior remains unchanged: once stream chunks are flowing, the existing UI stop flag ends the reply at the next observed chunk and preserves any partial response.
