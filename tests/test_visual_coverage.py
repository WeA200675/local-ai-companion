from __future__ import annotations

from app.ai.scene_mixer import SceneMix
from app.media.coverage import VisualCoverageConfig, VisualCoverageRepository, infer_media_kind
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _repository(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    return VisualCoverageRepository(StateStore(factory))


def _mix(
    *,
    setting: str = "dark-studio",
    lighting: str = "low-key",
    composition: str = "close-up",
    atmosphere: str = "controlled",
) -> SceneMix:
    ids = {
        "setting": setting,
        "lighting": lighting,
        "composition": composition,
        "atmosphere": atmosphere,
    }
    return SceneMix(
        signature=":".join(ids.values()),
        title="test mix",
        context="",
        component_ids=ids,
    )


def test_coverage_guidance_appears_after_repeated_visuals(tmp_path) -> None:
    repository = _repository(tmp_path)
    for _ in range(4):
        repository.record(
            "chat-a",
            kind="image",
            look_id="studio-minimal",
            scene_mix=_mix(),
            motif_id="steady-gaze",
            mood_id="cool-steel",
            detail_id="metal-accent",
        )

    summary = repository.summary("chat-a")
    assert summary.sample_count == 4
    composition = next(item for item in summary.dimensions if item.key == "composition")
    assert composition.counts["close-up"] == 4
    assert "close-up" in composition.overused_ids
    assert "full-silhouette" in composition.underused_ids

    guidance = repository.guidance("chat-a")
    assert "Local visual coverage soft hint" in guidance
    assert "Komposition" in guidance
    assert "Close-up" in guidance
    assert "Silhouette" in guidance
    assert "explicit selection" in guidance


def test_coverage_is_conversation_scoped_and_resettable(tmp_path) -> None:
    repository = _repository(tmp_path)
    for _ in range(4):
        repository.record("chat-a", kind="image", scene_mix=_mix())
    for _ in range(2):
        repository.record(
            "chat-b",
            kind="video",
            scene_mix=_mix(lighting="neon-edge", composition="wide-frame"),
        )

    assert repository.summary("chat-a").sample_count == 4
    assert repository.summary("chat-b").sample_count == 2
    assert repository.guidance("chat-a")
    assert repository.guidance("chat-b") == ""

    repository.reset("chat-a")
    assert repository.summary("chat-a").sample_count == 0
    assert repository.summary("chat-b").sample_count == 2


def test_config_can_disable_guidance_and_bound_recent_window(tmp_path) -> None:
    repository = _repository(tmp_path)
    for index in range(10):
        repository.record(
            "chat-a",
            kind="image",
            scene_mix=_mix(composition="close-up" if index < 7 else "wide-frame"),
        )

    repository.set_config("chat-a", VisualCoverageConfig(enabled=False, recent_window=6))
    assert repository.summary("chat-a").sample_count == 6
    assert repository.guidance("chat-a") == ""

    repository.set_config("chat-a", VisualCoverageConfig(enabled=True, recent_window=6))
    assert repository.guidance("chat-a")


def test_media_kind_is_inferred_locally_from_file_suffix() -> None:
    assert infer_media_kind("frame.png") == "image"
    assert infer_media_kind("loop.gif") == "gif"
    assert infer_media_kind("clip.mp4") == "video"
    assert infer_media_kind("clip.webm") == "video"
