# Context Inspector

The **Kontext** tab is a read-only transparency view for the next local chat request. It does not change persona, memory, scenes, settings, or chat history.

It shows:

- the configured local model, context window, and response budget;
- base persona values beside the effective values after a temporary Session Mode;
- locked traits that a Session Mode cannot override;
- the active Scene Preset and merged style/preference tags;
- active user-authored Core Memory;
- active adaptive memory when adaptive memory is enabled;
- the chat-history messages that fit inside the configured history-message limit;
- the exact application-generated system prompt used by the local chat layer;
- a rough local estimate of input-token use and remaining configured context capacity.

## Token estimate

The app intentionally does not add a tokenizer dependency merely for this screen. It uses a simple deterministic character-based estimate plus a small per-message framing allowance. The selected Ollama model's own tokenizer remains authoritative, so the value is displayed as an approximation rather than a guarantee.

## Privacy

The Context Inspector is inside the same tab container as Chat, Memory, Media, and Settings. If the local privacy lock is active, the inspector is hidden behind the lock screen as well.

No context data is uploaded for inspection. Refreshing the view reads only local application state.
