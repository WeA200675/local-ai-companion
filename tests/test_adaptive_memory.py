from __future__ import annotations

from app.ai.memory_learning import AdaptiveMemoryLearner
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.memory.database import make_session_factory
from app.memory.store import StateStore


class FakeMemoryModel:
    def chat_json(self, *args, **kwargs):
        return {
            "observations": [
                {
                    "category": "communication",
                    "summary": "User prefers concise replies with clear choices",
                    "confidence": 0.92,
                },
                {
                    "category": "recurring_theme",
                    "summary": "A one-off detail that is not stable",
                    "confidence": 0.20,
                },
            ]
        }


def test_adaptive_memory_filters_low_confidence() -> None:
    learner = AdaptiveMemoryLearner(FakeMemoryModel())  # type: ignore[arg-type]
    proposal = learner.propose(user_text="short please", assistant_text="okay")
    accepted = learner.accepted(proposal)

    assert len(accepted) == 1
    assert accepted[0].category == "communication"
    assert accepted[0].confidence == 0.92


def test_memory_store_dedupes_and_can_be_reversibly_disabled(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)

    first_id, first_changed = store.upsert_memory_observation(
        category="communication",
        summary="User prefers concise replies with clear choices",
        confidence=0.72,
    )
    second_id, second_changed = store.upsert_memory_observation(
        category="communication",
        summary="  user PREFERS concise replies   with clear choices  ",
        confidence=0.91,
    )

    assert first_id == second_id
    assert first_changed is True
    assert second_changed is True
    rows = store.list_memory_observations()
    assert len(rows) == 1
    assert rows[0]["source_count"] == 2
    assert rows[0]["confidence"] == 0.91
    assert store.list_active_memory_summaries() == [
        "User prefers concise replies with clear choices"
    ]

    store.set_memory_observation_active(first_id, False)
    assert store.list_active_memory_summaries() == []
    assert store.list_memory_observations()[0]["active"] is False

    store.set_memory_observation_active(first_id, True)
    assert store.list_active_memory_summaries()


def test_system_prompt_includes_memory_as_soft_context() -> None:
    prompt = build_system_prompt(
        PersonaState(),
        ["teasing"],
        ["User prefers concise replies with clear choices"],
    )

    assert "User prefers concise replies with clear choices" in prompt
    assert "fallible" in prompt
    assert "current message" in prompt
