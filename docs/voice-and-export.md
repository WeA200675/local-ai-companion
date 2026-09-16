# Local Voice Studio and conversation export

## Voice Studio

The optional Voice Studio gives the companion a local text-to-speech path without adding a mandatory speech dependency to the app.

Launch it on Windows with `voice_studio_windows.cmd` or with `python -m app.voice_studio`. It can copy the latest complete Companion reply into the speech box, synthesize it in a worker thread and open the resulting WAV file with the operating system's local player.

The adapter uses the common OpenAI-compatible `POST /v1/audio/speech` shape so local servers such as Kokoro/OpenAI-compatible TTS bridges can be connected without a proprietary SDK. The configured endpoint is deliberately restricted to `localhost`, `127.0.0.1` or `::1`; a cloud/remote URL is rejected by configuration validation. The app does not install a TTS server or download a voice/model automatically.

Voice settings are stored in the existing local SQLite AppState. Generated audio defaults to `data/generated_voice/`, which remains inside the gitignored local data area.

## Conversation export

The active conversation can be exported without touching Persona, Core Memory, adaptive memory or other conversation branches:

```bash
python scripts/export_conversation.py --format markdown
python scripts/export_conversation.py --format json
```

Use `--conversation <id>` for another conversation and `--output <directory>` to choose a destination. Markdown is intended for readable private archives; JSON is a small versioned portable transcript representation.

Exports default to `data/exports/`. They can contain private conversation content and should be handled like backups. Exporting is read-only: it does not alter, archive, learn from or delete the source conversation.
