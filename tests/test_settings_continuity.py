from __future__ import annotations

from app.ai.persona import Trait
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def test_settings_and_character_continuity_round_trip(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)

    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow=str(tmp_path / "workflow.json"),
        continuity_key="nova-main",
        media_history_limit=321,
    )
    store.save_settings(settings)

    loaded = store.load_settings()
    assert loaded.model_name == "local-model"
    assert loaded.media_enabled is True
    assert loaded.continuity_key == "nova-main"
    assert loaded.media_history_limit == 321

    first = store.load_character_profile("nova-main")
    first.register_generation("generated/example.png")
    store.save_character_profile(first)
    second = store.load_character_profile("nova-main")

    assert second.seed == first.seed
    assert second.generation_count == 1
    assert second.last_media_path == "generated/example.png"


def test_media_history_feedback_updates_character_and_visual_preferences(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    profile = store.load_character_profile("persona-main")

    media_id = store.record_media_event(
        path="data/generated_media/example.png",
        kind="png",
        prompt_id="prompt-1",
        seed=profile.seed,
        continuity_key="persona-main",
        intent={
            "mood": "dominant",
            "theme": "dark lounge",
            "visual_style": "cinematic noir",
            "wardrobe": ["latex jacket", "boots"],
        },
    )

    store.set_media_feedback(media_id, "positive")
    event = store.list_media_events()[0]
    visual = store.load_visual_preferences()
    assert event["feedback"] == "positive"
    assert event["seed"] == profile.seed
    assert store.load_character_profile("persona-main").positive_feedback == 1
    assert visual.liked["dominant"] == 1
    assert visual.liked["cinematic noir"] == 1
    assert visual.liked["latex jacket"] == 1

    store.set_media_feedback(media_id, "negative")
    changed = store.load_character_profile("persona-main")
    visual = store.load_visual_preferences()
    assert changed.positive_feedback == 0
    assert changed.negative_feedback == 1
    assert "dominant" not in visual.liked
    assert visual.disliked["dominant"] == 1

    store.set_media_feedback(media_id, None)
    cleared = store.load_character_profile("persona-main")
    visual = store.load_visual_preferences()
    assert cleared.negative_feedback == 0
    assert "dominant" not in visual.disliked


def test_trait_learning_respects_bounds_and_rate() -> None:
    trait = Trait(current=0.50, user_min=0.40, user_max=0.60, learning_rate=0.10)
    trait.apply_delta(0.5)
    assert trait.current == 0.55

    trait.apply_delta(1.0)
    assert trait.current == 0.60

    trait.locked = True
    trait.apply_delta(-1.0)
    assert trait.current == 0.60
