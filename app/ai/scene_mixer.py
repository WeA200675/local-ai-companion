from __future__ import annotations

import random

from pydantic import BaseModel, Field

from app.memory.store import StateStore


class MixComponent(BaseModel):
    id: str
    label: str
    context: str
    style_tags: list[str] = Field(default_factory=list)


class SceneMix(BaseModel):
    signature: str
    title: str
    context: str
    style_tags: list[str] = Field(default_factory=list)
    components: dict[str, str] = Field(default_factory=dict)
    component_ids: dict[str, str] = Field(default_factory=dict)

    def prompt_text(self) -> str:
        return f"{self.title}: {self.context}"


class SceneMixerState(BaseModel):
    active_by_conversation: dict[str, SceneMix] = Field(default_factory=dict)
    locked_dimensions_by_conversation: dict[str, list[str]] = Field(default_factory=dict)
    recent_signatures: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)


SETTINGS = [
    MixComponent(
        id="dark-studio",
        label="Dark Studio",
        context="a private dark photo studio with uncluttered space",
        style_tags=["dark studio", "editorial"],
    ),
    MixComponent(
        id="rain-window",
        label="Rain Window",
        context="a quiet interior beside a rain-streaked window with reflections outside",
        style_tags=["rain", "window reflections", "moody"],
    ),
    MixComponent(
        id="industrial-loft",
        label="Industrial Loft",
        context="an industrial loft with concrete, steel, and generous negative space",
        style_tags=["industrial", "loft", "texture"],
    ),
    MixComponent(
        id="private-lounge",
        label="Private Lounge",
        context="a private lounge with deep seating, clean lines, and a secluded atmosphere",
        style_tags=["lounge", "private", "elegant"],
    ),
    MixComponent(
        id="mirror-room",
        label="Mirror Room",
        context="a minimal room with one large mirror used as a compositional element",
        style_tags=["mirror", "reflection", "minimal"],
    ),
]

LIGHTING = [
    MixComponent(
        id="low-key",
        label="Low Key",
        context="low-key lighting with controlled highlights and deep shadow",
        style_tags=["low key", "deep shadow", "cinematic lighting"],
    ),
    MixComponent(
        id="neon-edge",
        label="Neon Edge",
        context="subtle colored edge light with dark ambient fill",
        style_tags=["neon edge", "rim light", "night"],
    ),
    MixComponent(
        id="warm-lamp",
        label="Warm Lamp",
        context="warm practical lamp light with soft falloff",
        style_tags=["warm light", "soft falloff", "intimate lighting"],
    ),
    MixComponent(
        id="hard-window",
        label="Hard Window",
        context="directional window light creating graphic bands of light and shadow",
        style_tags=["window light", "graphic shadow", "contrast"],
    ),
    MixComponent(
        id="silver-rim",
        label="Silver Rim",
        context="cool silver rim light separating the subject from a darker background",
        style_tags=["silver rim", "cool light", "separation"],
    ),
]

COMPOSITIONS = [
    MixComponent(
        id="close-up",
        label="Close-up",
        context="a close portrait-like composition emphasizing expression, hands, and material detail",
        style_tags=["close-up", "portrait", "detail"],
    ),
    MixComponent(
        id="full-silhouette",
        label="Silhouette",
        context="a full-body silhouette composition with strong posture and clean negative space",
        style_tags=["silhouette", "full body", "negative space"],
    ),
    MixComponent(
        id="mirror-angle",
        label="Mirror Angle",
        context="an off-axis composition using a mirror reflection without losing identity continuity",
        style_tags=["mirror angle", "reflection", "off-axis"],
    ),
    MixComponent(
        id="low-angle",
        label="Low Angle",
        context="a restrained low-angle composition that emphasizes presence rather than distortion",
        style_tags=["low angle", "presence", "cinematic"],
    ),
    MixComponent(
        id="wide-frame",
        label="Wide Frame",
        context="a wider environmental frame where the room and subject share visual importance",
        style_tags=["wide frame", "environmental portrait", "space"],
    ),
]

ATMOSPHERES = [
    MixComponent(
        id="controlled",
        label="Controlled",
        context="a composed, deliberate mood with precise body language",
        style_tags=["controlled", "composed", "precise"],
    ),
    MixComponent(
        id="playful",
        label="Playful",
        context="a playful, knowing mood with lighter energy and expressive reactions",
        style_tags=["playful", "knowing", "expressive"],
    ),
    MixComponent(
        id="mysterious",
        label="Mysterious",
        context="a mysterious mood built through partial reveal, shadow, and unanswered visual detail",
        style_tags=["mysterious", "partial reveal", "suspense"],
    ),
    MixComponent(
        id="dreamlike",
        label="Dreamlike",
        context="a slightly dreamlike mood with soft transitions and selective focus",
        style_tags=["dreamlike", "selective focus", "soft atmosphere"],
    ),
    MixComponent(
        id="editorial",
        label="Editorial",
        context="a polished editorial mood with intentional posing and strong styling choices",
        style_tags=["editorial", "polished", "fashion portrait"],
    ),
]

