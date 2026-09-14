from __future__ import annotations

import random
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class VarietyCard(BaseModel):
    """Temporary creative overlay used to keep sessions from feeling repetitive."""

    id: str
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(default="mix", max_length=40)
    instruction: str = Field(min_length=1, max_length=700)
    style_tags: list[str] = Field(default_factory=list, max_length=16)
    enabled: bool = True
    builtin: bool = False

    @field_validator("name", "category", "instruction", mode="before")
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


class VarietyState(BaseModel):
    cards: list[VarietyCard] = Field(default_factory=list)
    active_by_conversation: dict[str, str] = Field(default_factory=dict)
    recent_ids: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)


def default_variety_cards() -> list[VarietyCard]:
    """Built-in neutral/adult-companion prompts that change pacing and atmosphere."""

    return [
        VarietyCard(
            id="slow-burn",
            name="Slow Burn",
            category="Atmosphäre",
            instruction=(
                "Let the exchange breathe. Build atmosphere gradually, use vivid but concise sensory "
                "detail, and avoid rushing toward a conclusion."
            ),
            style_tags=["slow burn", "atmospheric", "cinematic"],
            builtin=True,
        ),
        VarietyCard(
            id="playful-spark",
            name="Verspielter Funke",
            category="Dialog",
            instruction=(
                "Use playful wit, light challenge, and shorter back-and-forth beats. Keep the response "
                "interactive rather than turning it into a monologue."
            ),
            style_tags=["playful", "witty", "interactive"],
            builtin=True,
        ),
        VarietyCard(
            id="confident-presence",
            name="Starke Präsenz",
            category="Dynamik",
            instruction=(
                "Lean into a confident, composed presence with clear initiative while staying responsive "
                "to the user's current direction and boundaries."
            ),
            style_tags=["confident", "controlled", "focused"],
            builtin=True,
        ),
        VarietyCard(
            id="visual-frame",
            name="Visueller Fokus",
            category="Visuell",
            instruction=(
                "Think in striking visual frames: lighting, posture, wardrobe, environment, and camera-like "
                "composition. Prefer concrete imagery over abstract explanation."
            ),
            style_tags=["visual", "cinematic", "composition"],
            builtin=True,
        ),
        VarietyCard(
            id="dialogue-closeup",
            name="Dialog-Nahaufnahme",
            category="Dialog",
            instruction=(
                "Favor dialogue and immediate reactions. Keep narration lean and make each response invite "
                "a natural next move from the user."
            ),
            style_tags=["dialogue", "close-up", "responsive"],
            builtin=True,
        ),
        VarietyCard(
            id="mystery-beat",
            name="Geheimnisvoller Beat",
            category="Überraschung",
            instruction=(
                "Introduce a small unanswered detail, reveal, or unexpected shift that creates curiosity "
                "without contradicting established context."
            ),
            style_tags=["mysterious", "suspense", "unexpected"],
            builtin=True,
        ),
        VarietyCard(
            id="role-flip",
            name="Initiative wechseln",
            category="Dynamik",
            instruction=(
                "Change the usual conversational rhythm: invite the user to lead one beat, then take "
                "initiative on the next. Do not alter the learned base persona."
            ),
            style_tags=["dynamic", "role shift", "responsive"],
            builtin=True,
        ),
        VarietyCard(
            id="minimalist",
            name="Knapp & intensiv",
            category="Tempo",
            instruction=(
                "Use fewer words, stronger line breaks, and precise language. Make the exchange feel "
                "immediate without losing clarity or context."
            ),
            style_tags=["minimal", "intense", "precise"],
            builtin=True,
        ),
        VarietyCard(
            id="creative-detour",
            name="Kreativer Umweg",
            category="Überraschung",
            instruction=(
                "Offer one fresh angle that still fits the current conversation: a new framing, prop, "
                "location detail, or conversational game. Keep continuity intact."
            ),
            style_tags=["creative", "fresh angle", "variety"],
            builtin=True,
        ),
        VarietyCard(
            id="afterglow",
            name="Ruhiger Nachklang",
            category="Atmosphäre",
            instruction=(
                "Use a calmer, more intimate conversational pace focused on reflection, small details, "
                "and continuity with what just happened."
            ),
            style_tags=["calm", "intimate", "reflective"],
            builtin=True,
        ),
    ]


