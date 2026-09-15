from __future__ import annotations

import random
from typing import Callable, Literal

from pydantic import BaseModel, Field

from app.ai.creative_accents import DetailAccentRepository, MoodGradeRepository
from app.ai.creative_director import CreativeDirectorRepository
from app.ai.look_presets import LookPresetRepository
from app.ai.scene_evolution import (
    ActiveRitual,
    ActiveSceneEvolution,
    RitualRepository,
    SceneEvolutionRepository,
)
from app.ai.scene_mixer import (
    ATMOSPHERES,
    COMPOSITIONS,
    LIGHTING,
    SETTINGS,
    MixComponent,
    SceneMix,
    SceneMixerRepository,
)
from app.ai.session_arcs import SessionArcRepository
from app.ai.variety import VarietyRepository
from app.ai.visual_motifs import VisualMotifRepository
from app.memory.store import StateStore

MediaPreference = Literal["auto", "image", "motion"]


class ScenarioTemplate(BaseModel):
    """Compatibility envelope used to build a coherent temporary session bundle."""

    id: str
    name: str
    description: str
    look_ids: list[str] = Field(default_factory=list)
    variety_ids: list[str] = Field(default_factory=list)
    arc_ids: list[str] = Field(default_factory=list)
    scene_components: dict[str, list[str]] = Field(default_factory=dict)
    motif_ids: list[str] = Field(default_factory=list)
    mood_ids: list[str] = Field(default_factory=list)
    detail_ids: list[str] = Field(default_factory=list)
    evolution_ids: list[str] = Field(default_factory=list)
    ritual_ids: list[str] = Field(default_factory=list)
    media_preference: MediaPreference = "auto"


class PreviousCreativeState(BaseModel):
    look_id: str | None = None
    variety_id: str | None = None
    arc_id: str | None = None
    arc_stage_index: int = 0
    scene_component_ids: dict[str, str] = Field(default_factory=dict)
    motif_id: str | None = None
    mood_id: str | None = None
    detail_id: str | None = None
    evolution: ActiveSceneEvolution | None = None
    ritual: ActiveRitual | None = None


class ScenarioSeedSelection(BaseModel):
    template_id: str
    template_name: str
    description: str
    random_seed: int = Field(ge=0)
    media_preference: MediaPreference = "auto"
    selected_ids: dict[str, str] = Field(default_factory=dict)
    scene_component_ids: dict[str, str] = Field(default_factory=dict)
    layer_summary: dict[str, str] = Field(default_factory=dict)
    preserved_layers: list[str] = Field(default_factory=list)
    compatibility_score: int = Field(default=100, ge=0, le=100)
    compatibility_notes: list[str] = Field(default_factory=list)
    automatic_sequences: bool = True
    previous: PreviousCreativeState


