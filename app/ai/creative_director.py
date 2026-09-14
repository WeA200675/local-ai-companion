from __future__ import annotations

import random
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

from app.ai.look_presets import LookPreset, LookPresetRepository
from app.ai.scene_mixer import SceneMix, SceneMixerRepository
from app.ai.session_arcs import ActiveArc, SessionArcRepository
from app.ai.variety import VarietyCard, VarietyRepository
from app.ai.visual_motifs import VisualMotif, VisualMotifRepository
from app.memory.store import StateStore

DirectorIntensity = Literal["gentle", "balanced", "wild"]
T = TypeVar("T")


class CreativeDirectorConfig(BaseModel):
    """User-controlled policy for temporary creative variation."""

    enabled: bool = False
    interval: int = Field(default=4, ge=2, le=20)
    intensity: DirectorIntensity = "balanced"
    lock_look: bool = False
    lock_variety: bool = False
    lock_arc: bool = False
    lock_scene_mix: bool = False
    lock_visual_motif: bool = False
    favorite_look_ids: list[str] = Field(default_factory=list)
    favorite_arc_ids: list[str] = Field(default_factory=list)
    favorite_visual_motif_ids: list[str] = Field(default_factory=list)


class CreativeDirectorState(BaseModel):
    config_by_conversation: dict[str, CreativeDirectorConfig] = Field(default_factory=dict)
    last_turn_by_conversation: dict[str, int] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


class CreativeDirectorResult(BaseModel):
    changed: list[str] = Field(default_factory=list)
    look: LookPreset | None = None
    variety: VarietyCard | None = None
    arc: ActiveArc | None = None
    scene_mix: SceneMix | None = None
    visual_motif: VisualMotif | None = None

    @property
    def changed_anything(self) -> bool:
        return bool(self.changed)


