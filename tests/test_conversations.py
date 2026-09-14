from __future__ import annotations

import pytest

from app.memory.conversation_facade import ConversationStateFacade
from app.memory.conversations import ConversationRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_conversations_isolate_history_and_switch(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    store.append_message("user", "legacy hello")

    conversations = ConversationRepository(store)
    facade = ConversationStateFacade(store, conversations)

    assert conversations.active_id() == "main"
    assert [message.content for message in facade.list_messages()] == ["legacy hello"]

    second = conversations.create("Zweite Richtung", activate=True)
    facade.append_message("user", "only second")
    facade.append_message("assistant", "second reply")

    assert [message.content for message in facade.list_messages()] == [
        "only second",
        "second reply",
    ]

    conversations.set_active("main")
    assert [message.content for message in facade.list_messages()] == ["legacy hello"]
    assert conversations.get(second.id).message_count == 2


def test_fork_copies_history_but_future_messages_diverge(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    conversations = ConversationRepository(store)
    facade = ConversationStateFacade(store, conversations)

    facade.append_message("user", "shared start")
    facade.append_message("assistant", "shared reply")
    forked = conversations.fork("main", title="Alternative", activate=True)

    assert [message.content for message in facade.list_messages()] == [
        "shared start",
        "shared reply",
    ]
    facade.append_message("user", "different branch")

    conversations.set_active("main")
    assert [message.content for message in facade.list_messages()] == [
        "shared start",
        "shared reply",
    ]
    conversations.set_active(forked.id)
    assert [message.content for message in facade.list_messages()][-1] == "different branch"


def test_archive_preserves_history_and_requires_one_active_thread(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    conversations = ConversationRepository(store)

    with pytest.raises(ValueError):
        conversations.archive("main")

    second = conversations.create("Archive me", activate=True)
    conversations.append_message("user", "keep me", conversation_id=second.id)
    conversations.archive(second.id)

    archived = conversations.get(second.id, include_archived=True)
    assert archived is not None and archived.archived is True
    assert [
        message.content
        for message in conversations.list_messages(conversation_id=second.id)
    ] == ["keep me"]

    restored = conversations.unarchive(second.id)
    assert restored.archived is False
