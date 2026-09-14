from __future__ import annotations

import random

from app.ai.creative_director import (
    CreativeDirector,
    CreativeDirectorConfig,
    CreativeDirectorRepository,
)
from app.ai.look_presets import LookPresetRepository
from app.ai.scene_mixer import SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.ai.variety import VarietyRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _director(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    looks = LookPresetRepository(store)
    arcs = SessionArcRepository(store)
    mixer = SceneMixerRepository(store)
    variety = VarietyRepository(store)
    repository = CreativeDirectorRepository(store)
    director = CreativeDirector(repository, looks, arcs, mixer, variety)
    return repository, director, looks, arcs, mixer, variety


def test_director_is_opt_in(tmp_path) -> None:
    repository, director, *_ = _director(tmp_path)

    assert repository.config("chat-a").enabled is False
    assert director.maybe_rotate("chat-a", assistant_count=100, rng=random.Random(1)) is None


def test_surprise_respects_locks_and_prefers_favorites(tmp_path) -> None:
    repository, director, looks, arcs, mixer, variety = _director(tmp_path)
    repository.set_config(
        "chat-a",
        CreativeDirectorConfig(
            lock_variety=True,
            lock_scene_mix=True,
            favorite_look_ids=["noir-latex"],
            favorite_arc_ids=["tension-curve"],
        ),
    )

    result = director.apply("chat-a", rng=random.Random(7))

    assert result.changed == ["look", "arc"]
    assert result.look is not None and result.look.id == "noir-latex"
    assert result.arc is not None and result.arc.arc_id == "tension-curve"
    assert looks.active("chat-a").id == "noir-latex"  # type: ignore[union-attr]
    assert arcs.active("chat-a").arc_id == "tension-curve"  # type: ignore[union-attr]
    assert mixer.active("chat-a") is None
    assert variety.active("chat-a") is None


def test_automatic_rotation_honors_interval_and_marks_turn(tmp_path) -> None:
    repository, director, *_ = _director(tmp_path)
    repository.set_config(
        "chat-a",
        CreativeDirectorConfig(
            enabled=True,
            interval=2,
            intensity="gentle",
            lock_variety=True,
            lock_arc=True,
            lock_scene_mix=True,
            favorite_look_ids=["studio-minimal"],
        ),
    )

    assert director.maybe_rotate("chat-a", assistant_count=1, rng=random.Random(3)) is None
    result = director.maybe_rotate("chat-a", assistant_count=2, rng=random.Random(3))
    assert result is not None
    assert result.changed == ["look"]
    assert repository.last_turn("chat-a") == 2
    assert director.maybe_rotate("chat-a", assistant_count=3, rng=random.Random(4)) is None
    assert director.maybe_rotate("chat-a", assistant_count=4, rng=random.Random(4)) is not None
    assert repository.last_turn("chat-a") == 4


def test_scene_mixer_dimension_locks_preserve_selected_parts(tmp_path) -> None:
    _, _, _, _, mixer, _ = _director(tmp_path)
    first = mixer.draw("chat-a", rng=random.Random(11))
    mixer.set_dimension_locked("chat-a", "setting", True)
    mixer.set_dimension_locked("chat-a", "composition", True)

    second = mixer.draw("chat-a", rng=random.Random(99))

    assert mixer.locked_dimensions("chat-a") == {"setting", "composition"}
    assert second.component_ids["setting"] == first.component_ids["setting"]
    assert second.component_ids["composition"] == first.component_ids["composition"]
    assert second.component_ids["lighting"] in {
        "low-key",
        "neon-edge",
        "warm-lamp",
        "hard-window",
        "silver-rim",
    }
    assert second.component_ids["atmosphere"] in {
        "controlled",
        "playful",
        "mysterious",
        "dreamlike",
        "editorial",
    }
