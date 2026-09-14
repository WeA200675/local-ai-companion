from __future__ import annotations

from typing import Any

from app.ai.model import ChatMessage
from app.memory.conversations import ConversationRepository
from app.memory.store import StateStore


class ConversationStateFacade:
    """Delegate global state to StateStore while isolating chat methods per conversation."""

    def __init__(self, store: StateStore, conversations: ConversationRepository) -> None:
        self.base_store = store
        self.conversations = conversations

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_store, name)

    def append_message(self, role: str, content: str) -> None:
        self.conversations.append_message(role, content)

    def list_messages(self, limit: int = 100) -> list[ChatMessage]:
        return self.conversations.list_messages(limit=limit)

    def latest_user_message(self) -> str | None:
        return self.conversations.latest_user_message()

    def latest_exchange(self) -> tuple[str, str] | None:
        return self.conversations.latest_exchange()

    def delete_last_assistant_message(self) -> str | None:
        return self.conversations.delete_last_assistant_message()

    def replace_last_assistant_message(self, content: str) -> None:
        self.conversations.replace_last_assistant_message(content)

    def assistant_message_count(self) -> int:
        return self.conversations.assistant_message_count()

    def clear_messages(self) -> None:
        self.conversations.clear_messages()
