import pytest

from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_latest_exchange_replace_and_delete_are_reversible(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)

    store.append_message("user", "First")
    store.append_message("assistant", "Partial")

    assert store.latest_user_message() == "First"
    assert store.latest_exchange() == ("First", "Partial")

    store.replace_last_assistant_message("Partial continued")
    assert store.latest_exchange() == ("First", "Partial continued")

    removed = store.delete_last_assistant_message()
    assert removed == "Partial continued"
    assert store.latest_exchange() is None
    assert [message.content for message in store.list_messages()] == ["First"]


def test_delete_last_assistant_never_deletes_user_message(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    store.append_message("user", "Keep me")

    assert store.delete_last_assistant_message() is None
    assert store.latest_user_message() == "Keep me"

    with pytest.raises(KeyError):
        store.replace_last_assistant_message("No assistant exists")
