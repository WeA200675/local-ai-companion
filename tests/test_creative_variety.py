from __future__ import annotations

import random

from app.ai.look_presets import LookPresetRepository
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.ai.scene_mixer import SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.context_inspector import build_context_snapshot
from app.memory.conversations import ConversationRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _store(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    return StateStore(factory)


def test_look_presets_are_conversation_scoped(tmp_path) -> None:
    store = _store(tmp_path)
    conversations = ConversationRepository(store)
    first = conversations.active_id()
    second = conversations.create("Alternative", activate=False).id
    looks = LookPresetRepository(store)

    selected = looks.set_active(first, "noir-latex")

    assert selected is not None
    assert selected.name == "Noir Latex"
    assert looks.active(first) is not None
    assert looks.active(second) is None

    looks.set_active(first, None)
    assert looks.active(first) is None


def test_session_arc_advances_and_finishes_without_touching_other_conversation(tmp_path) -> None:
    store = _store(tmp_path)
    conversations = ConversationRepository(store)
    first = conversations.active_id()
    second = conversations.create("Alternative", activate=False).id
    arcs = SessionArcRepository(store)

    active = arcs.activate(first, "mystery-night")
    assert active.stage_index == 0
    assert active.stage_count == 3
    assert arcs.active(second) is None

    active = arcs.advance(first)
    assert active is not None and active.stage_index == 1
    active = arcs.advance(first)
    assert active is not None and active.stage_index == 2
    assert arcs.advance(first) is None
    assert arcs.active(first) is None


def test_scene_mixer_is_local_persistent_and_scoped(tmp_path) -> None:
    store = _store(tmp_path)
    conversations = ConversationRepository(store)
    first = conversations.active_id()
    second = conversations.create("Alternative", activate=False).id
    mixer = SceneMixerRepository(store)

    mix = mixer.draw(first, rng=random.Random(7))

    assert mix.signature
    assert len(mix.components) == 4
    assert mixer.active(first) == mix
    assert mixer.active(second) is None

    mixer.clear(first)
    assert mixer.active(first) is None


def test_prompt_and_context_inspector_include_all_creative_overlays(tmp_path) -> None:
    store = _store(tmp_path)
    conversations = ConversationRepository(store)
    conversation_id = conversations.active_id()
    conversations.append_message("user", "Keep the scene visually coherent.", conversation_id=conversation_id)

    looks = LookPresetRepository(store)
    arcs = SessionArcRepository(store)
    mixer = SceneMixerRepository(store)
    look = looks.set_active(conversation_id, "leather-command")
    arc = arcs.activate(conversation_id, "cinematic-sequence")
    mix = mixer.draw(conversation_id, rng=random.Random(3))
    assert look is not None

    prompt = build_system_prompt(
        PersonaState(),
        look_context=look.prompt_text(),
        arc_context=arc.prompt_text(),
        scene_mix_context=mix.prompt_text(),
    )
    assert "Leather Command" in prompt
    assert "Cinematic Sequence" in prompt
    assert mix.title in prompt
    assert "stable character identity" in prompt

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(),
        persona=PersonaState(),
        preference_tags=[],
        look_preset=look,
        active_arc=arc,
        scene_mix=mix,
        conversations=conversations,
    )
    assert snapshot.look_name == "Leather Command"
    assert snapshot.arc_name == "Cinematic Sequence"
    assert snapshot.arc_stage == "Establishing"
    assert snapshot.scene_mix_name == mix.title
    assert "leather" in snapshot.effective_tags
    assert len(snapshot.history) == 1
