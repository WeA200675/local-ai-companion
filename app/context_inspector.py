from __future__ import annotations

from math import ceil

from pydantic import BaseModel, Field

from app.ai.adult_intensity import AdultIntensityConfig
from app.ai.creative_accents import DetailAccent, MoodGrade
from app.ai.creative_director import CreativeDirectorConfig
from app.ai.look_presets import LookPreset
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.ai.scenario_seeds import ScenarioSeedSelection
from app.ai.scene_evolution import ActiveRitual, ActiveSceneEvolution
from app.ai.scene_mixer import SceneMix
from app.ai.scene_presets import ScenePreset
from app.ai.session_arcs import ActiveArc
from app.ai.session_modes import SessionMode, TRAIT_NAMES
from app.ai.twist_deck import TwistCard
from app.ai.variety import VarietyCard
from app.ai.visual_motifs import VisualMotif
from app.memory.conversations import ConversationRepository
from app.memory.core_memory import CoreMemoryRepository
from app.memory.session_moments import SessionMoment
from app.memory.store import StateStore
from app.settings import AppSettings


class ContextHistoryItem(BaseModel):
    role: str
    preview: str
    approx_tokens: int = Field(ge=0)


class ContextSnapshot(BaseModel):
    model_name: str
    context_window: int | None
    response_budget: int | None
    conversation_id: str | None = None
    conversation_title: str | None = None
    scenario_seed_name: str | None = None
    scenario_media_preference: str | None = None
    scenario_compatibility_score: int | None = None
    scenario_random_seed: int | None = None
    sexuality_current: int = 1
    sexuality_max: int = 4
    sexuality_label: str = "Flirtend"
    sexuality_locked: bool = False
    kink_current: int = 0
    kink_max: int = 4
    kink_label: str = "Konventionell"
    kink_locked: bool = False
    adult_dynamic_escalation: bool = True
    adult_preferences: list[str] = Field(default_factory=list)
    adult_boundaries: list[str] = Field(default_factory=list)
    adult_intensity_context: str = ""
    base_traits: dict[str, float]
    effective_traits: dict[str, float]
    locked_traits: list[str]
    session_mode: str | None
    scene_name: str | None
    scene_context: str
    scene_evolution_name: str | None = None
    scene_evolution_stage: str | None = None
    scene_evolution_context: str = ""
    scene_evolution_automatic: bool = False
    scene_evolution_interval: int | None = None
    ritual_name: str | None = None
    ritual_step: str | None = None
    ritual_context: str = ""
    ritual_automatic: bool = False
    ritual_interval: int | None = None
    variety_name: str | None = None
    variety_context: str = ""
    look_name: str | None = None
    look_context: str = ""
    arc_name: str | None = None
    arc_stage: str | None = None
    arc_context: str = ""
    scene_mix_name: str | None = None
    scene_mix_context: str = ""
    visual_motif_name: str | None = None
    visual_motif_context: str = ""
    mood_grade_name: str | None = None
    mood_grade_context: str = ""
    detail_accent_name: str | None = None
    detail_accent_context: str = ""
    session_moment_name: str | None = None
    session_moment_context: str = ""
    twist_name: str | None = None
    twist_context: str = ""
    twist_auto_enabled: bool = False
    twist_interval: int | None = None
    anti_repetition_enabled: bool = False
    anti_repetition_context: str = ""
    director_enabled: bool = False
    director_interval: int | None = None
    director_intensity: str | None = None
    director_locks: list[str] = Field(default_factory=list)
    scene_mix_locks: list[str] = Field(default_factory=list)
    effective_tags: list[str]
    core_memory: list[str]
    adaptive_memory: list[str]
    history: list[ContextHistoryItem]
    system_prompt: str
    approx_input_tokens: int = Field(ge=0)
    approx_remaining_tokens: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)


def approximate_tokens(text: str) -> int:
    """Cheap local heuristic; deliberately avoids another tokenizer dependency."""

    clean = text.strip()
    if not clean:
        return 0
    return max(1, ceil(len(clean) / 4))


