from __future__ import annotations

import random

from app.ai.creative_accents import DetailAccentRepository, MoodGradeRepository
from app.ai.creative_director import CreativeDirectorConfig, CreativeDirectorRepository
from app.ai.look_presets import LookPresetRepository
from app.ai.scenario_seeds import ScenarioSeedEngine, ScenarioSeedRepository
from app.ai.scene_evolution import RitualRepository, SceneEvolutionRepository
from app.ai.scene_mixer import SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.ai.variety import VarietyRepository
from app.ai.visual_motifs import VisualMotifRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _engine(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    looks = LookPresetRepository(store)
    variety = VarietyRepository(store)
    arcs = SessionArcRepository(store)
    mixer = SceneMixerRepository(store)
    motifs = VisualMotifRepository(store)
    moods = MoodGradeRepository(store)
    details = DetailAccentRepository(store)
    evolutions = SceneEvolutionRepository(store)
    rituals = RitualRepository(store)
    director_repo = CreativeDirectorRepository(store)
    seed_repo = ScenarioSeedRepository(store)
    engine = ScenarioSeedEngine(
        seed_repo,
        looks,
        variety,
        arcs,
        mixer,
        motifs,
        moods,
        details,
        evolutions,
        rituals,
        director_repo,
    )
    return (
        engine,
        seed_repo,
        director_repo,
        looks,
        variety,
        arcs,
        mixer,
        motifs,
        moods,
        details,
        evolutions,
        rituals,
    )


def test_explicit_template_builds_only_compatible_layers(tmp_path) -> None:
    (
        engine,
        seed_repo,
        _,
        looks,
        variety,
        arcs,
        mixer,
        motifs,
        moods,
        details,
        evolutions,
        rituals,
    ) = _engine(tmp_path)
    template = engine.template("rain-noir")
    assert template is not None

    selection = engine.generate(
        "chat-a",
        template_id="rain-noir",
        seed=17,
        assistant_count=4,
    )

    assert selection.template_id == "rain-noir"
    assert selection.compatibility_score == 100
    assert selection.preserved_layers == []
    assert selection.random_seed == 17
    assert selection.media_preference == "auto"
    assert seed_repo.active("chat-a") == selection

    assert looks.active("chat-a").id in template.look_ids  # type: ignore[union-attr]
    assert variety.active("chat-a").id in template.variety_ids  # type: ignore[union-attr]
    assert arcs.active("chat-a").arc_id in template.arc_ids  # type: ignore[union-attr]
    assert motifs.active("chat-a").id in template.motif_ids  # type: ignore[union-attr]
    assert moods.active("chat-a").id in template.mood_ids  # type: ignore[union-attr]
    assert details.active("chat-a").id in template.detail_ids  # type: ignore[union-attr]
    assert evolutions.active("chat-a").plan_id in template.evolution_ids  # type: ignore[union-attr]
    assert evolutions.active("chat-a").automatic is True  # type: ignore[union-attr]
    assert rituals.active("chat-a").ritual_id in template.ritual_ids  # type: ignore[union-attr]
    assert rituals.active("chat-a").automatic is True  # type: ignore[union-attr]

    mix = mixer.active("chat-a")
    assert mix is not None
    for dimension, candidates in template.scene_components.items():
        assert mix.component_ids[dimension] in candidates


def test_generation_respects_director_and_scene_dimension_locks(tmp_path) -> None:
    (
        engine,
        _,
        director_repo,
        looks,
        _,
        _,
        mixer,
        _,
        moods,
        _,
        _,
        _,
    ) = _engine(tmp_path)
    looks.set_active("chat-a", "studio-minimal")
    moods.set_active("chat-a", "soft-film")
    original_mix = mixer.draw("chat-a", rng=random.Random(3))
    mixer.set_dimension_locked("chat-a", "setting", True)
    director_repo.set_config(
        "chat-a",
        CreativeDirectorConfig(lock_look=True, lock_mood_grade=True),
    )

    selection = engine.generate(
        "chat-a",
        template_id="rain-noir",
        seed=23,
        assistant_count=2,
    )

    assert looks.active("chat-a").id == "studio-minimal"  # type: ignore[union-attr]
    assert moods.active("chat-a").id == "soft-film"  # type: ignore[union-attr]
    assert "look" in selection.preserved_layers
    assert "mood_grade" in selection.preserved_layers
    assert "scene_mix.setting" in selection.preserved_layers
    assert selection.compatibility_score < 100
    updated_mix = mixer.active("chat-a")
    assert updated_mix is not None
    assert updated_mix.component_ids["setting"] == original_mix.component_ids["setting"]


def test_restore_previous_recovers_creative_state(tmp_path) -> None:
    (
        engine,
        seed_repo,
        _,
        looks,
        variety,
        arcs,
        mixer,
        motifs,
        moods,
        details,
        evolutions,
        rituals,
    ) = _engine(tmp_path)

    looks.set_active("chat-a", "soft-lounge")
    variety.set_active("chat-a", "afterglow")
    arcs.activate("chat-a", "mystery-night")
    arcs.advance("chat-a")
    initial_mix = mixer.draw("chat-a", rng=random.Random(8))
    motifs.set_active("chat-a", "playful-lean")
    moods.set_active("chat-a", "soft-film")
    details.set_active("chat-a", "velvet-drape")
    evolutions.start(
        "chat-a",
        "night-deepens",
        automatic=True,
        interval=3,
        assistant_count=6,
    )
    evolutions.advance("chat-a", assistant_count=6)
    rituals.start(
        "chat-a",
        "cooldown-close",
        automatic=True,
        interval=2,
        assistant_count=6,
    )
    rituals.advance("chat-a", assistant_count=6)

    engine.generate(
        "chat-a",
        template_id="studio-command",
        seed=31,
        assistant_count=10,
    )
    assert seed_repo.active("chat-a") is not None

    assert engine.restore_previous("chat-a") is True
    assert seed_repo.active("chat-a") is None
    assert looks.active("chat-a").id == "soft-lounge"  # type: ignore[union-attr]
    assert variety.active("chat-a").id == "afterglow"  # type: ignore[union-attr]
    restored_arc = arcs.active("chat-a")
    assert restored_arc is not None
    assert restored_arc.arc_id == "mystery-night"
    assert restored_arc.stage_index == 1
    restored_mix = mixer.active("chat-a")
    assert restored_mix is not None
    assert restored_mix.component_ids == initial_mix.component_ids
    assert motifs.active("chat-a").id == "playful-lean"  # type: ignore[union-attr]
    assert moods.active("chat-a").id == "soft-film"  # type: ignore[union-attr]
    assert details.active("chat-a").id == "velvet-drape"  # type: ignore[union-attr]
    restored_evolution = evolutions.active("chat-a")
    assert restored_evolution is not None
    assert restored_evolution.plan_id == "night-deepens"
    assert restored_evolution.stage_index == 1
    assert restored_evolution.automatic is True
    assert restored_evolution.interval == 3
    restored_ritual = rituals.active("chat-a")
    assert restored_ritual is not None
    assert restored_ritual.ritual_id == "cooldown-close"
    assert restored_ritual.step_index == 1
    assert restored_ritual.automatic is True
    assert restored_ritual.interval == 2


def test_random_generation_avoids_recent_template_and_is_conversation_scoped(tmp_path) -> None:
    engine, seed_repo, *_ = _engine(tmp_path)

    first = engine.generate("chat-a", seed=1, assistant_count=0)
    second = engine.generate("chat-a", seed=2, assistant_count=0)

    assert second.template_id != first.template_id
    assert seed_repo.active("chat-a") == second
    assert seed_repo.active("chat-b") is None
    assert seed_repo.recent_template_ids("chat-a")[-2:] == [
        first.template_id,
        second.template_id,
    ]


def test_motion_template_marks_local_media_preference_without_new_dependency(tmp_path) -> None:
    engine, *_ = _engine(tmp_path)

    selection = engine.generate(
        "chat-a",
        template_id="motion-night",
        seed=5,
        include_evolution=False,
        include_ritual=False,
    )

    assert selection.media_preference == "motion"
    assert "scene_evolution" in selection.preserved_layers
    assert "ritual" in selection.preserved_layers
