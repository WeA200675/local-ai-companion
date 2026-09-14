from __future__ import annotations

from app.ai.learning import BehaviorLearner
from app.ai.persona import PersonaState


class FakeModel:
    def chat_json(self, *args, **kwargs):
        return {
            "dominance": 0.5,
            "strictness": 0.8,
            "teasing": 0.0,
            "initiative": 0.0,
            "persistence": 0.0,
            "creativity": 0.0,
            "autonomy": 0.0,
            "rationale": "reinforce dominant tone",
        }


def test_learning_respects_locks_and_is_one_revision() -> None:
    persona = PersonaState()
    persona.strictness.locked = True
    before_dominance = persona.dominance.current
    before_strictness = persona.strictness.current
    before_revision = persona.revision

    learner = BehaviorLearner(FakeModel())  # type: ignore[arg-type]
    result = learner.apply(
        user_text="good",
        assistant_text="reply",
        feedback="positive",
        persona=persona,
    )

    assert result.persona.dominance.current > before_dominance
    assert result.persona.strictness.current == before_strictness
    assert result.persona.revision == before_revision + 1
    assert result.rationale == "reinforce dominant tone"
