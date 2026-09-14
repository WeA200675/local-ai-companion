from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.model import ChatMessage, LocalModelError, OllamaClient
from app.ai.persona import PersonaState


TRAIT_NAMES = (
    "dominance",
    "strictness",
    "teasing",
    "initiative",
    "persistence",
    "creativity",
    "autonomy",
)

Feedback = Literal["positive", "negative"]


class LearningProposal(BaseModel):
    dominance: float = Field(default=0.0, ge=-1.0, le=1.0)
    strictness: float = Field(default=0.0, ge=-1.0, le=1.0)
    teasing: float = Field(default=0.0, ge=-1.0, le=1.0)
    initiative: float = Field(default=0.0, ge=-1.0, le=1.0)
    persistence: float = Field(default=0.0, ge=-1.0, le=1.0)
    creativity: float = Field(default=0.0, ge=-1.0, le=1.0)
    autonomy: float = Field(default=0.0, ge=-1.0, le=1.0)
    rationale: str = ""

    def deltas(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in TRAIT_NAMES}


@dataclass(frozen=True, slots=True)
class LearningResult:
    persona: PersonaState
    feedback: Feedback
    deltas: dict[str, float]
    rationale: str


class BehaviorLearner:
    """Feedback-driven learning layer around an otherwise static local LLM.

    The language model proposes bounded trait signals. The application owns the
    actual update and PersonaState applies each trait's user-defined learning
    rate, lock, and min/max bounds. This keeps learned behavior reversible and
    user-controlled.
    """

    def __init__(self, model: OllamaClient) -> None:
        self.model = model

    def propose(
        self,
        *,
        user_text: str,
        assistant_text: str,
        feedback: Feedback,
        persona: PersonaState,
    ) -> LearningProposal:
        system_prompt = """You are a behavior-learning analyzer for a local companion app.
Return exactly one JSON object with numeric keys dominance, strictness, teasing, initiative, persistence, creativity, autonomy, each between -1 and 1, plus a short rationale string.

The user explicitly rated the immediately preceding assistant response. Infer which personality traits were expressed in that response and propose small directional learning signals. Positive feedback should reinforce traits actually visible in the response. Negative feedback should reduce traits that plausibly caused the disliked response. Do not invent changes unrelated to the exchange. Prefer 0 for traits with weak evidence. Most non-zero values should be between -0.5 and 0.5.

These values are only proposals; application-side locks and limits are authoritative. Do not include prose outside the JSON object."""
        context = (
            f"Feedback: {feedback}\n"
            f"Current persona revision: {persona.revision}\n"
            f"Current trait values: "
            + ", ".join(
                f"{name}={getattr(persona, name).current:.2f}" for name in TRAIT_NAMES
            )
            + f"\n\nUser message:\n{user_text}\n\nAssistant reply:\n{assistant_text}"
        )
        payload = self.model.chat_json(
            [ChatMessage(role="user", content=context)],
            system_prompt=system_prompt,
            temperature=0.15,
        )
        return LearningProposal.model_validate(payload)

    def apply(
        self,
        *,
        user_text: str,
        assistant_text: str,
        feedback: Feedback,
        persona: PersonaState,
    ) -> LearningResult:
        before = persona.model_copy(deep=True)
        try:
            proposal = self.propose(
                user_text=user_text,
                assistant_text=assistant_text,
                feedback=feedback,
                persona=before,
            )
        except (LocalModelError, ValueError):
            proposal = LearningProposal(rationale="No learning update: analyzer failed")

        updated = before.model_copy(deep=True)
        deltas = proposal.deltas()
        changed = False
        for trait_name, signal in deltas.items():
            trait = getattr(updated, trait_name)
            old_value = trait.current
            trait.apply_delta(signal)
            changed = changed or trait.current != old_value
        if changed:
            updated.revision += 1

        return LearningResult(
            persona=updated,
            feedback=feedback,
            deltas=deltas,
            rationale=proposal.rationale.strip(),
        )
