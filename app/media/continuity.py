from __future__ import annotations

import random

from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    """Persistent visual identity hints for one recurring generated character."""

    key: str
    seed: int = Field(ge=1, lt=2**63)
    appearance_prompt: str = (
        "same clearly adult companion character, consistent face, consistent hair, "
        "consistent body proportions, recognizable identity across images"
    )
    generation_count: int = Field(default=0, ge=0)
    positive_feedback: int = Field(default=0, ge=0)
    negative_feedback: int = Field(default=0, ge=0)
    last_media_path: str | None = None

    @classmethod
    def create(cls, key: str) -> "CharacterProfile":
        return cls(
            key=key.strip() or "persona-main",
            seed=random.SystemRandom().randrange(1, 2**63 - 1),
        )

    def register_generation(self, path: str) -> None:
        self.generation_count += 1
        self.last_media_path = path

    def register_feedback(self, feedback: str) -> None:
        if feedback == "positive":
            self.positive_feedback += 1
        elif feedback == "negative":
            self.negative_feedback += 1
        else:
            raise ValueError(f"Unsupported media feedback: {feedback}")
