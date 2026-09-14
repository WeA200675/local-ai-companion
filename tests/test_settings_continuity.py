from __future__ import annotations

from app.ai.persona import Trait
from app.media.service import MediaService
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


class _DummyModel:
    pass


class _DummyBackend:
    enabled = True

    def close(self) -> None:
        pass


def _service(store: StateStore) -> MediaService:
    return MediaService(
        _DummyModel(),  # type: ignore[arg-type]
        _DummyBackend(),  # type: ignore[arg-type]
        store=store,
        settings=AppSettings(media_reference_enabled=True),
    )


def test_settings_and_character_continuity_round_trip(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)

    settings = AppSettings(
        model_name="local-model",
        chat_temperature=1.15,
        chat_history_messages=120,
        chat_num_ctx=16384,
        chat_num_predict=900,
        media_enabled=True,
        media_workflow=str(tmp_path / "workflow.json"),
        continuity_key="nova-main",
        media_reference_enabled=True,
        media_reference_node="12",
        media_reference_input_key="image",
        media_history_limit=321,
    )
    store.save_settings(settings)

    loaded = store.load_settings()
    assert loaded.model_name == "local-model"
    assert loaded.chat_temperature == 1.15
    assert loaded.chat_history_messages == 120
    assert loaded.chat_num_ctx == 16384
    assert loaded.chat_num_predict == 900
    assert loaded.media_enabled is True
    assert loaded.continuity_key == "nova-main"
    assert loaded.media_reference_enabled is True
    assert loaded.media_reference_node == "12"
    assert loaded.media_reference_input_key == "image"
    assert loaded.media_history_limit == 321

    first = store.load_character_profile("nova-main")
    first.register_generation("generated/example.png")
    first.set_reference(17, "generated/reference.png")
    store.save_character_profile(first)
    second = store.load_character_profile("nova-main")

    assert second.seed == first.seed
    assert second.generation_count == 1
    assert second.last_media_path == "generated/example.png"
    assert second.reference_media_id == 17
    assert second.reference_media_path == "generated/reference.png"

    second.clear_reference()
    store.save_character_profile(second)
    cleared = store.load_character_profile("nova-main")
    assert cleared.reference_media_id is None
    assert cleared.reference_media_path is None


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


def test_reference_continuity_uses_newest_liked_existing_file(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    first_id = store.record_media_event(
        path=str(first),
        kind="png",
        prompt_id="one",
        seed=1,
        continuity_key="persona-main",
        intent={"mood": "calm"},
    )
    second_id = store.record_media_event(
        path=str(second),
        kind="png",
        prompt_id="two",
        seed=2,
        continuity_key="persona-main",
        intent={"mood": "confident"},
    )
    store.set_media_feedback(first_id, "positive")
    store.set_media_feedback(second_id, "positive")

    service = _service(store)
    assert service._reference_path("persona-main") == second
    assert service._reference_path("another-character") is None


def test_pinned_reference_beats_newer_liked_image(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    anchor = tmp_path / "anchor.png"
    newer = tmp_path / "newer.png"
    anchor.write_bytes(b"anchor")
    newer.write_bytes(b"newer")

    anchor_id = store.record_media_event(
        path=str(anchor),
        kind="png",
        prompt_id="anchor",
        seed=1,
        continuity_key="persona-main",
        intent={"mood": "calm"},
    )
    newer_id = store.record_media_event(
        path=str(newer),
        kind="png",
        prompt_id="newer",
        seed=2,
        continuity_key="persona-main",
        intent={"mood": "bold"},
    )
    store.set_media_feedback(newer_id, "positive")
    profile = store.load_character_profile("persona-main")
    profile.set_reference(anchor_id, str(anchor))
    store.save_character_profile(profile)

    assert _service(store)._reference_path("persona-main") == anchor


def test_video_is_not_used_as_reference_fallback(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    video = tmp_path / "liked.mp4"
    video.write_bytes(b"video")
    media_id = store.record_media_event(
        path=str(video),
        kind="mp4",
        prompt_id="video",
        seed=1,
        continuity_key="persona-main",
        intent={"mood": "cinematic"},
    )
    store.set_media_feedback(media_id, "positive")

    assert _service(store)._reference_path("persona-main") is None


def test_trait_learning_respects_bounds_and_rate() -> None:
    trait = Trait(current=0.50, user_min=0.40, user_max=0.60, learning_rate=0.10)
    trait.apply_delta(0.5)
    assert trait.current == 0.55

    trait.apply_delta(1.0)
    assert trait.current == 0.60

    trait.locked = True
    trait.apply_delta(-1.0)
    assert trait.current == 0.60
