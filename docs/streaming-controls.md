# Streaming chat controls

Interactive chat uses Ollama's streaming response mode. Text is rendered as chunks arrive instead of waiting for the full reply to finish.

## User controls

- **Stop** cancels the currently generating text reply cooperatively.
- **Esc** is the keyboard shortcut for the same action.
- **Ctrl+Return** sends the current message.
- Send, clear-chat, and input controls are temporarily disabled while the text model is generating, which prevents overlapping chat requests.

If a reply is stopped after some text has already arrived, the partial reply remains visible and is stored in the local chat history. Media generation, adaptive-memory analysis, and persona feedback learning are not started for that incomplete reply.

If the local model connection fails after some chunks have already arrived, the partial text is also preserved locally and the UI reports that the response was interrupted.

## Implementation notes

`OllamaClient.chat_stream()` consumes Ollama's newline-delimited JSON stream and yields only non-empty text chunks. `ModelWorker` owns a thread-safe stop event and checks it through the model adapter's cooperative cancellation callback. The UI appends each chunk to one assistant message and finalizes the message only when generation completes, stops, or is interrupted.

Structured model helpers such as persona learning, adaptive-memory extraction, and media planning continue to use non-streaming JSON calls because those tasks need a complete validated object before application state can change.
