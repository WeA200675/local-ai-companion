# Local chat tuning

The Settings tab exposes a small set of model controls for the interactive chat path. These values affect normal streamed companion replies only; structured JSON tasks such as persona learning, media planning, diagnostics, and adaptive-memory extraction keep their own conservative settings.

## Controls

- **Chat temperature** (`0.00` to `2.00`): lower values are more predictable; higher values allow more variation. Default: `0.85`.
- **Chat history** (`10` to `500` messages): controls how many recent persisted chat messages are sent with the next reply. Default: `60`.
- **Ollama context window**: optional `num_ctx` override. `0` means the model/backend default. Larger values can increase RAM/VRAM use substantially.
- **Response limit**: optional `num_predict` override. `0` means the model/backend default.

All values are stored locally in the existing SQLite settings state. Older databases remain compatible because missing fields receive the application defaults when loaded.

Environment-variable first-run defaults are also available:

```text
LOCAL_CHAT_TEMPERATURE
LOCAL_CHAT_HISTORY_MESSAGES
LOCAL_CHAT_NUM_CTX
LOCAL_CHAT_NUM_PREDICT
```

The application omits `num_ctx` and `num_predict` from Ollama requests when their value is zero so that the selected model's own defaults remain authoritative.
