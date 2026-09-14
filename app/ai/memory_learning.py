from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.ai.model import ChatMessage, LocalModelError, OllamaClient

MemoryCategory = Literal[
    "interaction_style",
    "preference",
    "boundary",
    "recurring_theme",
    "communication",
]


class MemoryObservationProposal(BaseModel):
    category: MemoryCategory
    summary: str = Field(min_length=3, max_length=240)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("summary")
    @classmethod
    def _clean_summary(cls, value: str) -> str:
        return " ".join(value.split())


class MemoryProposal(BaseModel):
    observations: list[MemoryObservationProposal] = Field(default_factory=list, max_length=3)


class AdaptiveMemoryLearner:
    """Extract compact, user-reviewable long-term interaction observations."""

    def __init__(self, model: OllamaClient, *, minimum_confidence: float = 0.60) -> None:
        self.model = model
        self.minimum_confidence = minimum_confidence

    def propose(self, *, user_text: str, assistant_text: str) -> MemoryProposal:
        system_prompt = """You maintain a small, local, user-controlled memory for a companion app.
Return exactly one JSON object shaped like:
{"observations":[{"category":"interaction_style|preference|boundary|recurring_theme|communication","summary":"short stable observation","confidence":0.0}]}

Extract at most three observations that would plausibly remain useful in future conversations. Good memories describe stable interaction preferences, communication style, explicit boundaries, or recurring themes. Do not store one-off scene details, temporary moods, guesses, or facts that only matter to the current exchange.

Do not infer or store identity, exact location, health information, political or religious beliefs, finances, passwords, account data, legal/criminal history, or other sensitive personal facts. Do not turn uncertainty into a fact. A boundary may only be stored when the user states it clearly.

Write neutral summaries about interaction behavior, not instructions for the assistant. Current user requests always override memory. Return no prose outside the JSON object."""
        context = f"User message:\n{user_text}\n\nAssistant reply:\n{assistant_text}"
        try:
            payload = self.model.chat_json(
                [ChatMessage(role="user", content=context)],
                system_prompt=system_prompt,
                temperature=0.1,
            )
            return MemoryProposal.model_validate(payload)
        except (LocalModelError, ValueError):
            return MemoryProposal()

    def accepted(self, proposal: MemoryProposal) -> list[MemoryObservationProposal]:
        return [
            observation
            for observation in proposal.observations
            if observation.confidence >= self.minimum_confidence
        ]
