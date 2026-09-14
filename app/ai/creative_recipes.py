from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.ai.look_presets import LookPresetRepository
from app.ai.scene_mixer import SceneMix, SceneMixerRepository
from app.ai.session_arcs import SessionArcRepository
from app.ai.variety import VarietyRepository
from app.ai.visual_motifs import VisualMotifRepository
from app.memory.store import StateStore


class CreativeRecipe(BaseModel):
    """Reusable bundle of temporary creative layers.

    Recipes never contain persona traits, Core Memory, adaptive memory, or stable
    Character Studio identity. They only restore temporary creative context.
    """

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    look_id: str | None = None
    variety_id: str | None = None
    arc_id: str | None = None
    visual_motif_id: str | None = None
    scene_mix: SceneMix | None = None
    draw_scene_mix: bool = False
    builtin: bool = False

    @field_validator("id", "name", "description", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        return " ".join(str(value or "").split())


class CreativeRecipeState(BaseModel):
    recipes: list[CreativeRecipe] = Field(default_factory=list)
    last_applied_by_conversation: dict[str, str] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


def default_creative_recipes() -> list[CreativeRecipe]:
    return [
        CreativeRecipe(
            id="noir-control",
            name="Noir Control",
            description="Dunkler, kontrollierter Look mit ruhigem Spannungsaufbau und klarer Präsenz.",
            look_id="noir-latex",
            variety_id="confident-presence",
            arc_id="tension-curve",
            visual_motif_id="steady-gaze",
            draw_scene_mix=True,
            builtin=True,
        ),
        CreativeRecipe(
            id="playful-editorial",
            name="Playful Editorial",
            description="Leichtere Dynamik, glamouröse Bildsprache und wechselnde kurze Beats.",
            look_id="retro-glam",
            variety_id="playful-spark",
            arc_id="playful-pulse",
            visual_motif_id="playful-lean",
            draw_scene_mix=True,
            builtin=True,
        ),
        CreativeRecipe(
            id="rain-mystery",
            name="Rain Mystery",
            description="Regen-Noir, kleine Geheimnisse und breitere filmische Frames.",
            look_id="rainy-noir",
            variety_id="mystery-beat",
            arc_id="mystery-night",
            visual_motif_id="rain-silhouette",
            draw_scene_mix=True,
            builtin=True,
        ),
        CreativeRecipe(
            id="studio-detail",
            name="Studio Detail",
            description="Reduziertes Studio mit Material-, Hand- und Outfit-Details in wechselnden Einstellungen.",
            look_id="studio-minimal",
            variety_id="visual-frame",
            arc_id="cinematic-sequence",
            visual_motif_id="material-detail",
            draw_scene_mix=True,
            builtin=True,
        ),
    ]


class CreativeRecipeRepository:
    STATE_KEY = "creative_recipes"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        if self.store._load_app_state(self.STATE_KEY) is None:  # noqa: SLF001
            self.save(CreativeRecipeState(recipes=default_creative_recipes()))

    def load(self) -> CreativeRecipeState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return CreativeRecipeState(recipes=default_creative_recipes())
        try:
            state = CreativeRecipeState.model_validate_json(payload)
        except ValueError:
            return CreativeRecipeState(recipes=default_creative_recipes())
        if not state.recipes:
            state.recipes = default_creative_recipes()
        valid_ids = {recipe.id for recipe in state.recipes}
        state.last_applied_by_conversation = {
            key: value
            for key, value in state.last_applied_by_conversation.items()
            if value in valid_ids
        }
        return state

    def save(self, state: CreativeRecipeState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_recipes(self) -> list[CreativeRecipe]:
        return sorted(
            (recipe.model_copy(deep=True) for recipe in self.load().recipes),
            key=lambda item: (not item.builtin, item.name.casefold()),
        )

    def get(self, recipe_id: str) -> CreativeRecipe | None:
        clean = recipe_id.strip()
        return next(
            (recipe.model_copy(deep=True) for recipe in self.load().recipes if recipe.id == clean),
            None,
        )

    def last_applied(self, conversation_id: str) -> CreativeRecipe | None:
        recipe_id = self.load().last_applied_by_conversation.get(conversation_id)
        return self.get(recipe_id) if recipe_id else None

    def upsert_custom(self, recipe: CreativeRecipe) -> CreativeRecipe:
        if recipe.builtin:
            raise ValueError("Built-in recipes cannot be edited as custom recipes")
        state = self.load()
        existing = next((item for item in state.recipes if item.id == recipe.id), None)
        if existing is not None and existing.builtin:
            raise ValueError("Built-in recipes cannot be overwritten")
        state.recipes = [item for item in state.recipes if item.id != recipe.id]
        state.recipes.append(recipe.model_copy(deep=True))
        state.revision += 1
        self.save(state)
        return recipe.model_copy(deep=True)

    def create_custom(self, *, name: str, description: str = "", **layers) -> CreativeRecipe:
        recipe = CreativeRecipe(
            id=f"custom-{uuid4().hex[:10]}",
            name=name,
            description=description,
            builtin=False,
            **layers,
        )
        return self.upsert_custom(recipe)

    def delete_custom(self, recipe_id: str) -> bool:
        state = self.load()
        target = next((item for item in state.recipes if item.id == recipe_id), None)
        if target is None:
            return False
        if target.builtin:
            raise ValueError("Built-in recipes cannot be deleted")
        state.recipes = [item for item in state.recipes if item.id != recipe_id]
        state.last_applied_by_conversation = {
            key: value
            for key, value in state.last_applied_by_conversation.items()
            if value != recipe_id
        }
        state.revision += 1
        self.save(state)
        return True

    def mark_applied(self, conversation_id: str, recipe_id: str) -> None:
        state = self.load()
        state.last_applied_by_conversation[conversation_id] = recipe_id
        state.revision += 1
        self.save(state)


class CreativeRecipeManager:
    def __init__(
        self,
        repository: CreativeRecipeRepository,
        looks: LookPresetRepository,
        variety: VarietyRepository,
        arcs: SessionArcRepository,
        mixer: SceneMixerRepository,
        motifs: VisualMotifRepository,
    ) -> None:
        self.repository = repository
        self.looks = looks
        self.variety = variety
        self.arcs = arcs
        self.mixer = mixer
        self.motifs = motifs

    def capture_current(self, conversation_id: str, *, name: str) -> CreativeRecipe:
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValueError("Recipe name must not be empty")
        look = self.looks.active(conversation_id)
        variety = self.variety.active(conversation_id)
        arc = self.arcs.active(conversation_id)
        motif = self.motifs.active(conversation_id)
        mix = self.mixer.active(conversation_id)
        return self.repository.create_custom(
            name=clean_name,
            description="Gespeicherte Kombination aus der aktuellen Unterhaltung.",
            look_id=look.id if look else None,
            variety_id=variety.id if variety else None,
            arc_id=arc.arc_id if arc else None,
            visual_motif_id=motif.id if motif else None,
            scene_mix=mix.model_copy(deep=True) if mix else None,
            draw_scene_mix=False,
        )

    def apply(self, conversation_id: str, recipe_id: str) -> CreativeRecipe:
        recipe = self.repository.get(recipe_id)
        if recipe is None:
            raise KeyError(f"Creative recipe {recipe_id!r} not found")

        self.looks.set_active(conversation_id, recipe.look_id)
        self.variety.set_active(conversation_id, recipe.variety_id)
        if recipe.arc_id:
            self.arcs.activate(conversation_id, recipe.arc_id)
        else:
            self.arcs.clear(conversation_id)
        self.motifs.set_active(conversation_id, recipe.visual_motif_id)

        if recipe.scene_mix is not None:
            self.mixer.set_active(conversation_id, recipe.scene_mix)
        elif recipe.draw_scene_mix:
            self.mixer.draw(conversation_id)
        else:
            self.mixer.clear(conversation_id)

        self.repository.mark_applied(conversation_id, recipe.id)
        return recipe.model_copy(deep=True)
