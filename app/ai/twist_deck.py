from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore

TwistCategory = Literal["atmosphere", "camera", "dialogue", "detail", "setting"]


class TwistCard(BaseModel):
    """One-shot temporary creative event for the next companion response."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    category: TwistCategory = "atmosphere"
    instruction: str = Field(min_length=1, max_length=700)
    style_tags: list[str] = Field(default_factory=list, max_length=16)
    builtin: bool = True

    @field_validator("id", "name", "instruction", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        return " ".join(str(value or "").split())

    @field_validator("style_tags")
    @classmethod
    def _clean_tags(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = " ".join(value.split())[:80]
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result[:16]

    def prompt_text(self) -> str:
        return f"{self.name}: {self.instruction}"


class TwistConfig(BaseModel):
    enabled: bool = False
    interval: int = Field(default=5, ge=2, le=20)


class TwistDeckState(BaseModel):
    cards: list[TwistCard] = Field(default_factory=list)
    active_by_conversation: dict[str, str] = Field(default_factory=dict)
    config_by_conversation: dict[str, TwistConfig] = Field(default_factory=dict)
    last_turn_by_conversation: dict[str, int] = Field(default_factory=dict)
    recent_ids: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)


def default_twist_cards() -> list[TwistCard]:
    return [
        TwistCard(
            id="light-shift",
            name="Lichtwechsel",
            category="atmosphere",
            instruction=(
                "Introduce one subtle lighting change that alters the mood for this beat only, such as a "
                "lamp dimming, a brighter edge light, or moving reflections. Keep continuity intact."
            ),
            style_tags=["lighting shift", "mood change", "cinematic"],
        ),
        TwistCard(
            id="camera-cut",
            name="Kamera-Cut",
            category="camera",
            instruction=(
                "Reframe the moment with a noticeably different visual distance or angle for this beat. "
                "Avoid repeating the current framing and preserve character identity."
            ),
            style_tags=["reframed", "new angle", "visual variety"],
        ),
        TwistCard(
            id="small-prop",
            name="Neues Detail",
            category="detail",
            instruction=(
                "Introduce one small fitting prop, accessory, texture, or environmental detail that can be "
                "noticed or interacted with without taking over the scene."
            ),
            style_tags=["prop detail", "material detail", "environmental storytelling"],
        ),
        TwistCard(
            id="adjacent-space",
            name="Raumwechsel",
            category="setting",
            instruction=(
                "Open up an adjacent part of the established setting or shift to a nearby position in it. "
                "Treat this as a small spatial variation, not a continuity-breaking relocation."
            ),
            style_tags=["spatial shift", "environment", "continuity"],
        ),
        TwistCard(
            id="weather-beat",
            name="Wetter-Beat",
            category="atmosphere",
            instruction=(
                "Let weather or exterior ambience briefly become more noticeable through sound, glass, "
                "reflections, airflow, or changing light while keeping the scene grounded."
            ),
            style_tags=["weather ambience", "reflections", "atmospheric detail"],
        ),
        TwistCard(
            id="initiative-beat",
            name="Initiative-Beat",
            category="dialogue",
            instruction=(
                "Change the conversational rhythm for one beat: make a concise confident observation, offer "
                "a choice, or invite the user to lead the next move. Do not change the learned persona."
            ),
            style_tags=["dialogue beat", "rhythm change", "interactive"],
        ),
        TwistCard(
            id="reflection-clue",
            name="Spiegelhinweis",
            category="detail",
            instruction=(
                "Use a reflection, shadow, silhouette, or partial reveal to introduce one fresh visual clue "
                "or detail. Keep it suggestive and consistent with established context."
            ),
            style_tags=["reflection", "partial reveal", "visual clue"],
        ),
        TwistCard(
            id="quiet-choice",
            name="Kleine Wahl",
            category="dialogue",
            instruction=(
                "Offer one compact, in-scene choice between two fitting directions. Keep it optional and let "
                "the user's current message override the twist completely."
            ),
            style_tags=["choice", "interactive", "branching beat"],
        ),
    ]


class TwistDeckRepository:
    STATE_KEY = "twist_deck"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(TwistDeckState(cards=default_twist_cards()))

    def load(self) -> TwistDeckState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return TwistDeckState(cards=default_twist_cards())
        try:
            state = TwistDeckState.model_validate_json(payload)
        except ValueError:
            return TwistDeckState(cards=default_twist_cards())
        if not state.cards:
            state.cards = default_twist_cards()
        valid_ids = {card.id for card in state.cards}
        state.active_by_conversation = {
            key: value for key, value in state.active_by_conversation.items() if value in valid_ids
        }
        state.recent_ids = [item for item in state.recent_ids if item in valid_ids][-10:]
        return state

    def save(self, state: TwistDeckState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_cards(self) -> list[TwistCard]:
        return [card.model_copy(deep=True) for card in self.load().cards]

    def get(self, card_id: str) -> TwistCard | None:
        clean = card_id.strip()
        return next(
            (card.model_copy(deep=True) for card in self.load().cards if card.id == clean),
            None,
        )

    def config(self, conversation_id: str) -> TwistConfig:
        config = self.load().config_by_conversation.get(conversation_id)
        return (config or TwistConfig()).model_copy(deep=True)

    def set_config(self, conversation_id: str, config: TwistConfig) -> None:
        state = self.load()
        state.config_by_conversation[conversation_id] = config.model_copy(deep=True)
        state.revision += 1
        self.save(state)

    def active(self, conversation_id: str) -> TwistCard | None:
        state = self.load()
        card_id = state.active_by_conversation.get(conversation_id)
        if not card_id:
            return None
        return next(
            (card.model_copy(deep=True) for card in state.cards if card.id == card_id),
            None,
        )

    def set_active(self, conversation_id: str, card_id: str | None) -> TwistCard | None:
        state = self.load()
        if not card_id:
            if conversation_id in state.active_by_conversation:
                state.active_by_conversation.pop(conversation_id, None)
                state.revision += 1
                self.save(state)
            return None
        card = next((item for item in state.cards if item.id == card_id), None)
        if card is None:
            raise KeyError(f"Twist card {card_id!r} not found")
        state.active_by_conversation[conversation_id] = card.id
        state.recent_ids = [item for item in state.recent_ids if item != card.id]
        state.recent_ids.append(card.id)
        state.recent_ids = state.recent_ids[-10:]
        state.revision += 1
        self.save(state)
        return card.model_copy(deep=True)

    def clear(self, conversation_id: str) -> None:
        self.set_active(conversation_id, None)

    def draw(
        self,
        conversation_id: str,
        *,
        rng: random.Random | None = None,
    ) -> TwistCard:
        state = self.load()
        recent = set(state.recent_ids[-4:])
        fresh = [card for card in state.cards if card.id not in recent]
        pool = fresh or state.cards
        if not pool:
            raise ValueError("No twist cards are configured")
        chooser = rng or random.SystemRandom()
        selected = chooser.choice(pool)
        result = self.set_active(conversation_id, selected.id)
        assert result is not None
        return result

    def maybe_schedule(
        self,
        conversation_id: str,
        *,
        assistant_count: int,
        rng: random.Random | None = None,
    ) -> TwistCard | None:
        state = self.load()
        config = state.config_by_conversation.get(conversation_id, TwistConfig())
        if not config.enabled:
            return None
        if conversation_id in state.active_by_conversation:
            return self.active(conversation_id)
        last_turn = max(0, int(state.last_turn_by_conversation.get(conversation_id, 0)))
        if assistant_count - last_turn < config.interval:
            return None
        card = self.draw(conversation_id, rng=rng)
        state = self.load()
        state.last_turn_by_conversation[conversation_id] = max(0, int(assistant_count))
        state.revision += 1
        self.save(state)
        return card
