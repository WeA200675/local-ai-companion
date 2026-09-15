from __future__ import annotations

from app.ai.creative_accents import DetailAccentRepository, MoodGradeRepository
from app.ai.creative_director import CreativeDirectorRepository
from app.ai.look_presets import LookPresetRepository
from app.ai.scenario_seeds import ScenarioSeedEngine, ScenarioSeedRepository
from app.ai.scene_evolution import RitualRepository, SceneEvolutionRepository
from app.ai.scene_mixer import SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.ai.storyboard_journeys import (
    StoryboardJourneyEngine,
    StoryboardJourneyRepository,
    default_storyboard_journeys,
)
from app.ai.variety import VarietyRepository
from app.ai.visual_motifs import VisualMotifRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _engines(tmp_path):
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
    director = CreativeDirectorRepository(store)
    seed_repo = ScenarioSeedRepository(store)
    seed_engine = ScenarioSeedEngine(
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
        director,
    )
    journey_repo = StoryboardJourneyRepository(store)
    journey_engine = StoryboardJourneyEngine(journey_repo, seed_engine)
    return (
        journey_engine,
        journey_repo,
        seed_engine,
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
    )


def test_builtin_journeys_reference_existing_scenario_templates(tmp_path) -> None:
    journey_engine, _, seed_engine, *_ = _engines(tmp_path)
    scenario_ids = {item.id for item in seed_engine.templates()}

    journeys = default_storyboard_journeys()
    assert len(journeys) >= 5
    assert {item.id for item in journey_engine.journeys()} == {item.id for item in journeys}
    for journey in journeys:
        assert 2 <= len(journey.chapters) <= 8
        for chapter in journey.chapters:
            assert chapter.scenario_template_id in scenario_ids


def test_start_and_manual_advance_apply_coherent_chapter_seeds(tmp_path) -> None:
    journey_engine, journey_repo, _, seed_repo, *_ = _engines(tmp_path)

    active = journey_engine.start(
        "chat-a",
        "rain-to-dawn",
        seed=100,
        assistant_count=4,
        automatic=False,
    )

    assert active.chapter_index == 0
    assert active.chapter_name == "Rain Arrival"
    assert active.scenario_template_id == "rain-noir"
    assert active.random_seed == 100
    assert active.last_turn == 4
    first_seed = seed_repo.active("chat-a")
    assert first_seed is not None
    assert first_seed.template_id == "rain-noir"
    assert "Rain to Dawn" in first_seed.layer_summary["Journey"]

    advanced = journey_engine.advance("chat-a", assistant_count=7)
    assert advanced is not None
    assert advanced.chapter_index == 1
    assert advanced.scenario_template_id == "mirror-mystery"
    assert advanced.last_turn == 7
    assert journey_repo.active("chat-a") == advanced
    second_seed = seed_repo.active("chat-a")
    assert second_seed is not None
    assert second_seed.template_id == "mirror-mystery"
    assert second_seed.random_seed != first_seed.random_seed


def test_automatic_progression_waits_for_reply_threshold_and_finishes_without_restore(tmp_path) -> None:
    journey_engine, journey_repo, _, seed_repo, looks, *_ = _engines(tmp_path)

    active = journey_engine.start(
        "chat-a",
        "cinematic-presence",
        seed=9,
        automatic=True,
        replies_per_chapter=2,
        assistant_count=10,
    )
    assert active.chapter_index == 0
    first_look = looks.active("chat-a")
    assert first_look is not None

    assert journey_engine.maybe_advance("chat-a", assistant_count=11) is None
    moved = journey_engine.maybe_advance("chat-a", assistant_count=12)
    assert moved is not None
    assert moved.chapter_index == 1

    journey_engine.advance("chat-a", assistant_count=14)
    final = journey_engine.advance("chat-a", assistant_count=16)
    assert final is not None
    assert final.chapter_index == 3
    assert final.completed is False
    final_seed = seed_repo.active("chat-a")
    assert final_seed is not None

    completed = journey_engine.maybe_advance("chat-a", assistant_count=18)
    assert completed is not None
    assert completed.chapter_index == 3
    assert completed.completed is True
    assert completed.automatic is False
    assert seed_repo.active("chat-a") == final_seed
    assert journey_repo.active("chat-a") == completed


