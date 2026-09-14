from __future__ import annotations

import random

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class MoodGrade(BaseModel):
    """Temporary color/lighting grade used by chat and local media planning."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    prompt: str = Field(min_length=1, max_length=500)
    style_tags: list[str] = Field(default_factory=list, max_length=16)
    builtin: bool = False

    @field_validator("id", "name", "description", "prompt", mode="before")
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
        return f"{self.name}: {self.prompt}"


class DetailAccent(BaseModel):
    """Small temporary prop/material/detail cue that can freshen a scene."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    prompt: str = Field(min_length=1, max_length=500)
    style_tags: list[str] = Field(default_factory=list, max_length=16)
    builtin: bool = False

    @field_validator("id", "name", "description", "prompt", mode="before")
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
        return f"{self.name}: {self.prompt}"


class CreativeAccentState(BaseModel):
    active_by_conversation: dict[str, str] = Field(default_factory=dict)
    recent_ids: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)


def default_mood_grades() -> list[MoodGrade]:
    return [
        MoodGrade(
            id="amber-noir",
            name="Amber Noir",
            description="Warme Highlights, tiefe Schatten und elegante Noir-Wirkung.",
            prompt="warm amber practical highlights, deep neutral shadows, restrained cinematic contrast",
            style_tags=["amber noir", "warm highlights", "cinematic contrast"],
            builtin=True,
        ),
        MoodGrade(
            id="cool-steel",
            name="Cool Steel",
            description="Kühle, klare Bildwirkung mit metallischer Präzision.",
            prompt="cool steel-toned light, crisp separation, restrained saturation, polished editorial finish",
            style_tags=["cool steel", "crisp light", "editorial"],
            builtin=True,
        ),
        MoodGrade(
            id="silver-monochrome",
            name="Silver Monochrome",
            description="Fast monochrom, silbrig und grafisch.",
            prompt="near-monochrome silver tonal range, sculpted light, graphic shadow, fine material contrast",
            style_tags=["silver monochrome", "graphic shadow", "fine contrast"],
            builtin=True,
        ),
        MoodGrade(
            id="neon-night",
            name="Neon Night",
            description="Zurückhaltende Neon-Kanten und dunkle Nachtatmosphäre.",
            prompt="subtle neon edge accents, dark ambient fill, controlled reflections, night photography mood",
            style_tags=["neon night", "edge light", "reflections"],
            builtin=True,
        ),
        MoodGrade(
            id="soft-film",
            name="Soft Film",
            description="Weichere Filmästhetik mit sanften Übergängen.",
            prompt="soft filmic contrast, gentle highlight rolloff, subtle grain impression, natural skin and material texture",
            style_tags=["soft film", "gentle contrast", "filmic"],
            builtin=True,
        ),
        MoodGrade(
            id="editorial-punch",
            name="Editorial Punch",
            description="Knackiger Fashion-Look mit klaren Formen.",
            prompt="clean editorial contrast, decisive highlights, structured shadows, polished fashion photography finish",
            style_tags=["editorial punch", "fashion lighting", "structured contrast"],
            builtin=True,
        ),
        MoodGrade(
            id="faded-vintage",
            name="Faded Vintage",
            description="Leicht entsättigter, analog wirkender Retro-Ton.",
            prompt="slightly faded vintage tonal curve, muted saturation, gentle grain impression, understated retro mood",
            style_tags=["faded vintage", "muted", "retro film"],
            builtin=True,
        ),
    ]


def default_detail_accents() -> list[DetailAccent]:
    return [
        DetailAccent(
            id="glove-buckle",
            name="Gloves & Buckle",
            description="Hand-, Handschuh- und Verschlussdetails als kleiner visueller Akzent.",
            prompt="include a tasteful glove or buckle detail with readable hands and material texture",
            style_tags=["gloves", "buckle detail", "material texture"],
            builtin=True,
        ),
        DetailAccent(
            id="rain-glass",
            name="Rain on Glass",
            description="Regenperlen und Spiegelungen als atmosphärisches Detail.",
            prompt="use rain beads on glass and controlled reflections as a secondary visual detail",
            style_tags=["rain glass", "reflections", "atmospheric detail"],
            builtin=True,
        ),
        DetailAccent(
            id="chair-geometry",
            name="Chair Geometry",
            description="Stuhl oder Sessel als klare Form im Bildaufbau.",
            prompt="use a chair or lounge seat as a deliberate compositional shape without hiding the subject",
            style_tags=["chair geometry", "seated composition", "clean lines"],
            builtin=True,
        ),
        DetailAccent(
            id="mirror-trace",
            name="Mirror Trace",
            description="Eine kontrollierte Spiegelkante oder Teilreflexion.",
            prompt="include one controlled mirror edge or partial reflection while keeping a single clear primary identity",
            style_tags=["mirror trace", "partial reflection", "identity clarity"],
            builtin=True,
        ),
        DetailAccent(
            id="footwear-reflection",
            name="Footwear Reflection",
            description="Schuhe oder Boots plus Bodenreflexion als Fashion-Detail.",
            prompt="keep full-body styling readable and include boots or heels with a subtle floor reflection",
            style_tags=["footwear", "boots", "heels", "floor reflection"],
            builtin=True,
        ),
        DetailAccent(
            id="metal-accent",
            name="Metal Accent",
            description="Kleine Metall- oder Schmuckakzente mit klaren Highlights.",
            prompt="add a restrained metallic accessory or hardware accent with clean specular highlights",
            style_tags=["metal accent", "hardware detail", "specular highlight"],
            builtin=True,
        ),
        DetailAccent(
            id="velvet-drape",
            name="Velvet Drape",
            description="Textur im Hintergrund ohne die Figur zu überdecken.",
            prompt="use a small velvet or heavy-fabric drape as a textural background detail",
            style_tags=["velvet", "fabric texture", "background detail"],
            builtin=True,
        ),
        DetailAccent(
            id="hand-prop",
            name="Hand Prop",
            description="Ein neutrales kleines Objekt sorgt für neue Handpositionen.",
            prompt="place a small neutral prop in one hand to create a natural gesture and avoid repeated hand poses",
            style_tags=["hand prop", "gesture variation", "hands visible"],
            builtin=True,
        ),
    ]


