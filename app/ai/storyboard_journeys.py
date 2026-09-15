from __future__ import annotations

import random

from pydantic import BaseModel, Field, field_validator

from app.ai.scenario_seeds import (
    PreviousCreativeState,
    ScenarioSeedEngine,
    ScenarioSeedSelection,
)
from app.memory.store import StateStore


class StoryboardChapter(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=700)
    scenario_template_id: str = Field(min_length=1, max_length=80)
    style_tags: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("name", "instruction", "scenario_template_id", mode="before")
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


class StoryboardJourney(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    chapters: list[StoryboardChapter] = Field(min_length=2, max_length=8)
    builtin: bool = False


class ActiveStoryboardJourney(BaseModel):
    journey_id: str
    journey_name: str
    description: str = ""
    chapter_index: int = Field(ge=0)
    chapter_count: int = Field(ge=1)
    chapter_name: str
    chapter_instruction: str
    scenario_template_id: str
    style_tags: list[str] = Field(default_factory=list)
    automatic: bool = True
    replies_per_chapter: int = Field(default=3, ge=1, le=12)
    automatic_sequences: bool = True
    last_turn: int = Field(default=0, ge=0)
    random_seed: int = Field(default=0, ge=0)
    completed: bool = False
    origin_state: PreviousCreativeState
    prior_scenario_seed: ScenarioSeedSelection | None = None

    def prompt_text(self) -> str:
        state = "completed" if self.completed else "active"
        return (
            f"{self.journey_name} — chapter {self.chapter_index + 1}/{self.chapter_count}, "
            f"{self.chapter_name} ({state}): {self.chapter_instruction}"
        )


class StoryboardJourneyState(BaseModel):
    active_by_conversation: dict[str, ActiveStoryboardJourney] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_storyboard_journeys() -> list[StoryboardJourney]:
    return [
        StoryboardJourney(
            id="rain-to-dawn",
            name="Rain to Dawn",
            description="Eine längere filmische Nacht, die von Regen und Rätsel über Bewegung zu einem ruhigen, klaren Abschluss führt.",
            builtin=True,
            chapters=[
                StoryboardChapter(
                    name="Rain Arrival",
                    instruction="Establish the night slowly through reflections, presence, and a clear sense of place. Keep the exchange responsive rather than exposition-heavy.",
                    scenario_template_id="rain-noir",
                    style_tags=["slow build", "rain reflections", "cinematic continuity"],
                ),
                StoryboardChapter(
                    name="Mirror Clue",
                    instruction="Narrow the scene around one small mystery or visual clue. Let earlier details matter and invite the user's direction before resolving anything.",
                    scenario_template_id="mirror-mystery",
                    style_tags=["mystery", "mirror composition", "selective reveal"],
                ),
                StoryboardChapter(
                    name="Night in Motion",
                    instruction="Increase movement, camera variation, and decisive pacing while preserving established identity, location logic, and user boundaries.",
                    scenario_template_id="motion-night",
                    style_tags=["movement", "dynamic framing", "night energy"],
                ),
                StoryboardChapter(
                    name="First Light",
                    instruction="Reduce visual clutter and let the session settle into a deliberate closing phase with continuity, space, and an open next move.",
                    scenario_template_id="minimal-focus",
                    style_tags=["first light", "minimal focus", "open ending"],
                ),
            ],
        ),
        StoryboardJourney(
            id="studio-presence",
            name="Studio Presence",
            description="Kontrollierte Studio-Präsenz mit Fokuswechseln, Spiegelmoment und einem weicheren Ausklang.",
            builtin=True,
            chapters=[
                StoryboardChapter(
                    name="Commanding Frame",
                    instruction="Begin with composed, confident presence and clear visual geometry. Any power-play tone must follow the user's current direction and configured intimacy boundaries.",
                    scenario_template_id="studio-command",
                    style_tags=["composed presence", "editorial geometry", "controlled pacing"],
                ),
                StoryboardChapter(
                    name="Narrow Focus",
                    instruction="Reduce the scene to a few deliberate details, shorter beats, and stronger attention to expression, posture, and material continuity.",
                    scenario_template_id="minimal-focus",
                    style_tags=["close focus", "precise detail", "short beats"],
                ),
                StoryboardChapter(
                    name="Mirror Shift",
                    instruction="Reframe the established dynamic through reflection and a new angle without changing identity, permissions, or the user's stated boundaries.",
                    scenario_template_id="mirror-mystery",
                    style_tags=["mirror shift", "reframing", "continuity"],
                ),
                StoryboardChapter(
                    name="Lounge Release",
                    instruction="Ease the formal studio energy into a warmer, more conversational afterbeat while preserving the session's established tone.",
                    scenario_template_id="soft-lounge",
                    style_tags=["warm release", "afterbeat", "responsive"],
                ),
            ],
        ),
        StoryboardJourney(
            id="velvet-afterhours",
            name="Velvet Afterhours",
            description="Retro-Editorial wird schrittweise lockerer, geheimnisvoller und endet in einer reduzierten Schlusskomposition.",
            builtin=True,
            chapters=[
                StoryboardChapter(
                    name="Polished Opening",
                    instruction="Open with a polished retro-editorial rhythm and a few memorable visual anchors rather than a dense description.",
                    scenario_template_id="retro-afterhours",
                    style_tags=["retro editorial", "polished", "visual anchors"],
                ),
                StoryboardChapter(
                    name="Lounge Pulse",
                    instruction="Make the interaction more relaxed and responsive, using small gestures and conversational beats to connect the established details.",
                    scenario_template_id="soft-lounge",
                    style_tags=["lounge", "responsive dialogue", "small gestures"],
                ),
                StoryboardChapter(
                    name="Hidden Reflection",
                    instruction="Introduce one continuity-safe visual or conversational mystery and let it reshape the framing without forcing a reveal.",
                    scenario_template_id="mirror-mystery",
                    style_tags=["hidden reflection", "mystery beat", "continuity-safe"],
                ),
                StoryboardChapter(
                    name="Last Frame",
                    instruction="Close the journey with fewer elements, one strong focal point, and enough openness for the user to continue in any direction.",
                    scenario_template_id="minimal-focus",
                    style_tags=["last frame", "single focus", "open continuation"],
                ),
            ],
        ),
        StoryboardJourney(
            id="mystery-loop",
            name="Mystery Loop",
            description="Hinweis, Regenverdichtung, kontrollierter Studio-Wechsel und warmer Nachklang als längerer Spannungsbogen.",
            builtin=True,
            chapters=[
                StoryboardChapter(
                    name="The Clue",
                    instruction="Plant one modest unexplained detail and keep it available in the background while the normal conversation continues.",
                    scenario_template_id="mirror-mystery",
                    style_tags=["clue", "subtle suspense", "interactive"],
                ),
                StoryboardChapter(
                    name="Weather Turns",
                    instruction="Deepen atmosphere through rain, reflections, and tighter pacing while reusing the original clue instead of adding unrelated mysteries.",
                    scenario_template_id="rain-noir",
                    style_tags=["rain tension", "reflections", "connected detail"],
                ),
                StoryboardChapter(
                    name="Controlled Reveal",
                    instruction="Move toward a clean, bounded reveal with strong presence and deliberate staging. Keep the user's current request more important than the planned beat.",
                    scenario_template_id="studio-command",
                    style_tags=["controlled reveal", "decisive", "user-led"],
                ),
                StoryboardChapter(
                    name="Afterbeat",
                    instruction="Let the reveal breathe, soften the pace, and leave one optional thread rather than immediately starting another mystery.",
                    scenario_template_id="soft-lounge",
                    style_tags=["afterbeat", "soft landing", "optional thread"],
                ),
            ],
        ),
        StoryboardJourney(
            id="cinematic-presence",
            name="Cinematic Presence",
            description="Von minimaler Blickführung über Studio-Präsenz und Bewegung zu einem stilisierten Afterhours-Finale.",
            builtin=True,
            chapters=[
                StoryboardChapter(
                    name="Quiet Focus",
                    instruction="Start restrained and visually legible, with one focal point and enough space for the user's first choices to shape the session.",
                    scenario_template_id="minimal-focus",
                    style_tags=["quiet focus", "legible frame", "user space"],
                ),
                StoryboardChapter(
                    name="Presence Builds",
                    instruction="Increase confidence, initiative, and visual structure without turning the chapter plan into an obligation or overriding current boundaries.",
                    scenario_template_id="studio-command",
                    style_tags=["building presence", "initiative", "structured frame"],
                ),
                StoryboardChapter(
                    name="Motion Beat",
                    instruction="Use stronger spatial changes and motion-friendly composition while keeping character identity and scene geography continuous.",
                    scenario_template_id="motion-night",
                    style_tags=["motion beat", "spatial change", "continuity"],
                ),
                StoryboardChapter(
                    name="Afterhours Finale",
                    instruction="Resolve the sequence into a stylish, calmer final chapter that can either close naturally or become a new user-led beginning.",
                    scenario_template_id="retro-afterhours",
                    style_tags=["afterhours", "finale", "user-led continuation"],
                ),
            ],
        ),
    ]


class StoryboardJourneyRepository:
    STATE_KEY = "storyboard_journeys"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> StoryboardJourneyState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return StoryboardJourneyState()
        try:
            return StoryboardJourneyState.model_validate_json(payload)
        except ValueError:
            return StoryboardJourneyState()

    def save(self, state: StoryboardJourneyState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def active(self, conversation_id: str) -> ActiveStoryboardJourney | None:
        value = self.load().active_by_conversation.get(conversation_id)
        return value.model_copy(deep=True) if value is not None else None

    def set_active(self, conversation_id: str, active: ActiveStoryboardJourney) -> None:
        state = self.load()
        state.active_by_conversation[conversation_id] = active.model_copy(deep=True)
        state.revision += 1
        self.save(state)

    def clear(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.active_by_conversation:
            state.active_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)


class StoryboardJourneyEngine:
    """Coordinate longer temporary dramaturgy using existing reversible session seeds."""

    def __init__(
        self,
        repository: StoryboardJourneyRepository,
        scenario_engine: ScenarioSeedEngine,
    ) -> None:
        self.repository = repository
        self.scenario_engine = scenario_engine

    def journeys(self) -> list[StoryboardJourney]:
        return [item.model_copy(deep=True) for item in default_storyboard_journeys()]

    def journey(self, journey_id: str) -> StoryboardJourney | None:
        clean = journey_id.strip()
        return next((item for item in self.journeys() if item.id == clean), None)

    @staticmethod
    def _chapter_seed(base_seed: int, chapter_index: int) -> int:
        return (int(base_seed) + ((chapter_index + 1) * 1_000_003)) % (2**31)

    def _annotate_seed(
        self,
        conversation_id: str,
        selection: ScenarioSeedSelection,
        journey: StoryboardJourney,
        chapter_index: int,
    ) -> ScenarioSeedSelection:
        chapter = journey.chapters[chapter_index]
        updated = selection.model_copy(deep=True)
        updated.layer_summary["Journey"] = f"{journey.name} · {chapter.name}"
        updated.compatibility_notes = list(updated.compatibility_notes) + [
            f"Storyboard-Kapitel {chapter_index + 1}/{len(journey.chapters)} koordiniert diesen Session-Seed."
        ]
        self.scenario_engine.repository.set_active(conversation_id, updated)
        return updated

    def start(
        self,
        conversation_id: str,
        journey_id: str,
        *,
        automatic: bool = True,
        replies_per_chapter: int = 3,
        automatic_sequences: bool = True,
        assistant_count: int = 0,
        seed: int | None = None,
    ) -> ActiveStoryboardJourney:
        journey = self.journey(journey_id)
        if journey is None:
            raise KeyError(f"Storyboard journey {journey_id!r} not found")

        base_seed = int(seed) if seed is not None else random.SystemRandom().randrange(0, 2**31)
        prior_seed = self.scenario_engine.repository.active(conversation_id)
        chapter = journey.chapters[0]
        selection = self.scenario_engine.generate(
            conversation_id,
            template_id=chapter.scenario_template_id,
            include_evolution=True,
            include_ritual=True,
            automatic_sequences=automatic_sequences,
            assistant_count=assistant_count,
            seed=self._chapter_seed(base_seed, 0),
        )
        self._annotate_seed(conversation_id, selection, journey, 0)
        active = ActiveStoryboardJourney(
            journey_id=journey.id,
            journey_name=journey.name,
            description=journey.description,
            chapter_index=0,
            chapter_count=len(journey.chapters),
            chapter_name=chapter.name,
            chapter_instruction=chapter.instruction,
            scenario_template_id=chapter.scenario_template_id,
            style_tags=list(chapter.style_tags),
            automatic=bool(automatic),
            replies_per_chapter=max(1, min(12, int(replies_per_chapter))),
            automatic_sequences=bool(automatic_sequences),
            last_turn=max(0, int(assistant_count)),
            random_seed=base_seed,
            completed=False,
            origin_state=selection.previous.model_copy(deep=True),
            prior_scenario_seed=(
                prior_seed.model_copy(deep=True) if prior_seed is not None else None
            ),
        )
        self.repository.set_active(conversation_id, active)
        return active.model_copy(deep=True)

    def configure(
        self,
        conversation_id: str,
        *,
        automatic: bool,
        replies_per_chapter: int,
        automatic_sequences: bool | None = None,
    ) -> ActiveStoryboardJourney | None:
        active = self.repository.active(conversation_id)
        if active is None:
            return None
        active.automatic = bool(automatic) and not active.completed
        active.replies_per_chapter = max(1, min(12, int(replies_per_chapter)))
        if automatic_sequences is not None:
            active.automatic_sequences = bool(automatic_sequences)
        self.repository.set_active(conversation_id, active)
        return active.model_copy(deep=True)

    def _apply_chapter(
        self,
        conversation_id: str,
        active: ActiveStoryboardJourney,
        chapter_index: int,
        *,
        assistant_count: int,
    ) -> ActiveStoryboardJourney:
        journey = self.journey(active.journey_id)
        if journey is None:
            raise KeyError(f"Storyboard journey {active.journey_id!r} not found")
        index = max(0, min(len(journey.chapters) - 1, int(chapter_index)))
        chapter = journey.chapters[index]
        selection = self.scenario_engine.generate(
            conversation_id,
            template_id=chapter.scenario_template_id,
            include_evolution=True,
            include_ritual=True,
            automatic_sequences=active.automatic_sequences,
            assistant_count=assistant_count,
            seed=self._chapter_seed(active.random_seed, index),
        )
        self._annotate_seed(conversation_id, selection, journey, index)
        active.chapter_index = index
        active.chapter_count = len(journey.chapters)
        active.chapter_name = chapter.name
        active.chapter_instruction = chapter.instruction
        active.scenario_template_id = chapter.scenario_template_id
        active.style_tags = list(chapter.style_tags)
        active.last_turn = max(0, int(assistant_count))
        active.completed = False
        self.repository.set_active(conversation_id, active)
        return active.model_copy(deep=True)

    def advance(
        self,
        conversation_id: str,
        *,
        assistant_count: int = 0,
    ) -> ActiveStoryboardJourney | None:
        active = self.repository.active(conversation_id)
        if active is None:
            return None
        if active.chapter_index + 1 >= active.chapter_count:
            active.completed = True
            active.automatic = False
            active.last_turn = max(0, int(assistant_count))
            self.repository.set_active(conversation_id, active)
            return active.model_copy(deep=True)
        return self._apply_chapter(
            conversation_id,
            active,
            active.chapter_index + 1,
            assistant_count=assistant_count,
        )

    def previous(
        self,
        conversation_id: str,
        *,
        assistant_count: int = 0,
    ) -> ActiveStoryboardJourney | None:
        active = self.repository.active(conversation_id)
        if active is None:
            return None
        if active.chapter_index <= 0:
            return active
        return self._apply_chapter(
            conversation_id,
            active,
            active.chapter_index - 1,
            assistant_count=assistant_count,
        )

    def maybe_advance(
        self,
        conversation_id: str,
        *,
        assistant_count: int,
    ) -> ActiveStoryboardJourney | None:
        active = self.repository.active(conversation_id)
        if active is None or not active.automatic or active.completed:
            return None
        if assistant_count - active.last_turn < active.replies_per_chapter:
            return None
        return self.advance(conversation_id, assistant_count=assistant_count)

    def restore_origin(self, conversation_id: str) -> bool:
        active = self.repository.active(conversation_id)
        if active is None:
            return False

        current = self.scenario_engine.repository.active(conversation_id)
        if current is None:
            current = ScenarioSeedSelection(
                template_id=active.scenario_template_id,
                template_name=active.chapter_name,
                description="Temporary storyboard restore marker",
                random_seed=self._chapter_seed(active.random_seed, active.chapter_index),
                previous=active.origin_state.model_copy(deep=True),
            )
        else:
            current = current.model_copy(deep=True)
            current.previous = active.origin_state.model_copy(deep=True)
        self.scenario_engine.repository.set_active(conversation_id, current)
        restored = self.scenario_engine.restore_previous(conversation_id)
        if active.prior_scenario_seed is not None:
            self.scenario_engine.repository.set_active(
                conversation_id,
                active.prior_scenario_seed.model_copy(deep=True),
            )
        self.repository.clear(conversation_id)
        return restored

    def detach(self, conversation_id: str) -> None:
        """Stop journey coordination but leave the current temporary creative layers intact."""

        self.repository.clear(conversation_id)
