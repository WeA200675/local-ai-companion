from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.ai.persona import PersonaState, Trait

TRAIT_NAMES = (
    "dominance",
    "strictness",
    "teasing",
    "initiative",
    "persistence",
    "creativity",
    "autonomy",
)


class SessionMode(BaseModel):
    """Temporary persona overlay that never mutates the learned base persona."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    trait_offsets: dict[str, float] = Field(default_factory=dict)
    style_tags: list[str] = Field(default_factory=list)

    @field_validator("id", "name", "description", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("trait_offsets")
    @classmethod
    def _validate_offsets(cls, value: dict[str, float]) -> dict[str, float]:
        clean: dict[str, float] = {}
        for name, offset in value.items():
            if name not in TRAIT_NAMES:
                continue
            clean[name] = min(0.5, max(-0.5, float(offset)))
        return clean

    @field_validator("style_tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))[:24]

    def apply(self, persona: PersonaState) -> PersonaState:
        effective = persona.model_copy(deep=True)
        for name, offset in self.trait_offsets.items():
            trait = getattr(effective, name, None)
            if not isinstance(trait, Trait) or trait.locked:
                continue
            low, high = sorted((trait.user_min, trait.user_max))
            trait.current = min(high, max(low, trait.current + offset))
        return effective

    def merged_tags(self, base_tags: list[str]) -> list[str]:
        return list(dict.fromkeys([*base_tags, *self.style_tags]))


class SessionModeState(BaseModel):
    modes: list[SessionMode] = Field(default_factory=list)
    active_id: str | None = None

    def active_mode(self) -> SessionMode | None:
        if not self.active_id:
            return None
        return next((mode for mode in self.modes if mode.id == self.active_id), None)


def default_session_modes() -> list[SessionMode]:
    return [
        SessionMode(
            id="strict-focus",
            name="Streng & fokussiert",
            description="Temporär direkter, konsequenter und initiativer, ohne die gelernte Basis zu verändern.",
            trait_offsets={"dominance": 0.15, "strictness": 0.20, "initiative": 0.10},
            style_tags=["controlled", "precise"],
        ),
        SessionMode(
            id="playful-tease",
            name="Verspielt & neckisch",
            description="Temporär mehr spielerische Energie und Kreativität.",
            trait_offsets={"teasing": 0.20, "creativity": 0.10, "strictness": -0.10},
            style_tags=["playful", "teasing"],
        ),
        SessionMode(
            id="creative-scene",
            name="Kreativ & atmosphärisch",
            description="Temporär stärker auf Atmosphäre, Variation und visuelle Ideen ausgerichtet.",
            trait_offsets={"creativity": 0.25, "autonomy": 0.10, "initiative": 0.05},
            style_tags=["cinematic", "atmospheric", "creative"],
        ),
    ]
