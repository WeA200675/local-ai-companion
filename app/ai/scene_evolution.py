from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class EvolutionStage(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=700)
    style_tags: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("name", "instruction", mode="before")
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


class SceneEvolutionPlan(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    stages: list[EvolutionStage] = Field(min_length=2, max_length=8)
    builtin: bool = False


class ActiveSceneEvolution(BaseModel):
    plan_id: str
    plan_name: str
    stage_index: int = Field(ge=0)
    stage_count: int = Field(ge=1)
    stage_name: str
    instruction: str
    style_tags: list[str] = Field(default_factory=list)
    automatic: bool = False
    interval: int = Field(default=2, ge=1, le=10)
    loop: bool = False
    last_turn: int = Field(default=0, ge=0)

    def prompt_text(self) -> str:
        return (
            f"{self.plan_name} — stage {self.stage_index + 1}/{self.stage_count}, "
            f"{self.stage_name}: {self.instruction}"
        )


class SceneEvolutionState(BaseModel):
    plans: list[SceneEvolutionPlan] = Field(default_factory=list)
    active_by_conversation: dict[str, ActiveSceneEvolution] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_scene_evolutions() -> list[SceneEvolutionPlan]:
    return [
        SceneEvolutionPlan(
            id="night-deepens",
            name="Night Deepens",
            description="Eine Szene wandert von ruhiger Abendstimmung über tiefere Nacht bis zum ersten Licht.",
            stages=[
                EvolutionStage(
                    name="Blue Hour",
                    instruction="Keep the established location, but let cool blue-hour light and longer shadows begin to take over.",
                    style_tags=["blue hour", "long shadows", "quiet transition"],
                ),
                EvolutionStage(
                    name="Midnight Contrast",
                    instruction="Preserve continuity while deepening contrast, practical pools of light, reflections, and a more enclosed late-night atmosphere.",
                    style_tags=["midnight", "low key", "reflections"],
                ),
                EvolutionStage(
                    name="Small Hours",
                    instruction="Make the same place feel quieter and more intimate through sparse light, negative space, and restrained movement.",
                    style_tags=["small hours", "negative space", "quiet"],
                ),
                EvolutionStage(
                    name="First Light",
                    instruction="Keep all established scene identity, but introduce the first pale daylight as a gentle visual release rather than a reset.",
                    style_tags=["first light", "soft dawn", "visual release"],
                ),
            ],
            builtin=True,
        ),
        SceneEvolutionPlan(
            id="storm-passes",
            name="Storm Passing",
            description="Wetter und Reflexionen verändern dieselbe Szene schrittweise, ohne den Ort auszutauschen.",
            stages=[
                EvolutionStage(
                    name="Distant Rain",
                    instruction="Introduce distant rain, faint window texture, and a sense that the weather is approaching while the current activity continues.",
                    style_tags=["distant rain", "window texture", "approaching storm"],
                ),
                EvolutionStage(
                    name="Downpour",
                    instruction="Increase rain reflections, moving highlights, and exterior sound cues while preserving the same room and character continuity.",
                    style_tags=["downpour", "wet reflections", "moving highlights"],
                ),
                EvolutionStage(
                    name="After Rain",
                    instruction="Let the storm recede. Use droplets, cleaner reflections, quieter pacing, and small aftermath details instead of a hard scene change.",
                    style_tags=["after rain", "droplets", "quiet aftermath"],
                ),
                EvolutionStage(
                    name="Clearing",
                    instruction="Open the visual field slightly with clearer air and softer contrast, keeping the original setting unmistakably continuous.",
                    style_tags=["clearing weather", "soft contrast", "fresh air"],
                ),
            ],
            builtin=True,
        ),
        SceneEvolutionPlan(
            id="studio-afterhours",
            name="Studio Afterhours",
            description="Vom sauberen Editorial-Setup zu einer lockereren Afterhours-Atmosphäre.",
            stages=[
                EvolutionStage(
                    name="Clean Setup",
                    instruction="Favor clear studio geometry, deliberate marks, and controlled editorial lighting.",
                    style_tags=["editorial studio", "clean geometry", "controlled light"],
                ),
                EvolutionStage(
                    name="Practical Lights",
                    instruction="Keep the studio recognizable but let practical lamps and off-set pools of light replace some of the formal setup.",
                    style_tags=["practical lights", "afterhours", "off-set pools"],
                ),
                EvolutionStage(
                    name="Loose Frame",
                    instruction="Relax the composition with asymmetry, visible edges of the set, and a less formal camera position while preserving identity.",
                    style_tags=["asymmetry", "loose frame", "behind the scenes"],
                ),
                EvolutionStage(
                    name="Last Take",
                    instruction="Give the scene a deliberate closing-image quality: fewer elements, one strong visual anchor, and calm pacing.",
                    style_tags=["last take", "strong anchor", "calm pacing"],
                ),
            ],
            builtin=True,
        ),
        SceneEvolutionPlan(
            id="threshold-shift",
            name="Threshold Shift",
            description="Die Inszenierung wandert innerhalb eines Ortes von statisch zu räumlich, ohne einen harten Ortswechsel.",
            stages=[
                EvolutionStage(
                    name="Anchor",
                    instruction="Establish one strong spatial anchor and keep the composition stable enough to make later changes readable.",
                    style_tags=["spatial anchor", "stable frame", "establishing"],
                ),
                EvolutionStage(
                    name="Reposition",
                    instruction="Shift the character or camera within the same room and reveal a previously secondary part of the environment.",
                    style_tags=["reposition", "new angle", "same room"],
                ),
                EvolutionStage(
                    name="Threshold",
                    instruction="Use a doorway, window, mirror edge, curtain, or corridor as a new compositional threshold without leaving established continuity.",
                    style_tags=["threshold", "doorway framing", "layered depth"],
                ),
                EvolutionStage(
                    name="Wide Reset",
                    instruction="End with a wider environmental composition that reconnects the new angle to the original scene geography.",
                    style_tags=["wide frame", "environmental portrait", "spatial continuity"],
                ),
            ],
            builtin=True,
        ),
    ]


class SceneEvolutionRepository:
    STATE_KEY = "scene_evolution"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(SceneEvolutionState(plans=default_scene_evolutions()))

    def load(self) -> SceneEvolutionState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return SceneEvolutionState(plans=default_scene_evolutions())
        try:
            state = SceneEvolutionState.model_validate_json(payload)
        except ValueError:
            return SceneEvolutionState(plans=default_scene_evolutions())
        if not state.plans:
            state.plans = default_scene_evolutions()
        valid_ids = {plan.id for plan in state.plans}
        state.active_by_conversation = {
            key: value
            for key, value in state.active_by_conversation.items()
            if value.plan_id in valid_ids
        }
        return state

    def save(self, state: SceneEvolutionState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_plans(self) -> list[SceneEvolutionPlan]:
        return [plan.model_copy(deep=True) for plan in self.load().plans]

    def get(self, plan_id: str) -> SceneEvolutionPlan | None:
        clean = plan_id.strip()
        return next(
            (plan.model_copy(deep=True) for plan in self.load().plans if plan.id == clean),
            None,
        )

    def active(self, conversation_id: str) -> ActiveSceneEvolution | None:
        value = self.load().active_by_conversation.get(conversation_id)
        return value.model_copy(deep=True) if value is not None else None

    @staticmethod
    def _active_from_plan(
        plan: SceneEvolutionPlan,
        *,
        stage_index: int,
        automatic: bool,
        interval: int,
        loop: bool,
        last_turn: int,
    ) -> ActiveSceneEvolution:
        stage = plan.stages[stage_index]
        return ActiveSceneEvolution(
            plan_id=plan.id,
            plan_name=plan.name,
            stage_index=stage_index,
            stage_count=len(plan.stages),
            stage_name=stage.name,
            instruction=stage.instruction,
            style_tags=list(stage.style_tags),
            automatic=automatic,
            interval=interval,
            loop=loop,
            last_turn=max(0, int(last_turn)),
        )

    def start(
        self,
        conversation_id: str,
        plan_id: str,
        *,
        automatic: bool = False,
        interval: int = 2,
        loop: bool = False,
        assistant_count: int = 0,
    ) -> ActiveSceneEvolution:
        plan = self.get(plan_id)
        if plan is None:
            raise KeyError(f"Scene evolution {plan_id!r} not found")
        active = self._active_from_plan(
            plan,
            stage_index=0,
            automatic=automatic,
            interval=max(1, min(10, int(interval))),
            loop=loop,
            last_turn=assistant_count,
        )
        state = self.load()
        state.active_by_conversation[conversation_id] = active
        state.revision += 1
        self.save(state)
        return active.model_copy(deep=True)

    def configure(
        self,
        conversation_id: str,
        *,
        automatic: bool,
        interval: int,
        loop: bool,
        assistant_count: int | None = None,
    ) -> ActiveSceneEvolution | None:
        state = self.load()
        active = state.active_by_conversation.get(conversation_id)
        if active is None:
            return None
        active.automatic = bool(automatic)
        active.interval = max(1, min(10, int(interval)))
        active.loop = bool(loop)
        if assistant_count is not None:
            active.last_turn = max(0, int(assistant_count))
        state.revision += 1
        self.save(state)
        return active.model_copy(deep=True)

    def advance(
        self,
        conversation_id: str,
        *,
        assistant_count: int | None = None,
    ) -> ActiveSceneEvolution | None:
        state = self.load()
        active = state.active_by_conversation.get(conversation_id)
        if active is None:
            return None
        plan = next((item for item in state.plans if item.id == active.plan_id), None)
        if plan is None:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
            return None

        next_index = active.stage_index + 1
        if next_index >= len(plan.stages):
            if active.loop:
                next_index = 0
            else:
                active.automatic = False
                if assistant_count is not None:
                    active.last_turn = max(0, int(assistant_count))
                state.revision += 1
                self.save(state)
                return active.model_copy(deep=True)

        replacement = self._active_from_plan(
            plan,
            stage_index=next_index,
            automatic=active.automatic,
            interval=active.interval,
            loop=active.loop,
            last_turn=assistant_count if assistant_count is not None else active.last_turn,
        )
        state.active_by_conversation[conversation_id] = replacement
        state.revision += 1
        self.save(state)
        return replacement.model_copy(deep=True)

    def maybe_advance(
        self,
        conversation_id: str,
        *,
        assistant_count: int,
    ) -> ActiveSceneEvolution | None:
        active = self.active(conversation_id)
        if active is None or not active.automatic:
            return None
        if assistant_count - active.last_turn < active.interval:
            return None
        previous_index = active.stage_index
        result = self.advance(conversation_id, assistant_count=assistant_count)
        if result is None or result.stage_index == previous_index:
            return None
        return result

    def clear(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.active_by_conversation:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)


class RitualStep(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=700)
    style_tags: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("name", "instruction", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        return " ".join(str(value or "").split())


class RitualDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    steps: list[RitualStep] = Field(min_length=2, max_length=8)
    builtin: bool = False


class ActiveRitual(BaseModel):
    ritual_id: str
    ritual_name: str
    step_index: int = Field(ge=0)
    step_count: int = Field(ge=1)
    step_name: str
    instruction: str
    style_tags: list[str] = Field(default_factory=list)
    automatic: bool = False
    interval: int = Field(default=1, ge=1, le=6)
    loop: bool = False
    last_turn: int = Field(default=0, ge=0)

    def prompt_text(self) -> str:
        return (
            f"{self.ritual_name} — step {self.step_index + 1}/{self.step_count}, "
            f"{self.step_name}: {self.instruction}"
        )


class RitualState(BaseModel):
    rituals: list[RitualDefinition] = Field(default_factory=list)
    active_by_conversation: dict[str, ActiveRitual] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_rituals() -> list[RitualDefinition]:
    return [
        RitualDefinition(
            id="arrival-focus",
            name="Arrival & Focus",
            description="Ein wiederholbarer Einstieg mit klarer Präsenz, Orientierung und anschließendem Fokus.",
            steps=[
                RitualStep(
                    name="Arrival",
                    instruction="Open with a concise arrival beat that establishes posture, distance, and the immediate atmosphere without over-explaining.",
                    style_tags=["arrival beat", "clear presence"],
                ),
                RitualStep(
                    name="Orientation",
                    instruction="Acknowledge one or two visible scene details and make the spatial relationship easy to picture.",
                    style_tags=["spatial clarity", "environment detail"],
                ),
                RitualStep(
                    name="Focus",
                    instruction="Narrow attention onto one deliberate conversational or visual focal point and reduce competing details.",
                    style_tags=["single focus", "controlled pacing"],
                ),
                RitualStep(
                    name="Settle",
                    instruction="Let the scene settle into its normal interactive rhythm instead of repeating the opening ceremony.",
                    style_tags=["settled rhythm", "continuity"],
                ),
            ],
            builtin=True,
        ),
        RitualDefinition(
            id="wardrobe-detail",
            name="Wardrobe & Detail",
            description="Eine kurze Sequenz von Silhouette über Materialdetails zurück zur ganzen Figur.",
            steps=[
                RitualStep(
                    name="Silhouette",
                    instruction="Start with the overall silhouette and stance; keep the character identity readable and the framing uncluttered.",
                    style_tags=["silhouette", "full shape", "clean framing"],
                ),
                RitualStep(
                    name="Material",
                    instruction="Shift attention to one material, seam, glove, buckle, boot, accessory, or texture detail without losing continuity.",
                    style_tags=["material detail", "fashion detail", "texture"],
                ),
                RitualStep(
                    name="Gesture",
                    instruction="Use one natural hand or posture gesture that interacts with the selected detail and changes the pose from the previous beat.",
                    style_tags=["hand gesture", "pose variation"],
                ),
                RitualStep(
                    name="Full Frame",
                    instruction="Return to a broader view that reconnects the detail to the full look and current environment.",
                    style_tags=["full frame", "wardrobe continuity"],
                ),
            ],
            builtin=True,
        ),
        RitualDefinition(
            id="challenge-reward",
            name="Challenge & Reward",
            description="Eine kontrollierte Spannungsfolge aus Aufgabe, Haltepunkt, Anerkennung und Reset.",
            steps=[
                RitualStep(
                    name="Challenge",
                    instruction="Introduce one bounded conversational or creative challenge appropriate to the current request; keep it optional and easy to decline.",
                    style_tags=["challenge beat", "clear choice"],
                ),
                RitualStep(
                    name="Hold",
                    instruction="Maintain the established challenge for one beat without escalating it or adding unrelated demands.",
                    style_tags=["held tension", "focused pacing"],
                ),
                RitualStep(
                    name="Acknowledge",
                    instruction="Acknowledge the user's direction or the scene's progress with concise positive feedback rather than repeating the challenge.",
                    style_tags=["acknowledgement", "progress beat"],
                ),
                RitualStep(
                    name="Reset",
                    instruction="Return control to the ordinary conversation flow and invite the next direction without making the ritual permanent.",
                    style_tags=["reset", "user direction"],
                ),
            ],
            builtin=True,
        ),
        RitualDefinition(
            id="camera-sequence",
            name="Camera Sequence",
            description="Ein filmischer Vierer-Rhythmus, der Bildkompositionen gezielt variiert.",
            steps=[
                RitualStep(
                    name="Establishing",
                    instruction="Use an environmental establishing frame that clearly shows the scene geography.",
                    style_tags=["establishing shot", "environment"],
                ),
                RitualStep(
                    name="Portrait",
                    instruction="Move to a medium or waist-up portrait with a different angle than the establishing frame.",
                    style_tags=["portrait", "medium frame"],
                ),
                RitualStep(
                    name="Detail",
                    instruction="Use one detail-led crop for hands, materials, footwear, reflections, or an object while keeping identity cues available.",
                    style_tags=["detail shot", "texture"],
                ),
                RitualStep(
                    name="Wide Exit",
                    instruction="Finish with a wider or off-axis composition that visually releases the sequence instead of repeating the first frame.",
                    style_tags=["wide exit", "off-axis"],
                ),
            ],
            builtin=True,
        ),
        RitualDefinition(
            id="mystery-reveal",
            name="Mystery Reveal",
            description="Kleine wiederverwendbare Dramaturgie aus Hinweis, Umleitung, Enthüllung und Nachklang.",
            steps=[
                RitualStep(
                    name="Clue",
                    instruction="Introduce one small concrete clue or unusual detail that fits the current scene and does not rewrite established facts.",
                    style_tags=["clue", "small mystery"],
                ),
                RitualStep(
                    name="Misdirection",
                    instruction="Let attention drift to a plausible secondary interpretation while keeping the original clue available.",
                    style_tags=["misdirection", "secondary focus"],
                ),
                RitualStep(
                    name="Reveal",
                    instruction="Resolve the clue with a modest reveal that adds texture rather than radically changing continuity.",
                    style_tags=["reveal", "continuity-safe twist"],
                ),
                RitualStep(
                    name="Afterbeat",
                    instruction="Give the reveal one quiet consequence or visual echo, then return to normal conversation pacing.",
                    style_tags=["afterbeat", "visual echo"],
                ),
            ],
            builtin=True,
        ),
        RitualDefinition(
            id="cooldown-close",
            name="Cooldown & Debrief",
            description="Ein ruhiger Abschlussrhythmus für längere oder intensivere kreative Sessions.",
            steps=[
                RitualStep(
                    name="Slow Down",
                    instruction="Reduce pace and visual clutter. Use shorter, calmer beats and avoid introducing a new escalation.",
                    style_tags=["slow down", "calm pacing"],
                ),
                RitualStep(
                    name="Reflect",
                    instruction="Briefly reflect the user's current preference or the strongest scene beat without treating it as permanent memory.",
                    style_tags=["reflection", "session recap"],
                ),
                RitualStep(
                    name="Closing Image",
                    instruction="End on one clear visual or conversational image and leave the next move fully open to the user.",
                    style_tags=["closing image", "open ending"],
                ),
            ],
            builtin=True,
        ),
    ]


class RitualRepository:
    STATE_KEY = "session_rituals"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(RitualState(rituals=default_rituals()))

    def load(self) -> RitualState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return RitualState(rituals=default_rituals())
        try:
            state = RitualState.model_validate_json(payload)
        except ValueError:
            return RitualState(rituals=default_rituals())
        if not state.rituals:
            state.rituals = default_rituals()
        valid_ids = {ritual.id for ritual in state.rituals}
        state.active_by_conversation = {
            key: value
            for key, value in state.active_by_conversation.items()
            if value.ritual_id in valid_ids
        }
        return state

    def save(self, state: RitualState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_rituals(self) -> list[RitualDefinition]:
        return [ritual.model_copy(deep=True) for ritual in self.load().rituals]

    def get(self, ritual_id: str) -> RitualDefinition | None:
        clean = ritual_id.strip()
        return next(
            (ritual.model_copy(deep=True) for ritual in self.load().rituals if ritual.id == clean),
            None,
        )

    def active(self, conversation_id: str) -> ActiveRitual | None:
        value = self.load().active_by_conversation.get(conversation_id)
        return value.model_copy(deep=True) if value is not None else None

    @staticmethod
    def _active_from_ritual(
        ritual: RitualDefinition,
        *,
        step_index: int,
        automatic: bool,
        interval: int,
        loop: bool,
        last_turn: int,
    ) -> ActiveRitual:
        step = ritual.steps[step_index]
        return ActiveRitual(
            ritual_id=ritual.id,
            ritual_name=ritual.name,
            step_index=step_index,
            step_count=len(ritual.steps),
            step_name=step.name,
            instruction=step.instruction,
            style_tags=list(step.style_tags),
            automatic=automatic,
            interval=interval,
            loop=loop,
            last_turn=max(0, int(last_turn)),
        )

    def start(
        self,
        conversation_id: str,
        ritual_id: str,
        *,
        automatic: bool = False,
        interval: int = 1,
        loop: bool = False,
        assistant_count: int = 0,
    ) -> ActiveRitual:
        ritual = self.get(ritual_id)
        if ritual is None:
            raise KeyError(f"Ritual {ritual_id!r} not found")
        active = self._active_from_ritual(
            ritual,
            step_index=0,
            automatic=automatic,
            interval=max(1, min(6, int(interval))),
            loop=loop,
            last_turn=assistant_count,
        )
        state = self.load()
        state.active_by_conversation[conversation_id] = active
        state.revision += 1
        self.save(state)
        return active.model_copy(deep=True)

    def configure(
        self,
        conversation_id: str,
        *,
        automatic: bool,
        interval: int,
        loop: bool,
        assistant_count: int | None = None,
    ) -> ActiveRitual | None:
        state = self.load()
        active = state.active_by_conversation.get(conversation_id)
        if active is None:
            return None
        active.automatic = bool(automatic)
        active.interval = max(1, min(6, int(interval)))
        active.loop = bool(loop)
        if assistant_count is not None:
            active.last_turn = max(0, int(assistant_count))
        state.revision += 1
        self.save(state)
        return active.model_copy(deep=True)

    def advance(
        self,
        conversation_id: str,
        *,
        assistant_count: int | None = None,
    ) -> ActiveRitual | None:
        state = self.load()
        active = state.active_by_conversation.get(conversation_id)
        if active is None:
            return None
        ritual = next((item for item in state.rituals if item.id == active.ritual_id), None)
        if ritual is None:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
            return None

        next_index = active.step_index + 1
        if next_index >= len(ritual.steps):
            if active.loop:
                next_index = 0
            else:
                self.clear(conversation_id)
                return None

        replacement = self._active_from_ritual(
            ritual,
            step_index=next_index,
            automatic=active.automatic,
            interval=active.interval,
            loop=active.loop,
            last_turn=assistant_count if assistant_count is not None else active.last_turn,
        )
        state.active_by_conversation[conversation_id] = replacement
        state.revision += 1
        self.save(state)
        return replacement.model_copy(deep=True)

    def maybe_advance(
        self,
        conversation_id: str,
        *,
        assistant_count: int,
    ) -> ActiveRitual | None:
        active = self.active(conversation_id)
        if active is None or not active.automatic:
            return None
        if assistant_count - active.last_turn < active.interval:
            return None
        return self.advance(conversation_id, assistant_count=assistant_count)

    def clear(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.active_by_conversation:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
