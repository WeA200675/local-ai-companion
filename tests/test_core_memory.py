from __future__ import annotations

from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.memory.core_memory import CoreMemoryRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_core_memory_is_persistent_ordered_and_user_controlled(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    repository = CoreMemoryRepository(store)

    low = repository.upsert(
        memory_id=None,
        title="Communication",
        content="Prefer short direct replies",
        priority=30,
        active=True,
    )
    high = repository.upsert(
        memory_id=None,
        title="Stable preference",
        content="Keep recurring visual identity consistent",
        priority=90,
        active=True,
    )

    reloaded = CoreMemoryRepository(StateStore(factory))
    assert [item.id for item in reloaded.list()] == [high.id, low.id]
    assert reloaded.active_prompt_entries() == [
        "Stable preference: Keep recurring visual identity consistent",
        "Communication: Prefer short direct replies",
    ]

    original_created = high.created_at
    edited = reloaded.upsert(
        memory_id=high.id,
        title="Stable preference",
        content="Keep the recurring companion visually recognizable",
        priority=95,
        active=True,
    )
    assert edited.id == high.id
    assert edited.created_at == original_created
    assert edited.priority == 95

    reloaded.set_active(high.id, False)
    assert reloaded.active_prompt_entries() == [
        "Communication: Prefer short direct replies"
    ]

    assert reloaded.delete(high.id) is True
    assert reloaded.delete(high.id) is False
    assert reloaded.get(high.id) is None


def test_core_memory_is_separate_from_fallible_adaptive_memory() -> None:
    prompt = build_system_prompt(
        PersonaState(),
        ["cinematic"],
        ["The user may prefer concise choices"],
        ["Communication rule: Address the user in German"],
    )

    assert "User-pinned Core Memory" in prompt
    assert "Communication rule: Address the user in German" in prompt
    assert "Adaptive long-term interaction memory" in prompt
    assert "The user may prefer concise choices" in prompt
    assert "current message" in prompt
    assert "Never silently rewrite" in prompt
