from __future__ import annotations

import random

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class VisualMotif(BaseModel):
    """Temporary visual direction for expression, posture, and camera framing."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    expression: str = Field(default="", max_length=160)
    posture: str = Field(default="", max_length=200)
    camera: str = Field(default="", max_length=200)
    style_tags: list[str] = Field(default_factory=list, max_length=16)
    builtin: bool = False

    @field_validator("id", "name", "description", "expression", "posture", "camera", mode="before")
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
        parts = [self.name]
        if self.expression:
            parts.append(f"expression: {self.expression}")
        if self.posture:
            parts.append(f"posture: {self.posture}")
        if self.camera:
            parts.append(f"camera: {self.camera}")
        return "; ".join(parts)

    def prompt_tags(self) -> list[str]:
        tags = list(self.style_tags)
        if self.expression:
            tags.append(f"expression {self.expression}")
        if self.posture:
            tags.append(f"posture {self.posture}")
        if self.camera:
            tags.append(f"camera {self.camera}")
        return tags


class VisualMotifState(BaseModel):
    motifs: list[VisualMotif] = Field(default_factory=list)
    active_by_conversation: dict[str, str] = Field(default_factory=dict)
    recent_ids: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)


def default_visual_motifs() -> list[VisualMotif]:
    return [
        VisualMotif(
            id="steady-gaze",
            name="Steady Gaze",
            description="Ruhige Präsenz mit klarer Blickführung und kontrollierter Bildwirkung.",
            expression="calm direct eye contact, restrained confidence",
            posture="upright poised stance with relaxed shoulders and hands visible",
            camera="waist-up portrait with a subtle low angle and clean negative space",
            style_tags=["direct gaze", "poised", "controlled portrait"],
            builtin=True,
        ),
        VisualMotif(
            id="over-shoulder-noir",
            name="Over-Shoulder Noir",
            description="Dreiviertel-Drehung für mehr Spannung und weniger frontale Wiederholung.",
            expression="composed over-shoulder glance",
            posture="body turned away slightly while the face returns toward camera",
            camera="three-quarter over-shoulder framing with strong shadow separation",
            style_tags=["three-quarter", "over shoulder", "noir framing"],
            builtin=True,
        ),
        VisualMotif(
            id="seated-command",
            name="Seated Presence",
            description="Sitzende, souveräne Inszenierung mit sichtbarer Körpersprache.",
            expression="focused composed expression",
            posture="confident seated posture, balanced asymmetry, hands naturally placed",
            camera="medium full shot near eye level with deliberate geometry",
            style_tags=["seated portrait", "composed", "structured pose"],
            builtin=True,
        ),
        VisualMotif(
            id="material-detail",
            name="Material Detail",
            description="Nahere Bildsprache für Hände, Materialien, Accessoires und Outfit-Details.",
            expression="subtle knowing expression",
            posture="natural poised stance with one hand interacting with clothing or an accessory",
            camera="detail-led crop that keeps face identity readable while emphasizing material texture",
            style_tags=["material detail", "hands visible", "texture", "fashion detail"],
            builtin=True,
        ),
        VisualMotif(
            id="mirror-offset",
            name="Mirror Offset",
            description="Asymmetrische Spiegelkomposition ohne Verlust der Character-Identität.",
            expression="quiet confident expression",
            posture="slight turn with asymmetric weight distribution",
            camera="off-axis mirror composition with one clear primary face and controlled reflection",
            style_tags=["mirror", "off-axis", "reflection", "identity continuity"],
            builtin=True,
        ),
        VisualMotif(
            id="rain-silhouette",
            name="Rain Silhouette",
            description="Breiteres Motiv mit Silhouette, Fensterlicht und zurückhaltender Mimik.",
            expression="subtle half-smile or thoughtful gaze",
            posture="full standing silhouette near a window with a clean readable outline",
            camera="wide environmental frame using rain reflections and negative space",
            style_tags=["silhouette", "rain", "wide frame", "reflections"],
            builtin=True,
        ),
        VisualMotif(
            id="playful-lean",
            name="Playful Lean",
            description="Lockerere Bilddynamik als Gegenpol zu strengeren, statischen Posen.",
            expression="knowing playful smile",
            posture="relaxed lean against furniture or wall with natural asymmetry",
            camera="medium close-up with a slight diagonal composition",
            style_tags=["playful", "relaxed pose", "diagonal composition"],
            builtin=True,
        ),
        VisualMotif(
            id="footwear-frame",
            name="Footwear Frame",
            description="Ganzkörper-Komposition, die Styling und Schuhe sichtbar hält, ohne die Identität zu verlieren.",
            expression="self-assured neutral-to-playful expression",
            posture="stable full-body stance with clear leg line and balanced weight",
            camera="full-body fashion frame with boots or heels clearly visible and the face still readable",
            style_tags=["full body", "fashion footwear", "boots", "heels", "clean anatomy"],
            builtin=True,
        ),
    ]


class VisualMotifRepository:
    STATE_KEY = "visual_motifs"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(VisualMotifState(motifs=default_visual_motifs()))

    def load(self) -> VisualMotifState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return VisualMotifState(motifs=default_visual_motifs())
        try:
            state = VisualMotifState.model_validate_json(payload)
        except ValueError:
            return VisualMotifState(motifs=default_visual_motifs())
        if not state.motifs:
            state.motifs = default_visual_motifs()
        valid_ids = {motif.id for motif in state.motifs}
        state.active_by_conversation = {
            key: value for key, value in state.active_by_conversation.items() if value in valid_ids
        }
        state.recent_ids = [item for item in state.recent_ids if item in valid_ids][-8:]
        return state

    def save(self, state: VisualMotifState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_motifs(self) -> list[VisualMotif]:
        return [motif.model_copy(deep=True) for motif in self.load().motifs]

    def get(self, motif_id: str) -> VisualMotif | None:
        clean = motif_id.strip()
        return next(
            (motif.model_copy(deep=True) for motif in self.load().motifs if motif.id == clean),
            None,
        )

    def active(self, conversation_id: str) -> VisualMotif | None:
        state = self.load()
        motif_id = state.active_by_conversation.get(conversation_id)
        if not motif_id:
            return None
        return next(
            (motif.model_copy(deep=True) for motif in state.motifs if motif.id == motif_id),
            None,
        )

    def set_active(self, conversation_id: str, motif_id: str | None) -> VisualMotif | None:
        state = self.load()
        if not motif_id:
            if conversation_id in state.active_by_conversation:
                state.active_by_conversation.pop(conversation_id, None)
                state.revision += 1
                self.save(state)
            return None
        motif = next((item for item in state.motifs if item.id == motif_id), None)
        if motif is None:
            raise KeyError(f"Visual motif {motif_id!r} not found")
        state.active_by_conversation[conversation_id] = motif.id
        state.recent_ids = [item for item in state.recent_ids if item != motif.id]
        state.recent_ids.append(motif.id)
        state.recent_ids = state.recent_ids[-8:]
        state.revision += 1
        self.save(state)
        return motif.model_copy(deep=True)

    def draw(
        self,
        conversation_id: str,
        *,
        rng: random.Random | None = None,
    ) -> VisualMotif:
        state = self.load()
        recent = set(state.recent_ids[-4:])
        pool = [motif for motif in state.motifs if motif.id not in recent] or state.motifs
        chooser = rng or random.SystemRandom()
        selected = chooser.choice(pool)
        result = self.set_active(conversation_id, selected.id)
        assert result is not None
        return result