def test_restore_origin_recovers_pre_journey_layers_and_prior_seed_marker(tmp_path) -> None:
    (
        journey_engine,
        journey_repo,
        seed_engine,
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
    ) = _engines(tmp_path)

    looks.set_active("chat-a", "soft-lounge")
    variety.set_active("chat-a", "afterglow")
    arcs.activate("chat-a", "mystery-night")
    original_mix = mixer.draw("chat-a")
    motifs.set_active("chat-a", "playful-lean")
    moods.set_active("chat-a", "soft-film")
    details.set_active("chat-a", "velvet-drape")
    evolutions.start("chat-a", "night-deepens", automatic=True, interval=3, assistant_count=2)
    rituals.start("chat-a", "cooldown-close", automatic=True, interval=2, assistant_count=2)

    prior_marker = seed_engine.generate(
        "chat-a",
        template_id="soft-lounge",
        seed=55,
        assistant_count=2,
    )
    # The journey starts from the currently applied prior seed state. Capture it
    # so restoration should return to exactly that state while reinstating the marker.
    prior_look = looks.active("chat-a")
    prior_variety = variety.active("chat-a")
    prior_arc = arcs.active("chat-a")
    prior_mix = mixer.active("chat-a")
    prior_motif = motifs.active("chat-a")
    prior_mood = moods.active("chat-a")
    prior_detail = details.active("chat-a")
    prior_evolution = evolutions.active("chat-a")
    prior_ritual = rituals.active("chat-a")
    assert prior_mix is not None

    journey_engine.start(
        "chat-a",
        "studio-presence",
        seed=77,
        assistant_count=5,
    )
    journey_engine.advance("chat-a", assistant_count=8)
    assert journey_repo.active("chat-a") is not None

    assert journey_engine.restore_origin("chat-a") is True
    assert journey_repo.active("chat-a") is None
    restored_marker = seed_repo.active("chat-a")
    assert restored_marker is not None
    assert restored_marker.template_id == prior_marker.template_id
    assert restored_marker.random_seed == prior_marker.random_seed
    assert looks.active("chat-a").id == prior_look.id  # type: ignore[union-attr]
    assert variety.active("chat-a").id == prior_variety.id  # type: ignore[union-attr]
    assert arcs.active("chat-a").arc_id == prior_arc.arc_id  # type: ignore[union-attr]
    assert mixer.active("chat-a").component_ids == prior_mix.component_ids  # type: ignore[union-attr]
    assert motifs.active("chat-a").id == prior_motif.id  # type: ignore[union-attr]
    assert moods.active("chat-a").id == prior_mood.id  # type: ignore[union-attr]
    assert details.active("chat-a").id == prior_detail.id  # type: ignore[union-attr]
    assert evolutions.active("chat-a").plan_id == prior_evolution.plan_id  # type: ignore[union-attr]
    assert rituals.active("chat-a").ritual_id == prior_ritual.ritual_id  # type: ignore[union-attr]

    # The unrelated state that existed before the prior seed was created is not
    # what journey restore targets; the journey's origin is the state at journey start.
    assert original_mix is not None


def test_detach_keeps_current_layers_and_state_is_conversation_scoped(tmp_path) -> None:
    journey_engine, journey_repo, _, seed_repo, looks, *_ = _engines(tmp_path)

    journey_engine.start("chat-a", "velvet-afterhours", seed=13, assistant_count=0)
    current_seed = seed_repo.active("chat-a")
    current_look = looks.active("chat-a")
    assert current_seed is not None
    assert current_look is not None
    assert journey_repo.active("chat-b") is None

    journey_engine.detach("chat-a")

    assert journey_repo.active("chat-a") is None
    assert seed_repo.active("chat-a") == current_seed
    assert looks.active("chat-a") == current_look


def test_previous_is_reproducible_for_same_journey_seed(tmp_path) -> None:
    journey_engine, _, _, seed_repo, *_ = _engines(tmp_path)

    journey_engine.start("chat-a", "rain-to-dawn", seed=1234, automatic=False)
    first = seed_repo.active("chat-a")
    assert first is not None
    journey_engine.advance("chat-a", assistant_count=2)
    journey_engine.previous("chat-a", assistant_count=3)
    again = seed_repo.active("chat-a")
    assert again is not None

    assert again.template_id == first.template_id
    assert again.random_seed == first.random_seed
    assert again.selected_ids == first.selected_ids
    assert again.scene_component_ids == first.scene_component_ids
