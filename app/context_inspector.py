from __future__ import annotations

from math import ceil

from pydantic import BaseModel, Field

from app.ai.creative_director import CreativeDirectorConfig
from app.ai.look_presets import LookPreset
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.ai.scene_mixer import SceneMix
from app.ai.scene_presets import ScenePreset
from app.ai.session_arcs import ActiveArc
from app.ai.session_modes import SessionMode, TRAIT_NAMES
from app.ai.variety import VarietyCard
from app.ai.visual_motifs import VisualMotif
from app.memory.conversations import ConversationRepository
from app.memory.core_memory import CoreMemoryRepository
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
    base_traits: dict[str, float]
    effective_traits: dict[str, float]
    locked_traits: list[str]
    session_mode: str | None
    scene_name: str | None
    scene_context: str
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
    variety_card: VarietyCard | None = None,
    look_preset: LookPreset | None = None,
    active_arc: ActiveArc | None = None,
    scene_mix: SceneMix | None = None,
    visual_motif: VisualMotif | None = None,
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
    effective_tags = _dedupe_tags(tags)

    scene_context = ""
    if scene_preset is not None:
        scene_context = f"{scene_preset.name}: {scene_preset.context}"

    variety_context = ""
    if variety_card is not None:
        variety_context = f"{variety_card.name}: {variety_card.instruction}"

    look_context = look_preset.prompt_text() if look_preset is not None else ""
    arc_context = active_arc.prompt_text() if active_arc is not None else ""
    scene_mix_context = scene_mix.prompt_text() if scene_mix is not None else ""
    visual_motif_context = visual_motif.prompt_text() if visual_motif is not None else ""

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
            )
            if locked
        ]

    return ContextSnapshot(
        model_name=settings.model_name,
        context_window=context_window,
        response_budget=response_budget,
        conversation_id=conversation_id,
        conversation_title=conversation_title,
        base_traits=base_traits,
        effective_traits=effective_traits,
        locked_traits=locked_traits,
        session_mode=session_mode.name if session_mode is not None else None,
        scene_name=scene_preset.name if scene_preset is not None else None,
        scene_context=scene_context,
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
