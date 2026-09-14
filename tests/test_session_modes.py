from __future__ import annotations

from app.ai.persona import PersonaState
from app.ai.session_mode_store import SessionModeStore
from app.ai.session_modes import SessionMode, SessionModeState
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_session_mode_overlay_does_not_mutate_base_persona() -> None:
    base = PersonaState()
    base.strictness.current = 0.55
    base.strictness.user_max = 0.60
    base.creativity.current = 0.70
    base.creativity.locked = True

    mode = SessionMode(
        id="test",
        name="Test",
        trait_offsets={"strictness": 0.30, "creativity": 0.20, "dominance": -0.10},
        style_tags=["cinematic", "controlled"],
    )
    effective = mode.apply(base)

    assert base.strictness.current == 0.55
    assert effective.strictness.current == 0.60
    assert effective.creativity.current == base.creativity.current
    assert effective.dominance.current == base.dominance.current - 0.10
    assert base.revision == effective.revision


def test_session_mode_merges_tags_without_duplicates() -> None:
    mode = SessionMode(
        id="tags",
        name="Tags",
        style_tags=["cinematic", "controlled", "cinematic"],
    )
    assert mode.merged_tags(["dark", "cinematic"]) == ["dark", "cinematic", "controlled"]


def test_session_mode_state_round_trip_in_local_store(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    repository = SessionModeStore(store)

    custom = SessionMode(
        id="custom",
        name="Custom",
        description="temporary overlay",
        trait_offsets={"initiative": 0.15},
        style_tags=["focused"],
    )
    repository.save(SessionModeState(modes=[custom], active_id="custom"))

    loaded = repository.load()
    active = loaded.active_mode()
    assert active is not None
    assert active.id == "custom"
    assert active.trait_offsets["initiative"] == 0.15
    assert active.style_tags == ["focused"]
