from __future__ import annotations

import json

from app.conversation_export import export_conversation
from app.memory.conversations import ConversationRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _repository(tmp_path) -> ConversationRepository:
    store = StateStore(make_session_factory(tmp_path / "export.sqlite3"))
    repository = ConversationRepository(store)
    repository.append_message("user", "Hallo")
    repository.append_message("assistant", "Guten Abend.")
    return repository


def test_markdown_export_contains_active_transcript(tmp_path) -> None:
    repository = _repository(tmp_path)
    path = export_conversation(repository, output_dir=tmp_path / "exports")
    text = path.read_text(encoding="utf-8")
    assert path.suffix == ".md"
    assert "# Hauptchat" in text
    assert "## User" in text
    assert "Hallo" in text
    assert "## Companion" in text
    assert "Guten Abend." in text


def test_json_export_is_portable_and_scoped(tmp_path) -> None:
    repository = _repository(tmp_path)
    other = repository.create("Andere Session", activate=True)
    repository.append_message("user", "Nur hier", conversation_id=other.id)
    path = export_conversation(
        repository,
        conversation_id=other.id,
        output_dir=tmp_path / "exports",
        format="json",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "local-ai-companion-conversation"
    assert payload["conversation"]["title"] == "Andere Session"
    assert payload["messages"] == [{"role": "user", "content": "Nur hier"}]