class ScenarioSeedState(BaseModel):
    active_by_conversation: dict[str, ScenarioSeedSelection] = Field(default_factory=dict)
    recent_template_ids_by_conversation: dict[str, list[str]] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_scenario_templates() -> list[ScenarioTemplate]:
    return [
        ScenarioTemplate(
            id="rain-noir",
            name="Rain Noir",
            description="Reflexionen, kontrollierte Dunkelheit und filmische Regenstimmung.",
            look_ids=["rainy-noir", "noir-latex", "leather-command"],
            variety_ids=["slow-burn", "visual-frame", "mystery-beat"],
            arc_ids=["mystery-night", "cinematic-sequence", "tension-curve"],
            scene_components={
                "setting": ["rain-window", "mirror-room"],
                "lighting": ["neon-edge", "low-key", "silver-rim"],
                "composition": ["wide-frame", "mirror-angle", "close-up"],
                "atmosphere": ["mysterious", "controlled"],
            },
            motif_ids=["rain-silhouette", "over-shoulder-noir", "mirror-offset"],
            mood_ids=["neon-night", "amber-noir", "silver-monochrome"],
            detail_ids=["rain-glass", "mirror-trace", "footwear-reflection"],
            evolution_ids=["storm-passes", "night-deepens"],
            ritual_ids=["mystery-reveal", "camera-sequence"],
            media_preference="auto",
        ),
        ScenarioTemplate(
            id="studio-command",
            name="Studio Command",
            description="Saubere Editorial-Geometrie, starke Präsenz und kontrollierte Materialdetails.",
            look_ids=["studio-minimal", "leather-command", "elegant-monochrome"],
            variety_ids=["confident-presence", "visual-frame", "minimalist"],
            arc_ids=["tension-curve", "cinematic-sequence"],
            scene_components={
                "setting": ["dark-studio", "industrial-loft"],
                "lighting": ["silver-rim", "hard-window", "low-key"],
                "composition": ["low-angle", "close-up", "full-silhouette"],
                "atmosphere": ["controlled", "editorial"],
            },
            motif_ids=["steady-gaze", "seated-command", "material-detail"],
            mood_ids=["cool-steel", "editorial-punch", "silver-monochrome"],
            detail_ids=["metal-accent", "glove-buckle", "chair-geometry"],
            evolution_ids=["studio-afterhours", "threshold-shift"],
            ritual_ids=["arrival-focus", "camera-sequence", "wardrobe-detail"],
            media_preference="image",
        ),
        ScenarioTemplate(
            id="soft-lounge",
            name="Soft Lounge Pulse",
            description="Wärmere Lounge-Atmosphäre mit spielerischen oder ruhigen Dialogbeats.",
            look_ids=["soft-lounge", "elegant-monochrome"],
            variety_ids=["playful-spark", "afterglow", "dialogue-closeup"],
            arc_ids=["playful-pulse", "tension-curve"],
            scene_components={
                "setting": ["private-lounge"],
                "lighting": ["warm-lamp", "silver-rim"],
                "composition": ["close-up", "wide-frame"],
                "atmosphere": ["playful", "dreamlike", "controlled"],
            },
            motif_ids=["playful-lean", "seated-command", "steady-gaze"],
            mood_ids=["soft-film", "amber-noir"],
            detail_ids=["chair-geometry", "velvet-drape", "hand-prop"],
            evolution_ids=["night-deepens"],
            ritual_ids=["arrival-focus", "cooldown-close", "wardrobe-detail"],
            media_preference="image",
        ),
        ScenarioTemplate(
            id="mirror-mystery",
            name="Mirror Mystery",
            description="Asymmetrische Spiegelbilder, kleine Hinweise und kontrollierte Enthüllungen.",
            look_ids=["elegant-monochrome", "noir-latex", "studio-minimal"],
            variety_ids=["mystery-beat", "slow-burn", "creative-detour"],
            arc_ids=["mystery-night", "cinematic-sequence"],
            scene_components={
                "setting": ["mirror-room", "dark-studio"],
                "lighting": ["silver-rim", "low-key", "hard-window"],
                "composition": ["mirror-angle", "close-up"],
                "atmosphere": ["mysterious", "editorial"],
            },
            motif_ids=["mirror-offset", "over-shoulder-noir", "material-detail"],
            mood_ids=["silver-monochrome", "cool-steel", "neon-night"],
            detail_ids=["mirror-trace", "metal-accent", "hand-prop"],
            evolution_ids=["threshold-shift", "night-deepens"],
            ritual_ids=["mystery-reveal", "camera-sequence"],
            media_preference="auto",
        ),
        ScenarioTemplate(
            id="retro-afterhours",
            name="Retro Afterhours",
            description="Polierter Retro-Look, weicher Filmton und lockerer Studio-Ausklang.",
            look_ids=["retro-glam", "elegant-monochrome"],
            variety_ids=["visual-frame", "playful-spark", "afterglow"],
            arc_ids=["cinematic-sequence", "playful-pulse"],
            scene_components={
                "setting": ["dark-studio", "private-lounge"],
                "lighting": ["warm-lamp", "hard-window"],
                "composition": ["full-silhouette", "close-up", "wide-frame"],
                "atmosphere": ["editorial", "dreamlike", "playful"],
            },
            motif_ids=["steady-gaze", "material-detail", "playful-lean"],
            mood_ids=["faded-vintage", "editorial-punch", "soft-film"],
            detail_ids=["velvet-drape", "chair-geometry", "metal-accent"],
            evolution_ids=["studio-afterhours", "night-deepens"],
            ritual_ids=["camera-sequence", "wardrobe-detail", "cooldown-close"],
            media_preference="image",
        ),
        ScenarioTemplate(
            id="motion-night",
            name="Motion Night",
            description="Dynamischer Nacht-Seed mit Bewegungsraum für GIF- oder Video-Workflows.",
            look_ids=["rainy-noir", "leather-command", "noir-latex"],
            variety_ids=["visual-frame", "creative-detour", "role-flip"],
            arc_ids=["cinematic-sequence", "tension-curve"],
            scene_components={
                "setting": ["rain-window", "industrial-loft"],
                "lighting": ["neon-edge", "silver-rim"],
                "composition": ["wide-frame", "low-angle", "full-silhouette"],
                "atmosphere": ["mysterious", "controlled"],
            },
            motif_ids=["rain-silhouette", "over-shoulder-noir", "footwear-frame"],
            mood_ids=["neon-night", "cool-steel"],
            detail_ids=["rain-glass", "footwear-reflection", "metal-accent"],
            evolution_ids=["storm-passes", "threshold-shift"],
            ritual_ids=["camera-sequence", "arrival-focus"],
            media_preference="motion",
        ),
        ScenarioTemplate(
            id="minimal-focus",
            name="Minimal Focus",
            description="Reduzierte Formen, klare Blickführung und wenig visuelle Ablenkung.",
            look_ids=["studio-minimal", "elegant-monochrome"],
            variety_ids=["minimalist", "confident-presence", "dialogue-closeup"],
            arc_ids=["tension-curve", "cinematic-sequence"],
            scene_components={
                "setting": ["dark-studio", "mirror-room"],
                "lighting": ["silver-rim", "hard-window"],
                "composition": ["close-up", "full-silhouette"],
                "atmosphere": ["controlled", "editorial"],
            },
            motif_ids=["steady-gaze", "material-detail"],
            mood_ids=["cool-steel", "silver-monochrome"],
            detail_ids=["metal-accent", "glove-buckle"],
            evolution_ids=["threshold-shift", "studio-afterhours"],
            ritual_ids=["arrival-focus", "wardrobe-detail"],
            media_preference="image",
        ),
    ]


