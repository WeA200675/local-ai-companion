from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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

    # Concrete visual-direction fields. They remain backend-neutral and are
    # intentionally optional so older/local planner payloads stay compatible.
    framing: str = "portrait"
    camera_angle: str = "eye level"
    lighting: str = "cinematic"
    composition: str = "balanced composition"
    motion: str = ""

    @field_validator(
        "mood",
        "theme",
        "visual_style",
        "reason",
        "framing",
        "camera_angle",
        "lighting",
        "composition",
        "motion",
        mode="before",
    )
    @classmethod
    def _clean_text(cls, value: object) -> str:
        return " ".join(str(value or "").split())[:500]

    @field_validator("wardrobe")
    @classmethod
    def _clean_wardrobe(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = " ".join(str(value).split())[:120]
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result[:16]


class MediaPlanner:
    """Model-agnostic planning layer for local media generation backends."""

    def from_model_payload(self, payload: dict) -> MediaIntent:
        return MediaIntent.model_validate(payload)