class VarietyRepository:
    STATE_KEY = "variety_deck"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(VarietyState(cards=default_variety_cards()))

    def load(self) -> VarietyState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return VarietyState(cards=default_variety_cards())
        try:
            state = VarietyState.model_validate_json(payload)
        except ValueError:
            return VarietyState(cards=default_variety_cards())
        if not state.cards:
            state.cards = default_variety_cards()
        valid_ids = {card.id for card in state.cards}
        state.active_by_conversation = {
            key: value
            for key, value in state.active_by_conversation.items()
            if value in valid_ids
        }
        state.recent_ids = [item for item in state.recent_ids if item in valid_ids][-8:]
        return state

    def save(self, state: VarietyState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_cards(self, *, enabled_only: bool = False) -> list[VarietyCard]:
        cards = self.load().cards
        if enabled_only:
            cards = [card for card in cards if card.enabled]
        return sorted(
            (card.model_copy(deep=True) for card in cards),
            key=lambda card: (card.category.casefold(), card.name.casefold()),
        )

    def get(self, card_id: str) -> VarietyCard | None:
        clean = card_id.strip()
        for card in self.load().cards:
            if card.id == clean:
                return card.model_copy(deep=True)
        return None

    def active(self, conversation_id: str) -> VarietyCard | None:
        state = self.load()
        card_id = state.active_by_conversation.get(conversation_id)
        if not card_id:
            return None
        return next(
            (card.model_copy(deep=True) for card in state.cards if card.id == card_id and card.enabled),
            None,
        )

    def set_active(self, conversation_id: str, card_id: str | None) -> VarietyCard | None:
        state = self.load()
        if not card_id:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
            return None
        card = next((item for item in state.cards if item.id == card_id and item.enabled), None)
        if card is None:
            raise KeyError(f"Variety card {card_id!r} not found or disabled")
        state.active_by_conversation[conversation_id] = card.id
        state.recent_ids = [item for item in state.recent_ids if item != card.id]
        state.recent_ids.append(card.id)
        state.recent_ids = state.recent_ids[-8:]
        state.revision += 1
        self.save(state)
        return card.model_copy(deep=True)

    def draw(
        self,
        conversation_id: str,
        *,
        category: str | None = None,
        rng: random.Random | None = None,
    ) -> VarietyCard:
        state = self.load()
        category_key = (category or "").strip().casefold()
        pool = [
            card
            for card in state.cards
            if card.enabled and (not category_key or card.category.casefold() == category_key)
        ]
        if not pool:
            raise ValueError("No enabled variety cards match this category")

        recent = set(state.recent_ids[-4:])
        fresh = [card for card in pool if card.id not in recent]
        candidates = fresh or pool
        chooser = rng or random.SystemRandom()
        selected = chooser.choice(candidates)
        result = self.set_active(conversation_id, selected.id)
        assert result is not None
        return result

    def upsert_custom(
        self,
        *,
        card_id: str | None,
        name: str,
        category: str,
        instruction: str,
        style_tags: list[str],
        enabled: bool = True,
    ) -> VarietyCard:
        state = self.load()
        clean_id = (card_id or "").strip()
        existing = next((card for card in state.cards if card.id == clean_id), None)
        if existing is not None and existing.builtin:
            raise ValueError("Built-in variety cards are not edited through the custom-card editor")
        card = VarietyCard(
            id=clean_id or f"custom-{uuid4().hex[:10]}",
            name=name,
            category=category or "Eigene",
            instruction=instruction,
            style_tags=style_tags,
            enabled=enabled,
            builtin=False,
        )
        state.cards = [card if item.id == card.id else item for item in state.cards]
        if all(item.id != card.id for item in state.cards):
            state.cards.append(card)
        state.revision += 1
        self.save(state)
        return card.model_copy(deep=True)

    def delete_custom(self, card_id: str) -> bool:
        state = self.load()
        target = next((card for card in state.cards if card.id == card_id), None)
        if target is None:
            return False
        if target.builtin:
            raise ValueError("Built-in variety cards cannot be deleted")
        state.cards = [card for card in state.cards if card.id != card_id]
        state.active_by_conversation = {
            key: value for key, value in state.active_by_conversation.items() if value != card_id
        }
        state.recent_ids = [item for item in state.recent_ids if item != card_id]
        state.revision += 1
        self.save(state)
        return True