def _dedupe_tags(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def build_context_snapshot(
    *,
    store: StateStore,
    settings: AppSettings,
    persona: PersonaState,
    preference_tags: list[str],
    session_mode: SessionMode | None = None,
    scene_preset: ScenePreset | None = None,
    scene_evolution: ActiveSceneEvolution | None = None,
    active_ritual: ActiveRitual | None = None,
    variety_card: VarietyCard | None = None,
    look_preset: LookPreset | None = None,
    active_arc: ActiveArc | None = None,
    scene_mix: SceneMix | None = None,
    visual_motif: VisualMotif | None = None,
    mood_grade: MoodGrade | None = None,
    detail_accent: DetailAccent | None = None,
    session_moment: SessionMoment | None = None,
    twist_card: TwistCard | None = None,
    scenario_seed: ScenarioSeedSelection | None = None,
    adult_intensity: AdultIntensityConfig | None = None,
    twist_auto_enabled: bool = False,
    twist_interval: int | None = None,
    anti_repetition_context: str = "",
    anti_repetition_enabled: bool = False,
    conversations: ConversationRepository | None = None,
    director_config: CreativeDirectorConfig | None = None,
    scene_mix_locks: list[str] | None = None,
) -> ContextSnapshot:
    """Build the same high-level context layers used for a new local chat request.

    Token counts are estimates only. Ollama/model tokenizers remain authoritative.
    """

    effective_persona = (
        session_mode.apply(persona) if session_mode is not None else persona.model_copy(deep=True)
    )

    tags = list(preference_tags)
    if session_mode is not None:
        tags.extend(session_mode.style_tags)
    if scene_preset is not None:
        tags.extend(scene_preset.style_tags)
    if scene_evolution is not None:
        tags.extend(scene_evolution.style_tags)
    if active_ritual is not None:
        tags.extend(active_ritual.style_tags)
    if variety_card is not None:
        tags.extend(variety_card.style_tags)
    if look_preset is not None:
        tags.extend(look_preset.style_tags)
    if active_arc is not None:
        tags.extend(active_arc.style_tags)
    if scene_mix is not None:
        tags.extend(scene_mix.style_tags)
    if visual_motif is not None:
        tags.extend(visual_motif.prompt_tags())
    if mood_grade is not None:
        tags.extend(mood_grade.style_tags)
    if detail_accent is not None:
        tags.extend(detail_accent.style_tags)
    if twist_card is not None:
        tags.extend(twist_card.style_tags)
    effective_tags = _dedupe_tags(tags)

    scene_context = ""
    if scene_preset is not None:
        scene_context = f"{scene_preset.name}: {scene_preset.context}"

    scene_evolution_context = (
        scene_evolution.prompt_text() if scene_evolution is not None else ""
    )
    ritual_context = active_ritual.prompt_text() if active_ritual is not None else ""

    variety_context = ""
    if variety_card is not None:
        variety_context = f"{variety_card.name}: {variety_card.instruction}"

    look_context = look_preset.prompt_text() if look_preset is not None else ""
    arc_context = active_arc.prompt_text() if active_arc is not None else ""
    scene_mix_context = scene_mix.prompt_text() if scene_mix is not None else ""
    visual_motif_context = visual_motif.prompt_text() if visual_motif is not None else ""
    mood_grade_context = mood_grade.prompt_text() if mood_grade is not None else ""
    detail_accent_context = detail_accent.prompt_text() if detail_accent is not None else ""
    session_moment_context = session_moment.prompt_text() if session_moment is not None else ""
    twist_context = twist_card.prompt_text() if twist_card is not None else ""
    adult = adult_intensity or AdultIntensityConfig()
    adult_intensity_context = adult.prompt_text()

    core_memory = CoreMemoryRepository(store).active_prompt_entries(limit=12)
    adaptive_memory = (
        store.list_active_memory_summaries(limit=12)
        if settings.adaptive_memory_enabled
        else []
    )

    system_prompt = build_system_prompt(
        effective_persona,
        effective_tags,
        adaptive_memory,
        core_memory,
        scene_context,
        variety_context,
        look_context,
        arc_context,
        scene_mix_context,
        visual_motif_context,
        mood_grade_context,
        detail_accent_context,
        anti_repetition_context,
        session_moment_context,
        twist_context,
        scene_evolution_context,
        ritual_context,
        adult_intensity_context,
    )

    conversation_id: str | None = None
    conversation_title: str | None = None
    if conversations is not None:
        conversation_id = conversations.active_id()
        thread = conversations.get(conversation_id, include_archived=False)
        conversation_title = thread.title if thread is not None else None
        messages = conversations.list_messages(
            limit=settings.chat_history_messages,
            conversation_id=conversation_id,
        )
    else:
        messages = store.list_messages(limit=settings.chat_history_messages)

    history: list[ContextHistoryItem] = []
    history_tokens = 0
    for message in messages:
        tokens = approximate_tokens(message.content) + 4
        history_tokens += tokens
        preview = " ".join(message.content.split())
        if len(preview) > 180:
            preview = preview[:177] + "…"
        history.append(
            ContextHistoryItem(
                role=message.role,
                preview=preview,
                approx_tokens=tokens,
            )
        )

    approx_input_tokens = approximate_tokens(system_prompt) + history_tokens
    context_window = settings.chat_num_ctx or None
    response_budget = settings.chat_num_predict or None
    approx_remaining: int | None = None
    warnings: list[str] = []

    if context_window is not None:
        reserved_reply = response_budget or 0
        approx_remaining = max(0, context_window - approx_input_tokens - reserved_reply)
        if approx_input_tokens >= context_window:
            warnings.append(
                "Der geschätzte Eingabekontext erreicht oder überschreitet das konfigurierte Kontextfenster."
            )
        elif approx_input_tokens >= int(context_window * 0.80):
            warnings.append(
                "Der geschätzte Eingabekontext belegt mindestens 80 % des konfigurierten Kontextfensters."
            )
        if response_budget and approx_input_tokens + response_budget > context_window:
            warnings.append(
                "Eingabekontext plus Antwortbudget überschreiten voraussichtlich das konfigurierte Kontextfenster."
            )

    base_traits = {name: float(getattr(persona, name).current) for name in TRAIT_NAMES}
    effective_traits = {
        name: float(getattr(effective_persona, name).current) for name in TRAIT_NAMES
    }
    locked_traits = [name for name in TRAIT_NAMES if bool(getattr(persona, name).locked)]

    director_locks: list[str] = []
    if director_config is not None:
        director_locks = [
            label
            for label, locked in (
                ("look", director_config.lock_look),
                ("variety", director_config.lock_variety),
                ("arc", director_config.lock_arc),
                ("scene_mix", director_config.lock_scene_mix),
                ("visual_motif", director_config.lock_visual_motif),
                ("mood_grade", director_config.lock_mood_grade),
                ("detail_accent", director_config.lock_detail_accent),
            )
            if locked
        ]

    return ContextSnapshot(
        model_name=settings.model_name,
        context_window=context_window,
        response_budget=response_budget,
        conversation_id=conversation_id,
        conversation_title=conversation_title,
        scenario_seed_name=scenario_seed.template_name if scenario_seed is not None else None,
        scenario_media_preference=(
            scenario_seed.media_preference if scenario_seed is not None else None
        ),
        scenario_compatibility_score=(
            scenario_seed.compatibility_score if scenario_seed is not None else None
        ),
        scenario_random_seed=scenario_seed.random_seed if scenario_seed is not None else None,
        sexuality_current=adult.sexuality_current,
        sexuality_max=adult.sexuality_max,
        sexuality_label=adult.sexuality_label,
        sexuality_locked=adult.sexuality_locked,
        kink_current=adult.kink_current,
        kink_max=adult.kink_max,
        kink_label=adult.kink_label,
        kink_locked=adult.kink_locked,
        adult_dynamic_escalation=adult.dynamic_escalation,
        adult_preferences=list(adult.kink_preferences),
        adult_boundaries=list(adult.boundaries),
        adult_intensity_context=adult_intensity_context,
        base_traits=base_traits,
        effective_traits=effective_traits,
        locked_traits=locked_traits,
        session_mode=session_mode.name if session_mode is not None else None,
        scene_name=scene_preset.name if scene_preset is not None else None,
        scene_context=scene_context,
        scene_evolution_name=scene_evolution.plan_name if scene_evolution is not None else None,
        scene_evolution_stage=scene_evolution.stage_name if scene_evolution is not None else None,
        scene_evolution_context=scene_evolution_context,
        scene_evolution_automatic=bool(scene_evolution and scene_evolution.automatic),
        scene_evolution_interval=scene_evolution.interval if scene_evolution is not None else None,
        ritual_name=active_ritual.ritual_name if active_ritual is not None else None,
        ritual_step=active_ritual.step_name if active_ritual is not None else None,
        ritual_context=ritual_context,
        ritual_automatic=bool(active_ritual and active_ritual.automatic),
        ritual_interval=active_ritual.interval if active_ritual is not None else None,
        variety_name=variety_card.name if variety_card is not None else None,
        variety_context=variety_context,
        look_name=look_preset.name if look_preset is not None else None,
        look_context=look_context,
        arc_name=active_arc.arc_name if active_arc is not None else None,
        arc_stage=active_arc.stage_name if active_arc is not None else None,
        arc_context=arc_context,
        scene_mix_name=scene_mix.title if scene_mix is not None else None,
        scene_mix_context=scene_mix_context,
        visual_motif_name=visual_motif.name if visual_motif is not None else None,
        visual_motif_context=visual_motif_context,
        mood_grade_name=mood_grade.name if mood_grade is not None else None,
        mood_grade_context=mood_grade_context,
        detail_accent_name=detail_accent.name if detail_accent is not None else None,
        detail_accent_context=detail_accent_context,
        session_moment_name=session_moment.title if session_moment is not None else None,
        session_moment_context=session_moment_context,
        twist_name=twist_card.name if twist_card is not None else None,
        twist_context=twist_context,
        twist_auto_enabled=twist_auto_enabled,
        twist_interval=twist_interval,
        anti_repetition_enabled=anti_repetition_enabled,
        anti_repetition_context=anti_repetition_context,
        director_enabled=bool(director_config and director_config.enabled),
        director_interval=director_config.interval if director_config is not None else None,
        director_intensity=director_config.intensity if director_config is not None else None,
        director_locks=director_locks,
        scene_mix_locks=sorted(scene_mix_locks or []),
        effective_tags=effective_tags,
        core_memory=core_memory,
        adaptive_memory=adaptive_memory,
        history=history,
        system_prompt=system_prompt,
        approx_input_tokens=approx_input_tokens,
        approx_remaining_tokens=approx_remaining,
        warnings=warnings,
    )