_SCENE_OPTIONS: dict[str, list[MixComponent]] = {
    "setting": SETTINGS,
    "lighting": LIGHTING,
    "composition": COMPOSITIONS,
    "atmosphere": ATMOSPHERES,
}


class ScenarioSeedRepository:
    STATE_KEY = "scenario_seeds"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> ScenarioSeedState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return ScenarioSeedState()
        try:
            state = ScenarioSeedState.model_validate_json(payload)
        except ValueError:
            return ScenarioSeedState()
        valid_templates = {item.id for item in default_scenario_templates()}
        state.recent_template_ids_by_conversation = {
            key: [item for item in values if item in valid_templates][-6:]
            for key, values in state.recent_template_ids_by_conversation.items()
        }
        return state

    def save(self, state: ScenarioSeedState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def active(self, conversation_id: str) -> ScenarioSeedSelection | None:
        item = self.load().active_by_conversation.get(conversation_id)
        return item.model_copy(deep=True) if item is not None else None

    def recent_template_ids(self, conversation_id: str) -> list[str]:
        return list(self.load().recent_template_ids_by_conversation.get(conversation_id, []))

    def set_active(self, conversation_id: str, selection: ScenarioSeedSelection) -> None:
        state = self.load()
        state.active_by_conversation[conversation_id] = selection.model_copy(deep=True)
        recent = [
            item
            for item in state.recent_template_ids_by_conversation.get(conversation_id, [])
            if item != selection.template_id
        ]
        recent.append(selection.template_id)
        state.recent_template_ids_by_conversation[conversation_id] = recent[-6:]
        state.revision += 1
        self.save(state)

    def clear(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.active_by_conversation:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)


class ScenarioSeedEngine:
    """Build coherent temporary session bundles while respecting creative locks."""

    def __init__(
        self,
        repository: ScenarioSeedRepository,
        looks: LookPresetRepository,
        variety: VarietyRepository,
        arcs: SessionArcRepository,
        mixer: SceneMixerRepository,
        motifs: VisualMotifRepository,
        moods: MoodGradeRepository,
        details: DetailAccentRepository,
        evolutions: SceneEvolutionRepository,
        rituals: RitualRepository,
        director_repository: CreativeDirectorRepository,
    ) -> None:
        self.repository = repository
        self.looks = looks
        self.variety = variety
        self.arcs = arcs
        self.mixer = mixer
        self.motifs = motifs
        self.moods = moods
        self.details = details
        self.evolutions = evolutions
        self.rituals = rituals
        self.director_repository = director_repository

    def templates(self) -> list[ScenarioTemplate]:
        return [item.model_copy(deep=True) for item in default_scenario_templates()]

    def template(self, template_id: str) -> ScenarioTemplate | None:
        clean = template_id.strip()
        return next((item for item in self.templates() if item.id == clean), None)

    @staticmethod
    def _pick_id(
        candidates: list[str],
        available_ids: set[str],
        chooser: random.Random,
        preferred_ids: set[str] | None = None,
    ) -> str | None:
        valid = [item for item in candidates if item in available_ids]
        if not valid:
            return None
        preferred = [item for item in valid if item in (preferred_ids or set())]
        return chooser.choice(preferred or valid)

    def _capture_previous(self, conversation_id: str) -> PreviousCreativeState:
        look = self.looks.active(conversation_id)
        variety = self.variety.active(conversation_id)
        arc = self.arcs.active(conversation_id)
        mix = self.mixer.active(conversation_id)
        motif = self.motifs.active(conversation_id)
        mood = self.moods.active(conversation_id)
        detail = self.details.active(conversation_id)
        return PreviousCreativeState(
            look_id=look.id if look else None,
            variety_id=variety.id if variety else None,
            arc_id=arc.arc_id if arc else None,
            arc_stage_index=arc.stage_index if arc else 0,
            scene_component_ids=dict(mix.component_ids) if mix else {},
            motif_id=motif.id if motif else None,
            mood_id=mood.id if mood else None,
            detail_id=detail.id if detail else None,
            evolution=self.evolutions.active(conversation_id),
            ritual=self.rituals.active(conversation_id),
        )

    @staticmethod
    def _scene_component(dimension: str, component_id: str) -> MixComponent | None:
        return next(
            (item for item in _SCENE_OPTIONS[dimension] if item.id == component_id),
            None,
        )

    def _persist_mix(self, conversation_id: str, parts: dict[str, MixComponent]) -> SceneMix:
        selected = self.mixer._build_mix(parts)  # noqa: SLF001 - same creative subsystem
        state = self.mixer.load()
        state.active_by_conversation[conversation_id] = selected
        state.recent_signatures = [
            signature for signature in state.recent_signatures if signature != selected.signature
        ]
        state.recent_signatures.append(selected.signature)
        state.recent_signatures = state.recent_signatures[-12:]
        state.revision += 1
        self.mixer.save(state)
        return selected.model_copy(deep=True)

    def _apply_scene(
        self,
        conversation_id: str,
        template: ScenarioTemplate,
        chooser: random.Random,
    ) -> tuple[SceneMix, list[str], int, list[str]]:
        active = self.mixer.active(conversation_id)
        locked = self.mixer.locked_dimensions(conversation_id)
        parts: dict[str, MixComponent] = {}
        preserved: list[str] = []
        penalty = 0
        notes: list[str] = []

        for dimension, options in _SCENE_OPTIONS.items():
            candidate_ids = template.scene_components.get(dimension, [])
            if dimension in locked and active is not None:
                previous_id = active.component_ids.get(dimension, "")
                previous = self._scene_component(dimension, previous_id)
                if previous is not None:
                    parts[dimension] = previous
                    preserved.append(f"scene_mix.{dimension}")
                    if candidate_ids and previous.id not in candidate_ids:
                        penalty += 4
                        notes.append(f"Scene-Mixer-Lock behält {dimension} außerhalb des Theme-Pools.")
                    continue

            valid = [item for item in options if not candidate_ids or item.id in candidate_ids]
            parts[dimension] = chooser.choice(valid or options)

        return self._persist_mix(conversation_id, parts), preserved, penalty, notes

    @staticmethod
    def _mismatch_penalty(current_id: str | None, candidates: list[str]) -> int:
        if not current_id or not candidates or current_id in candidates:
            return 0
        return 8

    def generate(
        self,
        conversation_id: str,
        *,
        template_id: str | None = None,
        include_evolution: bool = True,
        include_ritual: bool = True,
        automatic_sequences: bool = True,
        assistant_count: int = 0,
        seed: int | None = None,
    ) -> ScenarioSeedSelection:
        templates = self.templates()
        if not templates:
            raise ValueError("No scenario templates are configured")

        random_seed = int(seed) if seed is not None else random.SystemRandom().randrange(0, 2**31)
        chooser = random.Random(random_seed)
        if template_id:
            template = self.template(template_id)
            if template is None:
                raise KeyError(f"Scenario template {template_id!r} not found")
        else:
            recent = set(self.repository.recent_template_ids(conversation_id)[-3:])
            fresh = [item for item in templates if item.id not in recent]
            template = chooser.choice(fresh or templates)

        previous = self._capture_previous(conversation_id)
        config = self.director_repository.config(conversation_id)
        selected_ids: dict[str, str] = {}
        summary: dict[str, str] = {}
        preserved: list[str] = []
        notes: list[str] = []
        penalty = 0

        def preserve_layer(
            layer: str,
            current_id: str | None,
            current_label: str | None,
            candidates: list[str],
        ) -> None:
            nonlocal penalty
            preserved.append(layer)
            if current_id:
                selected_ids[layer] = current_id
            if current_label:
                summary[layer] = current_label
            mismatch = self._mismatch_penalty(current_id, candidates)
            penalty += mismatch
            if mismatch:
                notes.append(f"{layer} bleibt wegen Lock erhalten und liegt außerhalb des Theme-Pools.")

        look_current = self.looks.active(conversation_id)
        if config.lock_look:
            preserve_layer(
                "look",
                look_current.id if look_current else None,
                look_current.name if look_current else None,
                template.look_ids,
            )
        else:
            look_id = self._pick_id(
                template.look_ids,
                {item.id for item in self.looks.list_presets()},
                chooser,
                set(config.favorite_look_ids),
            )
            if look_id:
                look = self.looks.set_active(conversation_id, look_id)
                assert look is not None
                selected_ids["look"] = look.id
                summary["Look"] = look.name

        variety_current = self.variety.active(conversation_id)
        if config.lock_variety:
            preserve_layer(
                "variety",
                variety_current.id if variety_current else None,
                variety_current.name if variety_current else None,
                template.variety_ids,
            )
        else:
            variety_id = self._pick_id(
                template.variety_ids,
                {item.id for item in self.variety.list_cards(enabled_only=True)},
                chooser,
            )
            if variety_id:
                card = self.variety.set_active(conversation_id, variety_id)
                assert card is not None
                selected_ids["variety"] = card.id
                summary["Impuls"] = card.name

        arc_current = self.arcs.active(conversation_id)
        if config.lock_arc:
            preserve_layer(
                "arc",
                arc_current.arc_id if arc_current else None,
                arc_current.arc_name if arc_current else None,
                template.arc_ids,
            )
        else:
            arc_id = self._pick_id(
                template.arc_ids,
                {item.id for item in self.arcs.list_arcs()},
                chooser,
                set(config.favorite_arc_ids),
            )
            if arc_id:
                arc = self.arcs.activate(conversation_id, arc_id)
                selected_ids["arc"] = arc.arc_id
                summary["Arc"] = arc.arc_name

        if config.lock_scene_mix:
            current_mix = self.mixer.active(conversation_id)
            preserved.append("scene_mix")
            if current_mix is not None:
                summary["Scene Mixer"] = current_mix.title
                selected_ids["scene_mix"] = current_mix.signature
                for dimension, component_id in current_mix.component_ids.items():
                    candidates = template.scene_components.get(dimension, [])
                    if candidates and component_id not in candidates:
                        penalty += 3
                if any(
                    template.scene_components.get(dimension)
                    and component_id not in template.scene_components[dimension]
                    for dimension, component_id in current_mix.component_ids.items()
                ):
                    notes.append("Der komplette Scene Mixer bleibt wegen Lock unverändert.")
            scene_mix = current_mix
        else:
            scene_mix, scene_preserved, scene_penalty, scene_notes = self._apply_scene(
                conversation_id,
                template,
                chooser,
            )
            preserved.extend(scene_preserved)
            penalty += scene_penalty
            notes.extend(scene_notes)
            selected_ids["scene_mix"] = scene_mix.signature
            summary["Scene Mixer"] = scene_mix.title

        motif_current = self.motifs.active(conversation_id)
        if config.lock_visual_motif:
            preserve_layer(
                "visual_motif",
                motif_current.id if motif_current else None,
                motif_current.name if motif_current else None,
                template.motif_ids,
            )
        else:
            motif_id = self._pick_id(
                template.motif_ids,
                {item.id for item in self.motifs.list_motifs()},
                chooser,
                set(config.favorite_visual_motif_ids),
            )
            if motif_id:
                motif = self.motifs.set_active(conversation_id, motif_id)
                assert motif is not None
                selected_ids["visual_motif"] = motif.id
                summary["Visual-Motiv"] = motif.name

        mood_current = self.moods.active(conversation_id)
        if config.lock_mood_grade:
            preserve_layer(
                "mood_grade",
                mood_current.id if mood_current else None,
                mood_current.name if mood_current else None,
                template.mood_ids,
            )
        else:
            mood_id = self._pick_id(
                template.mood_ids,
                {item.id for item in self.moods.list_grades()},
                chooser,
            )
            if mood_id:
                mood = self.moods.set_active(conversation_id, mood_id)
                assert mood is not None
                selected_ids["mood_grade"] = mood.id
                summary["Mood"] = mood.name

        detail_current = self.details.active(conversation_id)
        if config.lock_detail_accent:
            preserve_layer(
                "detail_accent",
                detail_current.id if detail_current else None,
                detail_current.name if detail_current else None,
                template.detail_ids,
            )
        else:
            detail_id = self._pick_id(
                template.detail_ids,
                {item.id for item in self.details.list_accents()},
                chooser,
            )
            if detail_id:
                detail = self.details.set_active(conversation_id, detail_id)
                assert detail is not None
                selected_ids["detail_accent"] = detail.id
                summary["Detail"] = detail.name

        if include_evolution:
            evolution_id = self._pick_id(
                template.evolution_ids,
                {item.id for item in self.evolutions.list_plans()},
                chooser,
            )
            if evolution_id:
                evolution = self.evolutions.start(
                    conversation_id,
                    evolution_id,
                    automatic=automatic_sequences,
                    interval=2,
                    loop=False,
                    assistant_count=assistant_count,
                )
                selected_ids["scene_evolution"] = evolution.plan_id
                summary["Evolution"] = evolution.plan_name
        else:
            preserved.append("scene_evolution")
            current = self.evolutions.active(conversation_id)
            if current:
                summary["Evolution"] = current.plan_name

        if include_ritual:
            ritual_id = self._pick_id(
                template.ritual_ids,
                {item.id for item in self.rituals.list_rituals()},
                chooser,
            )
            if ritual_id:
                ritual = self.rituals.start(
                    conversation_id,
                    ritual_id,
                    automatic=automatic_sequences,
                    interval=1,
                    loop=False,
                    assistant_count=assistant_count,
                )
                selected_ids["ritual"] = ritual.ritual_id
                summary["Ritual"] = ritual.ritual_name
        else:
            preserved.append("ritual")
            current = self.rituals.active(conversation_id)
            if current:
                summary["Ritual"] = current.ritual_name

        compatibility_score = max(0, min(100, 100 - penalty))
        if not notes:
            notes.append("Alle veränderten Ebenen stammen aus demselben Kompatibilitätsprofil.")

        selection = ScenarioSeedSelection(
            template_id=template.id,
            template_name=template.name,
            description=template.description,
            random_seed=random_seed,
            media_preference=template.media_preference,
            selected_ids=selected_ids,
            scene_component_ids=dict(scene_mix.component_ids) if scene_mix is not None else {},
            layer_summary=summary,
            preserved_layers=list(dict.fromkeys(preserved)),
            compatibility_score=compatibility_score,
            compatibility_notes=notes,
            automatic_sequences=automatic_sequences,
            previous=previous,
        )
        self.repository.set_active(conversation_id, selection)
        return selection.model_copy(deep=True)

    def _restore_scene(self, conversation_id: str, component_ids: dict[str, str]) -> None:
        if not component_ids:
            self.mixer.clear(conversation_id)
            return
        parts: dict[str, MixComponent] = {}
        for dimension in _SCENE_OPTIONS:
            component = self._scene_component(dimension, component_ids.get(dimension, ""))
            if component is None:
                self.mixer.clear(conversation_id)
                return
            parts[dimension] = component
        self._persist_mix(conversation_id, parts)

    @staticmethod
    def _restore_simple(
        item_id: str | None,
        getter: Callable[[str], object | None],
        setter: Callable[[str, str | None], object | None],
        conversation_id: str,
    ) -> None:
        if item_id and getter(item_id) is None:
            setter(conversation_id, None)
            return
        setter(conversation_id, item_id)

    def restore_previous(self, conversation_id: str) -> bool:
        selection = self.repository.active(conversation_id)
        if selection is None:
            return False
        previous = selection.previous

        self._restore_simple(previous.look_id, self.looks.get, self.looks.set_active, conversation_id)
        self._restore_simple(
            previous.variety_id,
            self.variety.get,
            self.variety.set_active,
            conversation_id,
        )

        self.arcs.clear(conversation_id)
        if previous.arc_id and any(item.id == previous.arc_id for item in self.arcs.list_arcs()):
            self.arcs.activate(conversation_id, previous.arc_id)
            for _ in range(max(0, previous.arc_stage_index)):
                if self.arcs.advance(conversation_id) is None:
                    break

        self._restore_scene(conversation_id, previous.scene_component_ids)
        self._restore_simple(
            previous.motif_id,
            self.motifs.get,
            self.motifs.set_active,
            conversation_id,
        )
        self._restore_simple(previous.mood_id, self.moods.get, self.moods.set_active, conversation_id)
        self._restore_simple(
            previous.detail_id,
            self.details.get,
            self.details.set_active,
            conversation_id,
        )

        self.evolutions.clear(conversation_id)
        if previous.evolution is not None and self.evolutions.get(previous.evolution.plan_id):
            old = previous.evolution
            self.evolutions.start(
                conversation_id,
                old.plan_id,
                automatic=old.automatic,
                interval=old.interval,
                loop=old.loop,
                assistant_count=old.last_turn,
            )
            for _ in range(old.stage_index):
                self.evolutions.advance(conversation_id, assistant_count=old.last_turn)
            self.evolutions.configure(
                conversation_id,
                automatic=old.automatic,
                interval=old.interval,
                loop=old.loop,
                assistant_count=old.last_turn,
            )

        self.rituals.clear(conversation_id)
        if previous.ritual is not None and self.rituals.get(previous.ritual.ritual_id):
            old = previous.ritual
            self.rituals.start(
                conversation_id,
                old.ritual_id,
                automatic=old.automatic,
                interval=old.interval,
                loop=old.loop,
                assistant_count=old.last_turn,
            )
            for _ in range(old.step_index):
                if self.rituals.advance(conversation_id, assistant_count=old.last_turn) is None:
                    break
            current = self.rituals.active(conversation_id)
            if current is not None:
                self.rituals.configure(
                    conversation_id,
                    automatic=old.automatic,
                    interval=old.interval,
                    loop=old.loop,
                    assistant_count=old.last_turn,
                )

        self.repository.clear(conversation_id)
        return True
