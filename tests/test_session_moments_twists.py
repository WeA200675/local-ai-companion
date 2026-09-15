from __future__ import annotations

import random

from app.ai.persona import PersonaState
from app.ai.twist_deck import TwistConfig, TwistDeckRepository
from app.context_inspector import build_context_snapshot
from app.memory.conversations import ConversationRepository
from app.memory.database import make_session_factory
from app.memory.session_moments import SessionMomentRepository
from app.memory.store import StateStore
from app.settings import AppSettings


def _stack(tmp_path):
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    conversations = ConversationRepository(store)
    moments = SessionMomentRepository(store, conversations)
    twists = TwistDeckRepository(store)
    return store, conversations, moments, twists


def test_session_moment_captures_latest_exchange_and_stays_conversation_scoped(tmp_path) -> None:
    store, conversations, moments, _twists = _stack(tmp_path)
    conversation_id = conversations.active_id()
    conversations.append_message("user", "Keep the rain-lit room exactly like this.")
    conversations.append_message("assistant", "I stay by the window and keep the frame quiet.")

    moment = moments.capture_latest(
        conversation_id,
        title="Rain window",
        note="Return to the quiet window composition",
    )
    active = moments.set_active(conversation_id, moment.id)

    assert active is not None
    assert active.title == "Rain window"
    assert "earlier user excerpt" in active.prompt_text()
    assert moments.active(conversation_id).id == moment.id  # type: ignore[union-attr]

    other = conversations.create("Other", activate=False)
    assert moments.active(other.id) is None
    assert moments.list_moments(other.id) == []
    assert SessionMomentRepository(store, conversations).active(conversation_id).id == moment.id  # type: ignore[union-attr]


def test_session_moment_requires_complete_exchange(tmp_path) -> None:
    _store, conversations, moments, _twists = _stack(tmp_path)
    conversation_id = conversations.active_id()
    conversations.append_message("user", "Only half an exchange exists.")

    try:
        moments.capture_latest(conversation_id, title="Incomplete")
    except ValueError as exc:
        assert "complete user/assistant exchange" in str(exc)
    else:
        raise AssertionError("Expected incomplete exchanges to be rejected")


def test_twist_auto_schedule_respects_interval_and_is_conversation_scoped(tmp_path) -> None:
    _store, conversations, _moments, twists = _stack(tmp_path)
    conversation_id = conversations.active_id()
    twists.set_config(conversation_id, TwistConfig(enabled=True, interval=2))

    assert twists.maybe_schedule(
        conversation_id,
        assistant_count=1,
        rng=random.Random(3),
    ) is None
    first = twists.maybe_schedule(
        conversation_id,
        assistant_count=2,
        rng=random.Random(3),
    )
    assert first is not None
    assert twists.active(conversation_id).id == first.id  # type: ignore[union-attr]

    other = conversations.create("Other", activate=False)
    assert twists.active(other.id) is None
    assert twists.config(other.id).enabled is False

    twists.clear(conversation_id)
    assert twists.maybe_schedule(
        conversation_id,
        assistant_count=3,
        rng=random.Random(4),
    ) is None
    second = twists.maybe_schedule(
        conversation_id,
        assistant_count=4,
        rng=random.Random(4),
    )
    assert second is not None
    assert second.id != first.id


def test_context_snapshot_exposes_saved_moment_and_one_shot_twist(tmp_path) -> None:
    store, conversations, moments, twists = _stack(tmp_path)
    conversation_id = conversations.active_id()
    conversations.append_message("user", "Remember this composition for later.")
    conversations.append_message("assistant", "A silver reflection crosses the dark window.")
    moment = moments.capture_latest(conversation_id, title="Silver window")
    moments.set_active(conversation_id, moment.id)
    twist = twists.set_active(conversation_id, "camera-cut")
    assert twist is not None
    twists.set_config(conversation_id, TwistConfig(enabled=True, interval=6))

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(),
        persona=PersonaState(),
        preference_tags=[],
        session_moment=moment,
        twist_card=twist,
        twist_auto_enabled=True,
        twist_interval=6,
        conversations=conversations,
    )

    assert snapshot.session_moment_name == "Silver window"
    assert snapshot.twist_name == "Kamera-Cut"
    assert snapshot.twist_auto_enabled is True
    assert snapshot.twist_interval == 6
    assert "Saved moment: Silver window" in snapshot.system_prompt
    assert "Kamera-Cut" in snapshot.system_prompt
    assert "one-shot twist" in snapshot.system_prompt.lower()
    assert "new angle" in snapshot.effective_tags
