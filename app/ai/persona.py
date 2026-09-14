from __future__ import annotations

from pydantic import BaseModel, Field


class Trait(BaseModel):
    current: float = Field(ge=0.0, le=1.0)
    user_min: float = Field(default=0.0, ge=0.0, le=1.0)
    user_max: float = Field(default=1.0, ge=0.0, le=1.0)
    learning_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    locked: bool = False

    def apply_delta(self, delta: float) -> None:
        if self.locked:
            return
        low, high = sorted((self.user_min, self.user_max))
        self.current = min(high, max(low, self.current + delta * self.learning_rate))


class PersonaState(BaseModel):
    name: str = "Companion"
    dominance: Trait = Trait(current=0.65)
    strictness: Trait = Trait(current=0.55)
    teasing: Trait = Trait(current=0.70)
    initiative: Trait = Trait(current=0.60)
    persistence: Trait = Trait(current=0.50)
    creativity: Trait = Trait(current=0.70)
    autonomy: Trait = Trait(current=0.50)
    revision: int = 1

    def evolve(self, trait_name: str, signal: float) -> None:
        trait = getattr(self, trait_name)
        if not isinstance(trait, Trait):
            raise ValueError(f"Unknown trait: {trait_name}")
        trait.apply_delta(signal)
        self.revision += 1