_COMPONENTS = {
    "setting": SETTINGS,
    "lighting": LIGHTING,
    "composition": COMPOSITIONS,
    "atmosphere": ATMOSPHERES,
}
_VALID_DIMENSIONS = tuple(_COMPONENTS)


class SceneMixerRepository:
    STATE_KEY = "scene_mixer"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> SceneMixerState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return SceneMixerState()
        try:
            state = SceneMixerState.model_validate_json(payload)
        except ValueError:
            return SceneMixerState()
        state.locked_dimensions_by_conversation = {
            conversation_id: [
                dimension for dimension in dimensions if dimension in _VALID_DIMENSIONS
            ]
            for conversation_id, dimensions in state.locked_dimensions_by_conversation.items()
        }
        return state

    def save(self, state: SceneMixerState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def active(self, conversation_id: str) -> SceneMix | None:
        mix = self.load().active_by_conversation.get(conversation_id)
        return mix.model_copy(deep=True) if mix is not None else None

    def locked_dimensions(self, conversation_id: str) -> set[str]:
        state = self.load()
        return set(state.locked_dimensions_by_conversation.get(conversation_id, []))

    def set_dimension_locked(self, conversation_id: str, dimension: str, locked: bool) -> None:
        if dimension not in _VALID_DIMENSIONS:
            raise ValueError(f"Unsupported scene-mixer dimension: {dimension}")
        state = self.load()
        values = set(state.locked_dimensions_by_conversation.get(conversation_id, []))
        if locked:
            values.add(dimension)
        else:
            values.discard(dimension)
        if values:
            state.locked_dimensions_by_conversation[conversation_id] = [
                name for name in _VALID_DIMENSIONS if name in values
            ]
        else:
            state.locked_dimensions_by_conversation.pop(conversation_id, None)
        state.revision += 1
        self.save(state)

    @staticmethod
    def _build_mix(parts: dict[str, MixComponent]) -> SceneMix:
        signature = ":".join(component.id for component in parts.values())
        title = " · ".join(component.label for component in parts.values())
        context = "; ".join(component.context for component in parts.values())
        tags: list[str] = []
        seen: set[str] = set()
        for component in parts.values():
            for tag in component.style_tags:
                key = tag.casefold()
                if key not in seen:
                    seen.add(key)
                    tags.append(tag)
        return SceneMix(
            signature=signature,
            title=title,
            context=context,
            style_tags=tags,
            components={key: value.label for key, value in parts.items()},
            component_ids={key: value.id for key, value in parts.items()},
        )

    @staticmethod
    def _component_by_id(dimension: str, component_id: str) -> MixComponent | None:
        return next(
            (item for item in _COMPONENTS[dimension] if item.id == component_id),
            None,
        )

    def _locked_parts(
        self,
        active: SceneMix | None,
        locked_dimensions: set[str],
    ) -> dict[str, MixComponent]:
        if active is None:
            return {}
        parts: dict[str, MixComponent] = {}
        for dimension in locked_dimensions:
            component_id = active.component_ids.get(dimension)
            if not component_id:
                continue
            component = self._component_by_id(dimension, component_id)
            if component is not None:
                parts[dimension] = component
        return parts

    def draw(
        self,
        conversation_id: str,
        *,
        rng: random.Random | None = None,
    ) -> SceneMix:
        chooser = rng or random.SystemRandom()
        state = self.load()
        recent = set(state.recent_signatures[-6:])
        locked_dimensions = set(
            state.locked_dimensions_by_conversation.get(conversation_id, [])
        )
        fixed = self._locked_parts(
            state.active_by_conversation.get(conversation_id),
            locked_dimensions,
        )
        selected: SceneMix | None = None
        for _attempt in range(12):
            parts = {
                dimension: fixed.get(dimension) or chooser.choice(options)
                for dimension, options in _COMPONENTS.items()
            }
            candidate = self._build_mix(parts)
            selected = candidate
            if candidate.signature not in recent:
                break
        assert selected is not None
        state.active_by_conversation[conversation_id] = selected
        state.recent_signatures = [
            signature for signature in state.recent_signatures if signature != selected.signature
        ]
        state.recent_signatures.append(selected.signature)
        state.recent_signatures = state.recent_signatures[-12:]
        state.revision += 1
        self.save(state)
        return selected.model_copy(deep=True)

    def clear(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.active_by_conversation:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
