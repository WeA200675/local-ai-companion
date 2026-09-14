from __future__ import annotations

import random

from app.ai.creative_director import (
    CreativeDirector,
    CreativeDirectorConfig,
    CreativeDirectorRepository,
)
from app.ai.creative_recipes import CreativeRecipeManager, CreativeRecipeRepository
from app.ai.look_presets import LookPresetRepository
from app.ai.scene_mixer import SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.ai.variety import VarietyRepository
from app.ai.visual_motifs import VisualMotifRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _stack(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    looks = LookPresetRepository(store)
    variety = VarietyRepository(store)
    arcs = SessionArcRepository(store)
    mixer = SceneMixerRepository(store)
    motifs = VisualMotifRepository(store)
    recipes = CreativeRecipeRepository(store)
    manager = CreativeRecipeManager(recipes, looks, variety, arcs, mixer, motifs)
    return store, looks, variety, arcs, mixer, motifs, recipes, manager


def test_visual_motif_is_conversation_scoped_and_persistent(tmp_path) -> None:
    store, _, _, _, _, motifs, _, _ = _stack(tmp_path)

    active = motifs.set_active("chat-a", "footwear-frame")

    assert active is not None
    assert active.id == "footwear-frame"
    assert "camera" in active.prompt_text()
    assert motifs.active("chat-b") is None

    reloaded = VisualMotifRepository(store)
    assert reloaded.active("chat-a").id == "footwear-frame"  # type: ignore[union-attr]


def test_recipe_capture_restores_all_temporary_layers(tmp_path) -> None:
    _, looks, variety, arcs, mixer, motifs, recipes, manager = _stack(tmp_path)
    looks.set_active("chat-a", "leather-command")
    variety.set_active("chat-a", "visual-frame")
    arcs.activate("chat-a", "mystery-night")
    motifs.set_active("chat-a", "mirror-offset")
    original_mix = mixer.draw("chat-a", rng=random.Random(11))

    recipe = manager.capture_current("chat-a", name="My exact mix")

    looks.set_active("chat-a", "soft-lounge")
    variety.set_active("chat-a", "minimalist")
    arcs.activate("chat-a", "playful-pulse")
    motifs.set_active("chat-a", "playful-lean")
    mixer.draw("chat-a", rng=random.Random(99))

    manager.apply("chat-a", recipe.id)

    assert looks.active("chat-a").id == "leather-command"  # type: ignore[union-attr]
    assert variety.active("chat-a").id == "visual-frame"  # type: ignore[union-attr]
    assert arcs.active("chat-a").arc_id == "mystery-night"  # type: ignore[union-attr]
    assert motifs.active("chat-a").id == "mirror-offset"  # type: ignore[union-attr]
    assert mixer.active("chat-a").signature == original_mix.signature  # type: ignore[union-attr]
    assert recipes.last_applied("chat-a").id == recipe.id  # type: ignore[union-attr]


def test_builtin_recipe_draws_fresh_scene_mix(tmp_path) -> None:
    _, looks, variety, arcs, mixer, motifs, recipes, manager = _stack(tmp_path)

    applied = manager.apply("chat-a", "rain-mystery")

    assert applied.builtin is True
    assert looks.active("chat-a").id == "rainy-noir"  # type: ignore[union-attr]
    assert variety.active("chat-a").id == "mystery-beat"  # type: ignore[union-attr]
    assert arcs.active("chat-a").arc_id == "mystery-night"  # type: ignore[union-attr]
    assert motifs.active("chat-a").id == "rain-silhouette"  # type: ignore[union-attr]
    assert mixer.active("chat-a") is not None
    assert recipes.last_applied("chat-a").id == "rain-mystery"  # type: ignore[union-attr]


def test_director_can_rotate_only_visual_motif_and_prefer_favorite(tmp_path) -> None:
    store, looks, variety, arcs, mixer, motifs, _, _ = _stack(tmp_path)
    repository = CreativeDirectorRepository(store)
    director = CreativeDirector(repository, looks, arcs, mixer, variety, motifs)
    repository.set_config(
        "chat-a",
        CreativeDirectorConfig(
            lock_look=True,
            lock_variety=True,
            lock_arc=True,
            lock_scene_mix=True,
            favorite_visual_motif_ids=["steady-gaze"],
        ),
    )

    result = director.apply("chat-a", rng=random.Random(5))

    assert result.changed == ["visual_motif"]
    assert result.visual_motif is not None
    assert result.visual_motif.id == "steady-gaze"
    assert motifs.active("chat-a").id == "steady-gaze"  # type: ignore[union-attr]
