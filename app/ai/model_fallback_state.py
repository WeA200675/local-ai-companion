from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore

_STATE_KEY = "model_fallback_policy"


class ModelFallbackPolicy(BaseModel):
    enabled: bool = False
    models: list[str] = Field(default_factory=list)

    @field_validator("models", mode="before")
    @classmethod
    def _normalize_models(cls, value: object) -> list[str]:
        if value is None:
            return []
        raw_items = value.split(",") if isinstance(value, str) else list(value)  # type: ignore[arg-type]
        result: list[str] = []
        seen: set[str] = set()
        for raw in raw_items:
            name = str(raw or "").strip()
            folded = name.casefold()
            if not name or folded in seen:
                continue
            seen.add(folded)
            result.append(name)
        return result


class ModelFallbackRepository:
    """Small local AppState repository for the explicit model fallback chain.

    The fallback policy intentionally lives outside AppSettings because the
    Settings form predates this feature and reconstructs AppSettings from its
    visible fields. Keeping the policy in its own state key prevents an unrelated
    settings save from accidentally clearing the user's explicit fallback choices.
    """

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> ModelFallbackPolicy:
        payload = self.store._load_app_state(_STATE_KEY)
        if payload is None:
            return ModelFallbackPolicy()
        try:
            return ModelFallbackPolicy.model_validate_json(payload)
        except ValueError:
            return ModelFallbackPolicy()

    def save(self, policy: ModelFallbackPolicy) -> ModelFallbackPolicy:
        normalized = ModelFallbackPolicy.model_validate(policy.model_dump(mode="python"))
        if not normalized.models:
            normalized.enabled = False
        self.store._save_app_state(_STATE_KEY, normalized.model_dump_json())
        return normalized
