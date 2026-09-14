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
    appearance_revision: int = Field(default=1, ge=1)
    generation_count: int = Field(default=0, ge=0)
    positive_feedback: int = Field(default=0, ge=0)
    negative_feedback: int = Field(default=0, ge=0)
    last_media_path: str | None = None
    reference_media_id: int | None = Field(default=None, ge=1)
    reference_media_path: str | None = None

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

    def set_appearance(self, prompt: str) -> bool:
        clean = " ".join(prompt.split())
        if not clean:
            raise ValueError("Appearance prompt must not be empty")
        if clean == self.appearance_prompt:
            return False
        self.appearance_prompt = clean
        self.appearance_revision += 1
        return True

    def rotate_seed(self) -> int:
        old = self.seed
        while True:
            new = random.SystemRandom().randrange(1, 2**63 - 1)
            if new != old:
                self.seed = new
                return new

    def set_reference(self, media_id: int, path: str) -> None:
        clean = path.strip()
        if media_id < 1 or not clean:
            raise ValueError("Reference media requires a valid id and local path")
        self.reference_media_id = media_id
        self.reference_media_path = clean

    def clear_reference(self) -> None:
        self.reference_media_id = None
        self.reference_media_path = None