class CreativeDirectorRepository:
    STATE_KEY = "creative_director"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> CreativeDirectorState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return CreativeDirectorState()
        try:
            return CreativeDirectorState.model_validate_json(payload)
        except ValueError:
            return CreativeDirectorState()

    def save(self, state: CreativeDirectorState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def config(self, conversation_id: str) -> CreativeDirectorConfig:
        state = self.load()
        config = state.config_by_conversation.get(conversation_id)
        return (config or CreativeDirectorConfig()).model_copy(deep=True)

    def set_config(self, conversation_id: str, config: CreativeDirectorConfig) -> None:
        state = self.load()
        state.config_by_conversation[conversation_id] = config.model_copy(deep=True)
        state.revision += 1
        self.save(state)

    def last_turn(self, conversation_id: str) -> int:
        return max(0, int(self.load().last_turn_by_conversation.get(conversation_id, 0)))

    def mark_turn(self, conversation_id: str, assistant_count: int) -> None:
        state = self.load()
        state.last_turn_by_conversation[conversation_id] = max(0, int(assistant_count))
        state.revision += 1
        self.save(state)

    def set_favorite_look(self, conversation_id: str, preset_id: str, favorite: bool) -> None:
        config = self.config(conversation_id)
        values = [item for item in config.favorite_look_ids if item != preset_id]
        if favorite:
            values.append(preset_id)
        config.favorite_look_ids = values
        self.set_config(conversation_id, config)

    def set_favorite_arc(self, conversation_id: str, arc_id: str, favorite: bool) -> None:
        config = self.config(conversation_id)
        values = [item for item in config.favorite_arc_ids if item != arc_id]
        if favorite:
            values.append(arc_id)
        config.favorite_arc_ids = values
        self.set_config(conversation_id, config)

    def set_favorite_visual_motif(
        self,
        conversation_id: str,
        motif_id: str,
        favorite: bool,
    ) -> None:
        config = self.config(conversation_id)
        values = [item for item in config.favorite_visual_motif_ids if item != motif_id]
        if favorite:
            values.append(motif_id)
        config.favorite_visual_motif_ids = values
        self.set_config(conversation_id, config)


class CreativeDirector:
    """Rotate temporary creative layers without touching persona or memories.

    The director is deterministic under an injected ``random.Random`` which keeps
    tests reproducible. Automatic rotation is opt-in and bounded by per-conversation
    interval and locks.
    """

    def __init__(
        self,
        repository: CreativeDirectorRepository,
        looks: LookPresetRepository,
        arcs: SessionArcRepository,
        mixer: SceneMixerRepository,
        variety: VarietyRepository,
        motifs: VisualMotifRepository | None = None,
    ) -> None:
        self.repository = repository
        self.looks = looks
        self.arcs = arcs
        self.mixer = mixer
        self.variety = variety
        self.motifs = motifs

    @staticmethod
    def _choose(items: list[T], rng: random.Random | random.SystemRandom) -> T:
        if not items:
            raise ValueError("No creative options available")
        return rng.choice(items)

    def _draw_look(
        self,
        conversation_id: str,
        config: CreativeDirectorConfig,
        rng: random.Random | random.SystemRandom,
    ) -> LookPreset:
        presets = self.looks.list_presets()
        favorite_ids = set(config.favorite_look_ids)
        favorites = [item for item in presets if item.id in favorite_ids]
        pool = favorites or presets
        current = self.looks.active(conversation_id)
        alternatives = [item for item in pool if current is None or item.id != current.id]
        selected = self._choose(alternatives or pool, rng)
        result = self.looks.set_active(conversation_id, selected.id)
        assert result is not None
        return result

    def _draw_arc(
        self,
        conversation_id: str,
        config: CreativeDirectorConfig,
        rng: random.Random | random.SystemRandom,
        *,
        advance_existing: bool,
    ) -> ActiveArc:
        current = self.arcs.active(conversation_id)
        if current is not None and advance_existing:
            advanced = self.arcs.advance(conversation_id)
            if advanced is not None:
                return advanced

        arcs = self.arcs.list_arcs()
        favorite_ids = set(config.favorite_arc_ids)
        favorites = [item for item in arcs if item.id in favorite_ids]
        pool = favorites or arcs
        alternatives = [item for item in pool if current is None or item.id != current.arc_id]
        selected = self._choose(alternatives or pool, rng)
        return self.arcs.activate(conversation_id, selected.id)

    def _draw_visual_motif(
        self,
        conversation_id: str,
        config: CreativeDirectorConfig,
        rng: random.Random | random.SystemRandom,
    ) -> VisualMotif:
        if self.motifs is None:
            raise ValueError("Visual motif repository is not configured")
        motifs = self.motifs.list_motifs()
        favorite_ids = set(config.favorite_visual_motif_ids)
        favorites = [item for item in motifs if item.id in favorite_ids]
        pool = favorites or motifs
        current = self.motifs.active(conversation_id)
        alternatives = [item for item in pool if current is None or item.id != current.id]
        selected = self._choose(alternatives or pool, rng)
        result = self.motifs.set_active(conversation_id, selected.id)
        assert result is not None
        return result

    @staticmethod
    def _layer_count(intensity: DirectorIntensity, available: int) -> int:
        requested = {"gentle": 1, "balanced": 2, "wild": 5}[intensity]
        return min(max(0, available), requested)

    def apply(
        self,
        conversation_id: str,
        *,
        automatic: bool = False,
        assistant_count: int | None = None,
        rng: random.Random | None = None,
    ) -> CreativeDirectorResult:
        config = self.repository.config(conversation_id)
        chooser: random.Random | random.SystemRandom = rng or random.SystemRandom()
        available: list[str] = []
        if not config.lock_look:
            available.append("look")
        if not config.lock_variety:
            available.append("variety")
        if not config.lock_arc:
            available.append("arc")
        if not config.lock_scene_mix:
            available.append("scene_mix")
        if self.motifs is not None and not config.lock_visual_motif:
            available.append("visual_motif")

        if automatic:
            count = self._layer_count(config.intensity, len(available))
            layers = chooser.sample(available, count) if count else []
        else:
            # "Surprise me" deliberately changes every unlocked layer.
            layers = available

        result = CreativeDirectorResult()
        for layer in layers:
            if layer == "look":
                result.look = self._draw_look(conversation_id, config, chooser)
                result.changed.append(layer)
            elif layer == "variety":
                result.variety = self.variety.draw(conversation_id, rng=chooser)
                result.changed.append(layer)
            elif layer == "arc":
                result.arc = self._draw_arc(
                    conversation_id,
                    config,
                    chooser,
                    advance_existing=automatic,
                )
                result.changed.append(layer)
            elif layer == "scene_mix":
                result.scene_mix = self.mixer.draw(conversation_id, rng=chooser)
                result.changed.append(layer)
            elif layer == "visual_motif":
                result.visual_motif = self._draw_visual_motif(conversation_id, config, chooser)
                result.changed.append(layer)

        if automatic and assistant_count is not None:
            self.repository.mark_turn(conversation_id, assistant_count)
        return result

    def maybe_rotate(
        self,
        conversation_id: str,
        *,
        assistant_count: int,
        rng: random.Random | None = None,
    ) -> CreativeDirectorResult | None:
        config = self.repository.config(conversation_id)
        if not config.enabled:
            return None
        last_turn = self.repository.last_turn(conversation_id)
        if assistant_count - last_turn < config.interval:
            return None
        return self.apply(
            conversation_id,
            automatic=True,
            assistant_count=assistant_count,
            rng=rng,
        )
