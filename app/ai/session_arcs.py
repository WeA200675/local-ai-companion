from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class ArcStage(BaseModel):
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
        return list(dict.fromkeys(" ".join(value.split())[:80] for value in values if value.strip()))[:16]


class SessionArc(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    stages: list[ArcStage] = Field(min_length=2, max_length=8)
    builtin: bool = False


class ArcProgress(BaseModel):
    arc_id: str
    stage_index: int = Field(default=0, ge=0)


class ActiveArc(BaseModel):
    arc_id: str
    arc_name: str
    stage_index: int
    stage_count: int
    stage_name: str
    instruction: str
    style_tags: list[str] = Field(default_factory=list)

    def prompt_text(self) -> str:
        return (
            f"{self.arc_name} — phase {self.stage_index + 1}/{self.stage_count}, "
            f"{self.stage_name}: {self.instruction}"
        )


class SessionArcState(BaseModel):
    arcs: list[SessionArc] = Field(default_factory=list)
    progress_by_conversation: dict[str, ArcProgress] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_session_arcs() -> list[SessionArc]:
    return [
        SessionArc(
            id="tension-curve",
            name="Spannungsbogen",
            description="Von ruhigem Einstieg über Verdichtung zu einem klaren Fokus und anschließendem Nachklang.",
            builtin=True,
            stages=[
                ArcStage(
                    name="Ankommen",
                    instruction="Start measured and observant. Establish mood and invite a clear direction without rushing.",
                    style_tags=["measured", "observant", "slow build"],
                ),
                ArcStage(
                    name="Verdichten",
                    instruction="Increase focus and initiative. Reuse established details so the exchange feels intentionally connected.",
                    style_tags=["focused", "building tension", "continuity"],
                ),
                ArcStage(
                    name="Fokus",
                    instruction="Make the current beat feel decisive and vivid. Prefer strong choices and concise reactions over exposition.",
                    style_tags=["decisive", "vivid", "close-up"],
                ),
                ArcStage(
                    name="Nachklang",
                    instruction="Ease the pace and reflect on the immediate exchange with continuity, warmth, and small concrete details.",
                    style_tags=["calm", "afterglow", "reflective"],
                ),
            ],
        ),
        SessionArc(
            id="mystery-night",
            name="Mystery Night",
            description="Ein kleiner geheimnisvoller Faden mit Hinweis, Wendung und Auflösung.",
            builtin=True,
            stages=[
                ArcStage(
                    name="Hinweis",
                    instruction="Introduce one subtle unexplained detail that fits the current setting and creates curiosity.",
                    style_tags=["mysterious", "subtle clue"],
                ),
                ArcStage(
                    name="Wendung",
                    instruction="Reframe the earlier clue in an unexpected but continuity-safe way. Keep the user involved in the discovery.",
                    style_tags=["twist", "suspense", "interactive"],
                ),
                ArcStage(
                    name="Auflösung",
                    instruction="Resolve the small mystery cleanly, then leave one optional thread open for future continuation.",
                    style_tags=["reveal", "closure", "continuity"],
                ),
            ],
        ),
        SessionArc(
            id="playful-pulse",
            name="Verspielter Puls",
            description="Kurze, wechselnde Beats aus Herausforderung, Reaktion und ruhigerem Reset.",
            builtin=True,
            stages=[
                ArcStage(
                    name="Funke",
                    instruction="Use playful wit and a light challenge. Keep the turn short enough to invite an immediate response.",
                    style_tags=["playful", "witty", "spark"],
                ),
                ArcStage(
                    name="Ping-Pong",
                    instruction="Favor quick conversational back-and-forth and responsive initiative rather than long narration.",
                    style_tags=["interactive", "quick beats", "responsive"],
                ),
                ArcStage(
                    name="Reset",
                    instruction="Slow down slightly, acknowledge what just worked, and create room for the next direction.",
                    style_tags=["reset", "calm", "attentive"],
                ),
            ],
        ),
        SessionArc(
            id="cinematic-sequence",
            name="Cinematic Sequence",
            description="Eine Folge aus Establishing Shot, Nahaufnahme, visueller Verschiebung und Fade-out.",
            builtin=True,
            stages=[
                ArcStage(
                    name="Establishing",
                    instruction="Frame the environment first with two or three concrete visual anchors.",
                    style_tags=["wide frame", "establishing shot", "cinematic"],
                ),
                ArcStage(
                    name="Close-up",
                    instruction="Shift attention to posture, expression, hands, materials, or another close visual detail.",
                    style_tags=["close-up", "detail", "portrait"],
                ),
                ArcStage(
                    name="Shift",
                    instruction="Change one visual variable such as angle, lighting, position, or distance while preserving identity and scene continuity.",
                    style_tags=["camera shift", "dynamic composition", "continuity"],
                ),
                ArcStage(
                    name="Fade",
                    instruction="End this sequence with a quieter image or line that feels complete but leaves a natural continuation point.",
                    style_tags=["fade out", "quiet frame", "closure"],
                ),
            ],
        ),
    ]


class SessionArcRepository:
    STATE_KEY = "session_arcs"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(SessionArcState(arcs=default_session_arcs()))

    def load(self) -> SessionArcState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return SessionArcState(arcs=default_session_arcs())
        try:
            state = SessionArcState.model_validate_json(payload)
        except ValueError:
            return SessionArcState(arcs=default_session_arcs())
        if not state.arcs:
            state.arcs = default_session_arcs()
        valid_ids = {arc.id for arc in state.arcs}
        state.progress_by_conversation = {
            key: value
            for key, value in state.progress_by_conversation.items()
            if value.arc_id in valid_ids
        }
        return state

    def save(self, state: SessionArcState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_arcs(self) -> list[SessionArc]:
        return [arc.model_copy(deep=True) for arc in self.load().arcs]

    def active(self, conversation_id: str) -> ActiveArc | None:
        state = self.load()
        progress = state.progress_by_conversation.get(conversation_id)
        if progress is None:
            return None
        arc = next((item for item in state.arcs if item.id == progress.arc_id), None)
        if arc is None:
            return None
        index = min(progress.stage_index, len(arc.stages) - 1)
        stage = arc.stages[index]
        return ActiveArc(
            arc_id=arc.id,
            arc_name=arc.name,
            stage_index=index,
            stage_count=len(arc.stages),
            stage_name=stage.name,
            instruction=stage.instruction,
            style_tags=list(stage.style_tags),
        )

    def activate(self, conversation_id: str, arc_id: str) -> ActiveArc:
        state = self.load()
        arc = next((item for item in state.arcs if item.id == arc_id), None)
        if arc is None:
            raise KeyError(f"Session arc {arc_id!r} not found")
        state.progress_by_conversation[conversation_id] = ArcProgress(arc_id=arc.id, stage_index=0)
        state.revision += 1
        self.save(state)
        active = self.active(conversation_id)
        assert active is not None
        return active

    def advance(self, conversation_id: str) -> ActiveArc | None:
        state = self.load()
        progress = state.progress_by_conversation.get(conversation_id)
        if progress is None:
            return None
        arc = next((item for item in state.arcs if item.id == progress.arc_id), None)
        if arc is None:
            state.progress_by_conversation.pop(conversation_id, None)
            self.save(state)
            return None
        if progress.stage_index + 1 >= len(arc.stages):
            state.progress_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
            return None
        progress.stage_index += 1
        state.revision += 1
        self.save(state)
        return self.active(conversation_id)

    def clear(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.progress_by_conversation:
            state.progress_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)
