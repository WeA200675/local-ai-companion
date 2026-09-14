from __future__ import annotations

import random

from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.ai.variety import VarietyRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_variety_active_card_is_conversation_scoped(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    variety = VarietyRepository(store)

    card = variety.draw("conversation-a", rng=random.Random(1))
    assert variety.active("conversation-a") is not None
    assert variety.active("conversation-a").id == card.id
    assert variety.active("conversation-b") is None

    variety.set_active("conversation-a", None)
    assert variety.active("conversation-a") is None


def test_variety_draw_avoids_recent_cards_when_possible(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    variety = VarietyRepository(store)
    rng = random.Random(7)

    drawn = [variety.draw("conversation-a", rng=rng).id for _ in range(4)]
    assert len(set(drawn)) == 4


def test_custom_variety_card_persists_and_can_be_deleted(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    variety = VarietyRepository(store)

    custom = variety.upsert_custom(
        card_id=None,
        name="Eigener Wechsel",
        category="Eigene",
        instruction="Use a fresh conversational rhythm and keep it interactive.",
        style_tags=["fresh", "interactive", "fresh"],
    )
    assert custom.builtin is False
    assert custom.style_tags == ["fresh", "interactive"]

    variety.set_active("conversation-a", custom.id)
    assert variety.active("conversation-a").name == "Eigener Wechsel"
    assert variety.delete_custom(custom.id) is True
    assert variety.active("conversation-a") is None


def test_system_prompt_marks_variety_as_temporary_not_memory() -> None:
    prompt = build_system_prompt(
        PersonaState(),
        ["cinematic"],
        ["soft adaptive note"],
        ["Pinned: deliberate memory"],
        "Studio: low light",
        "Verspielter Funke: Use playful wit and shorter back-and-forth beats.",
    )

    assert "Active variety spark" in prompt
    assert "temporary creative framing" in prompt
    assert "never silently change persona traits, memories, or user preferences" in prompt