class _BaseAccentRepository:
    STATE_KEY = ""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load_state(self) -> CreativeAccentState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return CreativeAccentState()
        try:
            return CreativeAccentState.model_validate_json(payload)
        except ValueError:
            return CreativeAccentState()

    def save_state(self, state: CreativeAccentState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def active_id(self, conversation_id: str) -> str | None:
        return self.load_state().active_by_conversation.get(conversation_id)

    def _set_active_id(self, conversation_id: str, item_id: str | None) -> None:
        state = self.load_state()
        if item_id:
            state.active_by_conversation[conversation_id] = item_id
            state.recent_ids = [value for value in state.recent_ids if value != item_id]
            state.recent_ids.append(item_id)
            state.recent_ids = state.recent_ids[-10:]
        else:
            state.active_by_conversation.pop(conversation_id, None)
        state.revision += 1
        self.save_state(state)

    def recent_ids(self) -> list[str]:
        return list(self.load_state().recent_ids)


class MoodGradeRepository(_BaseAccentRepository):
    STATE_KEY = "mood_grades"

    def list_grades(self) -> list[MoodGrade]:
        return [item.model_copy(deep=True) for item in default_mood_grades()]

    def get(self, grade_id: str) -> MoodGrade | None:
        clean = grade_id.strip()
        return next((item for item in self.list_grades() if item.id == clean), None)

    def active(self, conversation_id: str) -> MoodGrade | None:
        item_id = self.active_id(conversation_id)
        return self.get(item_id) if item_id else None

    def set_active(self, conversation_id: str, grade_id: str | None) -> MoodGrade | None:
        if not grade_id:
            self._set_active_id(conversation_id, None)
            return None
        grade = self.get(grade_id)
        if grade is None:
            raise KeyError(f"Mood grade {grade_id!r} not found")
        self._set_active_id(conversation_id, grade.id)
        return grade.model_copy(deep=True)

    def draw(self, conversation_id: str, *, rng: random.Random | None = None) -> MoodGrade:
        items = self.list_grades()
        recent = set(self.recent_ids()[-4:])
        pool = [item for item in items if item.id not in recent] or items
        chooser = rng or random.SystemRandom()
        selected = chooser.choice(pool)
        result = self.set_active(conversation_id, selected.id)
        assert result is not None
        return result


class DetailAccentRepository(_BaseAccentRepository):
    STATE_KEY = "detail_accents"

    def list_accents(self) -> list[DetailAccent]:
        return [item.model_copy(deep=True) for item in default_detail_accents()]

    def get(self, accent_id: str) -> DetailAccent | None:
        clean = accent_id.strip()
        return next((item for item in self.list_accents() if item.id == clean), None)

    def active(self, conversation_id: str) -> DetailAccent | None:
        item_id = self.active_id(conversation_id)
        return self.get(item_id) if item_id else None

    def set_active(self, conversation_id: str, accent_id: str | None) -> DetailAccent | None:
        if not accent_id:
            self._set_active_id(conversation_id, None)
            return None
        accent = self.get(accent_id)
        if accent is None:
            raise KeyError(f"Detail accent {accent_id!r} not found")
        self._set_active_id(conversation_id, accent.id)
        return accent.model_copy(deep=True)

    def draw(self, conversation_id: str, *, rng: random.Random | None = None) -> DetailAccent:
        items = self.list_accents()
        recent = set(self.recent_ids()[-4:])
        pool = [item for item in items if item.id not in recent] or items
        chooser = rng or random.SystemRandom()
        selected = chooser.choice(pool)
        result = self.set_active(conversation_id, selected.id)
        assert result is not None
        return result
