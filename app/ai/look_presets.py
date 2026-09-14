from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class LookPreset(BaseModel):
    """Temporary visual identity overlay; never mutates the stable character profile."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    wardrobe: list[str] = Field(default_factory=list, max_length=12)
    style_tags: list[str] = Field(default_factory=list, max_length=20)
    builtin: bool = False

    @field_validator("id", "name", "description", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        return " ".join(str(value or "").split())

    @field_validator("wardrobe", "style_tags")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = " ".join(value.split())[:80]
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    def prompt_text(self) -> str:
        wardrobe = ", ".join(self.wardrobe) if self.wardrobe else "unspecified wardrobe"
        detail = f" — {self.description}" if self.description else ""
        return f"{self.name}: {wardrobe}{detail}"


class LookPresetState(BaseModel):
    presets: list[LookPreset] = Field(default_factory=list)
    active_by_conversation: dict[str, str] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_look_presets() -> list[LookPreset]:
    return [
        LookPreset(
            id="noir-latex",
            name="Noir Latex",
            description="Glossy monochrome styling with a controlled, cinematic silhouette.",
            wardrobe=["black latex outfit", "minimal accessories"],
            style_tags=["latex", "black", "glossy", "cinematic", "controlled"],
            builtin=True,
        ),
        LookPreset(
            id="leather-command",
            name="Leather Command",
            description="Structured leather styling with a confident, composed presence.",
            wardrobe=["black leather outfit", "boots"],
            style_tags=["leather", "structured", "confident", "dark fashion"],
            builtin=True,
        ),
        LookPreset(
            id="elegant-monochrome",
            name="Elegant Monochrome",
            description="Clean evening styling with strong lines and restrained detail.",
            wardrobe=["monochrome evening outfit", "simple jewelry"],
            style_tags=["elegant", "monochrome", "minimal", "editorial"],
            builtin=True,
        ),
        LookPreset(
            id="soft-lounge",
            name="Soft Lounge",
            description="Relaxed private-lounge styling with softer fabrics and warmer framing.",
            wardrobe=["soft lounge outfit", "barefoot styling"],
            style_tags=["soft fabric", "relaxed", "warm", "intimate portrait"],
            builtin=True,
        ),
        LookPreset(
            id="studio-minimal",
            name="Studio Minimal",
            description="Simple fitted styling intended to keep attention on face, posture, and lighting.",
            wardrobe=["minimal fitted outfit"],
            style_tags=["studio", "minimal", "clean lines", "portrait"],
            builtin=True,
        ),
        LookPreset(
            id="retro-glam",
            name="Retro Glam",
            description="Vintage-inspired glamour with polished hair, bold contrast, and editorial framing.",
            wardrobe=["retro-inspired dress", "statement heels"],
            style_tags=["retro", "glamour", "editorial", "high contrast"],
            builtin=True,
        ),
        LookPreset(
            id="rainy-noir",
            name="Rainy Noir",
            description="Dark coat-and-boots styling designed for reflective, rain-lit scenes.",
            wardrobe=["dark long coat", "boots"],
            style_tags=["noir", "rain", "reflections", "moody", "cinematic"],
            builtin=True,
        ),
    ]


class LookPresetRepository:
    STATE_KEY = "look_presets"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(LookPresetState(presets=default_look_presets()))

    def load(self) -> LookPresetState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return LookPresetState(presets=default_look_presets())
        try:
            state = LookPresetState.model_validate_json(payload)
        except ValueError:
            return LookPresetState(presets=default_look_presets())
        if not state.presets:
            state.presets = default_look_presets()
        valid_ids = {preset.id for preset in state.presets}
        state.active_by_conversation = {
            key: value for key, value in state.active_by_conversation.items() if value in valid_ids
        }
        return state

    def save(self, state: LookPresetState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_presets(self) -> list[LookPreset]:
        return [preset.model_copy(deep=True) for preset in self.load().presets]

    def get(self, preset_id: str) -> LookPreset | None:
        clean = preset_id.strip()
        return next(
            (preset.model_copy(deep=True) for preset in self.load().presets if preset.id == clean),
            None,
        )

    def active(self, conversation_id: str) -> LookPreset | None:
        state = self.load()
        preset_id = state.active_by_conversation.get(conversation_id)
        if not preset_id:
            return None
        return next(
            (preset.model_copy(deep=True) for preset in state.presets if preset.id == preset_id),
            None,
        )

    def set_active(self, conversation_id: str, preset_id: str | None) -> LookPreset | None:
        state = self.load()
        if not preset_id:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
            return None
        preset = next((item for item in state.presets if item.id == preset_id), None)
        if preset is None:
            raise KeyError(f"Look preset {preset_id!r} not found")
        state.active_by_conversation[conversation_id] = preset.id
        state.revision += 1
        self.save(state)
        return preset.model_copy(deep=True)
