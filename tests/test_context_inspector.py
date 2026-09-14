from __future__ import annotations

from app.ai.persona import PersonaState
from app.ai.scene_presets import ScenePreset
from app.ai.session_modes import SessionMode
from app.context_inspector import approximate_tokens, build_context_snapshot
from app.memory.core_memory import CoreMemoryRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def test_context_snapshot_exposes_effective_layers(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    store.append_message("user", "Keep this exchange short and atmospheric.")
    store.append_message("assistant", "Understood.")
    store.upsert_memory_observation(
        category="communication",
        summary="User prefers concise replies",
        confidence=0.95,
    )
    CoreMemoryRepository(store).upsert(
        memory_id=None,
        title="Stable preference",
        content="Use clear choices when asking a question",
        priority=90,
        active=True,
    )

    persona = PersonaState()
    persona.strictness.locked = True
    base_dominance = persona.dominance.current
    base_strictness = persona.strictness.current
    mode = SessionMode(
        id="focus",
        name="Focused",
        trait_offsets={"dominance": 0.20, "strictness": 0.20},
        style_tags=["controlled", "cinematic"],
    )
    scene = ScenePreset.create(
        name="Night studio",
        context="A quiet dark studio with low-key lighting",
        style_tags=["cinematic", "low light"],
    )
    settings = AppSettings(
        chat_history_messages=20,
        chat_num_ctx=100,
        chat_num_predict=50,
    )

    snapshot = build_context_snapshot(
        store=store,
        settings=settings,
        persona=persona,
        preference_tags=["precise"],
        session_mode=mode,
        scene_preset=scene,
    )

    assert snapshot.session_mode == "Focused"
    assert snapshot.scene_name == "Night studio"
    assert snapshot.effective_traits["dominance"] > base_dominance
    assert snapshot.effective_traits["strictness"] == base_strictness
    assert "strictness" in snapshot.locked_traits
    assert snapshot.effective_tags == ["precise", "controlled", "cinematic", "low light"]
    assert snapshot.core_memory == [
        "Stable preference: Use clear choices when asking a question"
    ]
    assert snapshot.adaptive_memory == ["User prefers concise replies"]
    assert len(snapshot.history) == 2
    assert "Night studio" in snapshot.system_prompt
    assert "Stable preference" in snapshot.system_prompt
    assert snapshot.approx_input_tokens > 0
    assert snapshot.warnings


def test_context_snapshot_respects_disabled_adaptive_memory(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    store.upsert_memory_observation(
        category="communication",
        summary="User prefers concise replies",
        confidence=0.95,
    )
    CoreMemoryRepository(store).upsert(
        memory_id=None,
        title="Pinned",
        content="Keep this stable",
        active=True,
    )

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(adaptive_memory_enabled=False),
        persona=PersonaState(),
        preference_tags=[],
    )

    assert snapshot.adaptive_memory == []
    assert snapshot.core_memory == ["Pinned: Keep this stable"]
    assert "Pinned: Keep this stable" in snapshot.system_prompt
    assert "User prefers concise replies" not in snapshot.system_prompt


def test_approximate_tokens_is_local_deterministic_heuristic() -> None:
    assert approximate_tokens("") == 0
    assert approximate_tokens("abcd") == 1
    assert approximate_tokens("abcdefgh") == 2
