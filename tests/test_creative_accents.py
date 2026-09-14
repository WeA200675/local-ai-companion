from __future__ import annotations

import random

from app.ai.anti_repetition import AntiRepetitionConfig, AntiRepetitionRepository
from app.ai.creative_accents import DetailAccentRepository, MoodGradeRepository
from app.ai.creative_director import (
    CreativeDirector,
    CreativeDirectorConfig,
    CreativeDirectorRepository,
)
from app.ai.creative_recipes import CreativeRecipeManager, CreativeRecipeRepository
from app.ai.look_presets import LookPresetRepository
from app.ai.persona import PersonaState
from app.ai.scene_mixer import SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.ai.variety import VarietyRepository
from app.ai.visual_motifs import VisualMotifRepository
from app.context_inspector import build_context_snapshot
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _stack(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    looks = LookPresetRepository(store)
    variety = VarietyRepository(store)
    arcs = SessionArcRepository(store)
    mixer = SceneMixerRepository(store)
    motifs = VisualMotifRepository(store)
    moods = MoodGradeRepository(store)
    details = DetailAccentRepository(store)
    anti = AntiRepetitionRepository(store)
    director_repository = CreativeDirectorRepository(store)
    director = CreativeDirector(
        director_repository,
        looks,
        arcs,
        mixer,
        variety,
        motifs,
        moods,
        details,
    )
    recipe_repository = CreativeRecipeRepository(store)
    recipe_manager = CreativeRecipeManager(
        recipe_repository,
        looks,
        variety,
        arcs,
        mixer,
        motifs,
        moods,
        details,
    )
    return (
        store,
        looks,
        variety,
        arcs,
        mixer,
        motifs,
        moods,
        details,
        anti,
        director_repository,
        director,
        recipe_repository,
        recipe_manager,
    )


def test_accents_are_conversation_scoped_and_persistent(tmp_path) -> None:
    store, *_, moods, details, anti, _repo, _director, _recipes, _manager = _stack(tmp_path)

    mood = moods.set_active("chat-a", "amber-noir")
    detail = details.set_active("chat-a", "glove-buckle")

    assert mood is not None and mood.id == "amber-noir"
    assert detail is not None and detail.id == "glove-buckle"
    assert moods.active("chat-b") is None
    assert details.active("chat-b") is None
    assert MoodGradeRepository(store).active("chat-a").id == "amber-noir"  # type: ignore[union-attr]
    assert DetailAccentRepository(store).active("chat-a").id == "glove-buckle"  # type: ignore[union-attr]
    assert anti.config("chat-a").enabled is True


def test_director_can_rotate_only_mood_and_detail(tmp_path) -> None:
    (
        _store,
        _looks,
        _variety,
        _arcs,
        _mixer,
        _motifs,
        moods,
        details,
        _anti,
        repository,
        director,
        _recipes,
        _manager,
    ) = _stack(tmp_path)
    repository.set_config(
        "chat-a",
        CreativeDirectorConfig(
            lock_look=True,
            lock_variety=True,
            lock_arc=True,
            lock_scene_mix=True,
            lock_visual_motif=True,
        ),
    )

    result = director.apply("chat-a", rng=random.Random(9))

    assert result.changed == ["mood_grade", "detail_accent"]
    assert result.mood_grade is not None
    assert result.detail_accent is not None
    assert moods.active("chat-a") is not None
    assert details.active("chat-a") is not None


def test_recipe_capture_roundtrips_mood_and_detail(tmp_path) -> None:
    (
        _store,
        _looks,
        _variety,
        _arcs,
        _mixer,
        _motifs,
        moods,
        details,
        _anti,
        _director_repo,
        _director,
        recipes,
        manager,
    ) = _stack(tmp_path)
    moods.set_active("chat-a", "soft-film")
    details.set_active("chat-a", "mirror-trace")

    recipe = manager.capture_current("chat-a", name="Soft mirror")
    moods.set_active("chat-a", "cool-steel")
    details.set_active("chat-a", "metal-accent")

    manager.apply("chat-a", recipe.id)

    assert moods.active("chat-a").id == "soft-film"  # type: ignore[union-attr]
    assert details.active("chat-a").id == "mirror-trace"  # type: ignore[union-attr]
    assert recipes.last_applied("chat-a").id == recipe.id  # type: ignore[union-attr]


def test_anti_repetition_detects_repeated_opening_and_staging(tmp_path) -> None:
    *_, anti, _repo, _director, _recipes, _manager = _stack(tmp_path)
    signature = "look:noir|mood:amber|detail:glove"
    anti.record_reply("chat-a", "You hold my gaze and wait.", signature)
    anti.record_reply("chat-a", "You hold my gaze and shift slightly.", signature)

    guidance = anti.guidance("chat-a", signature)

    assert "opening patterns" in guidance
    assert "creative combination" in guidance
    assert anti.guidance("chat-b", signature) == ""

    anti.set_config("chat-a", AntiRepetitionConfig(enabled=False))
    assert anti.guidance("chat-a", signature) == ""


def test_context_snapshot_contains_accents_and_repetition_guidance(tmp_path) -> None:
    store, *_, moods, details, anti, _repo, _director, _recipes, _manager = _stack(tmp_path)
    mood = moods.set_active("chat-a", "silver-monochrome")
    detail = details.set_active("chat-a", "hand-prop")
    anti.record_reply("chat-a", "Same opening words keep returning here.", "sig")
    anti.record_reply("chat-a", "Same opening words keep returning again.", "sig")
    guidance = anti.guidance("chat-a", "sig")

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(),
        persona=PersonaState(),
        preference_tags=[],
        mood_grade=mood,
        detail_accent=detail,
        anti_repetition_context=guidance,
        anti_repetition_enabled=True,
    )

    assert snapshot.mood_grade_name == "Silver Monochrome"
    assert snapshot.detail_accent_name == "Hand Prop"
    assert snapshot.anti_repetition_enabled is True
    assert "Silver Monochrome" in snapshot.system_prompt
    assert "Hand Prop" in snapshot.system_prompt
    assert "Anti-repetition guidance" in snapshot.system_prompt
