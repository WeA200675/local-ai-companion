from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class MediaIntent(BaseModel):
    generate: bool = False
    kind: Literal["image", "gif", "video"] = "image"
    mood: str = "neutral"
    theme: str = ""
    visual_style: str = "cinematic"
    wardrobe: list[str] = Field(default_factory=list)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    continuity_key: str | None = None
    reason: str = ""


class MediaPlanner:
    """Model-agnostic planning layer for local media generation backends."""

    def from_model_payload(self, payload: dict) -> MediaIntent:
        return MediaIntent.model_validate(payload)
