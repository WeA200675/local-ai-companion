# Chat backend failure recovery

Interactive chat now treats a failed local inference as a recoverable attempt instead of making the user resend and duplicate the same message.

## Behavior

When a model request fails before any assistant text is produced:

- the user message remains exactly once in the local conversation history;
- the transcript receives a visible local failure marker;
- the existing regenerate action changes its label to a failure-specific **Wiederholen** action;
- using that action reuses the latest stored user turn and does not append a duplicate user message;
- the error dialog distinguishes common timeout, Ollama-unreachable, model-missing, and local inference-backend failures;
- actionable technical detail from the local Ollama backend is retained when available.

If partial assistant text was already streamed before the backend failed, the existing interrupted-response path remains authoritative: the partial text is stored locally and **Fortsetzen** can be used instead of treating the exchange as a zero-output failure.

A successful retry, an intentional stop, a partial-response interruption, conversation switching, or clearing the chat resets the transient failure UI state. No failure marker is written into long-term memory, Persona learning, or the conversation database.

This feature adds no dependency, cloud service, telemetry, model download, or proprietary component.
