from __future__ import annotations

from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.ai.scene_presets import ScenePresetRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_scene_presets_are_persistent_and_reversible(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    repository = ScenePresetRepository(store)

    scene = repository.upsert(
        scene_id=None,
        name="Dark studio",
        context="Private cinematic room with controlled low-key lighting",
        style_tags=["cinematic", "low light", "Cinematic", "elegant"],
    )
    assert scene.style_tags == ["cinematic", "low light", "elegant"]
    assert repository.active() is None

    active = repository.set_active(scene.id)
    assert active is not None
    assert active.id == scene.id

    reloaded = ScenePresetRepository(StateStore(factory))
    assert reloaded.active() is not None
    assert reloaded.active().name == "Dark studio"  # type: ignore[union-attr]

    edited = reloaded.upsert(
        scene_id=scene.id,
        name="Dark studio",
        context="Same private room, quieter mood and closer framing",
        style_tags=["cinematic", "close-up"],
    )
    assert edited.id == scene.id
    assert reloaded.active().context.startswith("Same private room")  # type: ignore[union-attr]

    reloaded.set_active(None)
    assert reloaded.active() is None
    assert reloaded.delete(scene.id) is True
    assert reloaded.get(scene.id) is None


def test_system_prompt_marks_scene_as_temporary() -> None:
    prompt = build_system_prompt(
        PersonaState(),
        ["cinematic"],
        [],
        [],
        "Dark studio: private room with low-key lighting",
    )

    assert "Active user-selected scene preset" in prompt
    assert "Dark studio: private room with low-key lighting" in prompt
    assert "temporary framing" in prompt
    assert "never convert it into permanent memory" in prompt
