from __future__ import annotations

from app.ai.persona import PersonaState
from app.ai.scene_evolution import RitualRepository, SceneEvolutionRepository
from app.context_inspector import build_context_snapshot
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _repositories(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    return store, SceneEvolutionRepository(store), RitualRepository(store)


def test_scene_evolution_is_conversation_scoped_and_manual_progression_is_persistent(tmp_path) -> None:
    store, evolution, _rituals = _repositories(tmp_path)

    first = evolution.start("chat-a", "night-deepens", assistant_count=7)
    second = evolution.advance("chat-a", assistant_count=8)

    assert first.stage_name == "Blue Hour"
    assert second is not None
    assert second.stage_index == 1
    assert second.stage_name == "Midnight Contrast"
    assert evolution.active("chat-b") is None

    reloaded = SceneEvolutionRepository(store)
    restored = reloaded.active("chat-a")
    assert restored is not None
    assert restored.stage_name == "Midnight Contrast"
    assert restored.last_turn == 8


def test_scene_evolution_automatic_interval_and_end_hold(tmp_path) -> None:
    _store, evolution, _rituals = _repositories(tmp_path)
    active = evolution.start(
        "chat-a",
        "threshold-shift",
        automatic=True,
        interval=2,
        assistant_count=10,
    )

    assert active.automatic is True
    assert evolution.maybe_advance("chat-a", assistant_count=11) is None
    stage_two = evolution.maybe_advance("chat-a", assistant_count=12)
    assert stage_two is not None and stage_two.stage_index == 1

    assert evolution.maybe_advance("chat-a", assistant_count=14).stage_index == 2  # type: ignore[union-attr]
    assert evolution.maybe_advance("chat-a", assistant_count=16).stage_index == 3  # type: ignore[union-attr]
    assert evolution.maybe_advance("chat-a", assistant_count=18) is None

    final = evolution.active("chat-a")
    assert final is not None
    assert final.stage_index == 3
    assert final.automatic is False


def test_ritual_auto_progression_completes_without_becoming_state_for_other_chat(tmp_path) -> None:
    store, _evolution, rituals = _repositories(tmp_path)
    active = rituals.start(
        "chat-a",
        "cooldown-close",
        automatic=True,
        interval=1,
        assistant_count=3,
    )

    assert active.step_name == "Slow Down"
    assert rituals.maybe_advance("chat-a", assistant_count=4).step_name == "Reflect"  # type: ignore[union-attr]
    assert rituals.maybe_advance("chat-a", assistant_count=5).step_name == "Closing Image"  # type: ignore[union-attr]
    assert rituals.maybe_advance("chat-a", assistant_count=6) is None
    assert rituals.active("chat-a") is None
    assert rituals.active("chat-b") is None
    assert RitualRepository(store).active("chat-a") is None


def test_ritual_loop_wraps_to_first_step(tmp_path) -> None:
    _store, _evolution, rituals = _repositories(tmp_path)
    rituals.start(
        "chat-a",
        "camera-sequence",
        automatic=True,
        interval=1,
        loop=True,
        assistant_count=0,
    )

    rituals.maybe_advance("chat-a", assistant_count=1)
    rituals.maybe_advance("chat-a", assistant_count=2)
    rituals.maybe_advance("chat-a", assistant_count=3)
    wrapped = rituals.maybe_advance("chat-a", assistant_count=4)

    assert wrapped is not None
    assert wrapped.step_index == 0
    assert wrapped.step_name == "Establishing"


def test_context_snapshot_includes_evolution_and_ritual_as_temporary_layers(tmp_path) -> None:
    store, evolution, rituals = _repositories(tmp_path)
    active_evolution = evolution.start("chat-a", "storm-passes")
    active_ritual = rituals.start("chat-a", "wardrobe-detail")

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(),
        persona=PersonaState(),
        preference_tags=[],
        scene_evolution=active_evolution,
        active_ritual=active_ritual,
    )

    assert snapshot.scene_evolution_name == "Storm Passing"
    assert snapshot.scene_evolution_stage == "Distant Rain"
    assert snapshot.ritual_name == "Wardrobe & Detail"
    assert snapshot.ritual_step == "Silhouette"
    assert "Storm Passing" in snapshot.system_prompt
    assert "Wardrobe & Detail" in snapshot.system_prompt
    assert "never an obligation" in snapshot.system_prompt
    assert "scene evolution" in snapshot.system_prompt.lower()
    assert "distant rain" in snapshot.effective_tags
    assert "silhouette" in snapshot.effective_tags
