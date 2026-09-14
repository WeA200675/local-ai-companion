from __future__ import annotations

from PySide6.QtCore import Signal

from app.ai.anti_repetition import AntiRepetitionRepository
from app.ai.creative_accents import (
    DetailAccent,
    DetailAccentRepository,
    MoodGrade,
    MoodGradeRepository,
)
from app.ai.creative_director import CreativeDirector
from app.ai.look_presets import LookPreset, LookPresetRepository
from app.ai.prompting import build_system_prompt
from app.ai.scene_mixer import SceneMix, SceneMixerRepository
from app.ai.scene_presets import ScenePreset
from app.ai.session_arcs import ActiveArc, SessionArcRepository
from app.ai.session_modes import SessionMode
from app.ai.variety import VarietyCard, VarietyRepository
from app.ai.visual_motifs import VisualMotif, VisualMotifRepository
from app.memory.conversations import ConversationRepository
from app.memory.core_memory import CoreMemoryRepository
from app.ui.chat import ChatWidget, MediaWorker


class ModeAwareChatWidget(ChatWidget):
    """ChatWidget variant with temporary mode, scene, variety and creative overlays."""

    creative_context_changed = Signal()

    def __init__(
        self,
        *args,
        session_mode: SessionMode | None = None,
        scene_preset: ScenePreset | None = None,
        conversation_repository: ConversationRepository | None = None,
        variety_repository: VarietyRepository | None = None,
        variety_card: VarietyCard | None = None,
        look_repository: LookPresetRepository | None = None,
        look_preset: LookPreset | None = None,
        arc_repository: SessionArcRepository | None = None,
        active_arc: ActiveArc | None = None,
        mixer_repository: SceneMixerRepository | None = None,
        scene_mix: SceneMix | None = None,
        motif_repository: VisualMotifRepository | None = None,
        visual_motif: VisualMotif | None = None,
        mood_repository: MoodGradeRepository | None = None,
        mood_grade: MoodGrade | None = None,
        detail_repository: DetailAccentRepository | None = None,
        detail_accent: DetailAccent | None = None,
        anti_repetition_repository: AntiRepetitionRepository | None = None,
        creative_director: CreativeDirector | None = None,
        **kwargs,
    ) -> None:
        self.session_mode = session_mode
        self.scene_preset = scene_preset
        self.conversations = conversation_repository
        self.variety_repository = variety_repository
        self.variety_card = variety_card
        self.look_repository = look_repository
        self.look_preset = look_preset
        self.arc_repository = arc_repository
        self.active_arc = active_arc
        self.mixer_repository = mixer_repository
        self.scene_mix = scene_mix
        self.motif_repository = motif_repository
        self.visual_motif = visual_motif
        self.mood_repository = mood_repository
        self.mood_grade = mood_grade
        self.detail_repository = detail_repository
        self.detail_accent = detail_accent
        self.anti_repetition_repository = anti_repetition_repository
        self.creative_director = creative_director
        super().__init__(*args, **kwargs)
        self.core_memory = CoreMemoryRepository(self.store)

    def set_session_mode(self, mode: SessionMode | None) -> None:
        self.session_mode = mode.model_copy(deep=True) if mode is not None else None
        if mode is None:
            self.status.setText("Session-Modus: Basis")
        else:
            self.status.setText(f"Session-Modus: {mode.name}")

    def set_scene_preset(self, scene: ScenePreset | None) -> None:
        self.scene_preset = scene.model_copy(deep=True) if scene is not None else None
        if scene is None:
            self.status.setText("Szene: Basis")
        else:
            self.status.setText(f"Szene: {scene.name}")

    def set_variety_card(self, card: VarietyCard | None) -> None:
        self.variety_card = card.model_copy(deep=True) if card is not None else None
        if card is None:
            self.status.setText("Impuls: Basis")
        else:
            self.status.setText(f"Impuls: {card.name}")

    def set_look_preset(self, preset: LookPreset | None) -> None:
        self.look_preset = preset.model_copy(deep=True) if preset is not None else None
        if preset is None:
            self.status.setText("Look: Basis")
        else:
            self.status.setText(f"Look: {preset.name}")

    def set_active_arc(self, active: ActiveArc | None) -> None:
        self.active_arc = active.model_copy(deep=True) if active is not None else None
        if active is None:
            self.status.setText("Session-Arc: aus")
        else:
            self.status.setText(
                f"Arc: {active.arc_name} · {active.stage_name} ({active.stage_index + 1}/{active.stage_count})"
            )

    def set_scene_mix(self, mix: SceneMix | None) -> None:
        self.scene_mix = mix.model_copy(deep=True) if mix is not None else None
        if mix is None:
            self.status.setText("Scene Mixer: aus")
        else:
            self.status.setText(f"Scene Mixer: {mix.title}")

    def set_visual_motif(self, motif: VisualMotif | None) -> None:
        self.visual_motif = motif.model_copy(deep=True) if motif is not None else None
        if motif is None:
            self.status.setText("Visual-Motiv: Basis")
        else:
            self.status.setText(f"Visual-Motiv: {motif.name}")

    def set_mood_grade(self, grade: MoodGrade | None) -> None:
        self.mood_grade = grade.model_copy(deep=True) if grade is not None else None
        if grade is None:
            self.status.setText("Mood-Grade: Basis")
        else:
            self.status.setText(f"Mood-Grade: {grade.name}")

    def set_detail_accent(self, accent: DetailAccent | None) -> None:
        self.detail_accent = accent.model_copy(deep=True) if accent is not None else None
        if accent is None:
            self.status.setText("Detail-Akzent: aus")
        else:
            self.status.setText(f"Detail-Akzent: {accent.name}")

    def refresh_creative_overlays(self) -> None:
        if self.conversations is None:
            return
        conversation_id = self.conversations.active_id()
        if self.variety_repository is not None:
            self.variety_card = self.variety_repository.active(conversation_id)
        if self.look_repository is not None:
            self.look_preset = self.look_repository.active(conversation_id)
        if self.arc_repository is not None:
            self.active_arc = self.arc_repository.active(conversation_id)
        if self.mixer_repository is not None:
            self.scene_mix = self.mixer_repository.active(conversation_id)
        if self.motif_repository is not None:
            self.visual_motif = self.motif_repository.active(conversation_id)
        if self.mood_repository is not None:
            self.mood_grade = self.mood_repository.active(conversation_id)
        if self.detail_repository is not None:
            self.detail_accent = self.detail_repository.active(conversation_id)

    def set_conversation(self, conversation_id: str) -> None:
        if self.conversations is None:
            return
        if not self.can_reconfigure():
            raise RuntimeError("Unterhaltung kann während eines lokalen Jobs nicht gewechselt werden")
        self.conversations.set_active(conversation_id)
        self.refresh_creative_overlays()
        self._pending_user_text = ""
        self._latest_user_text = ""
        self._latest_assistant_text = ""
        self._continuation_prefix = ""
        self._last_response_incomplete = False
        self.more_button.setEnabled(False)
        self.less_button.setEnabled(False)
        self._load_history()
        thread = self.conversations.get(conversation_id, include_archived=False)
        if thread is not None:
            self.status.setText(f"Unterhaltung: {thread.title}")

    def _effective_persona(self):
        if self.session_mode is None:
            return self.persona.model_copy(deep=True)
        return self.session_mode.apply(self.persona)

    def _effective_tags(self) -> list[str]:
        if self.session_mode is None:
            tags = list(self.preference_tags)
        else:
            tags = self.session_mode.merged_tags(self.preference_tags)
        if self.scene_preset is not None:
            tags.extend(self.scene_preset.style_tags)
        if self.variety_card is not None:
            tags.extend(self.variety_card.style_tags)
        if self.look_preset is not None:
            tags.extend(self.look_preset.style_tags)
        if self.active_arc is not None:
            tags.extend(self.active_arc.style_tags)
        if self.scene_mix is not None:
            tags.extend(self.scene_mix.style_tags)
        if self.visual_motif is not None:
            tags.extend(self.visual_motif.prompt_tags())
        if self.mood_grade is not None:
            tags.extend(self.mood_grade.style_tags)
        if self.detail_accent is not None:
            tags.extend(self.detail_accent.style_tags)

        result: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            clean = tag.strip()
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    def _scene_context(self) -> str:
        if self.scene_preset is None:
            return ""
        return f"{self.scene_preset.name}: {self.scene_preset.context}"

    def _variety_context(self) -> str:
        if self.variety_card is None:
            return ""
        return f"{self.variety_card.name}: {self.variety_card.instruction}"

    def _look_context(self) -> str:
        if self.look_preset is None:
            return ""
        return self.look_preset.prompt_text()

    def _arc_context(self) -> str:
        if self.active_arc is None:
            return ""
        return self.active_arc.prompt_text()

    def _scene_mix_context(self) -> str:
        if self.scene_mix is None:
            return ""
        return self.scene_mix.prompt_text()

    def _visual_motif_context(self) -> str:
        if self.visual_motif is None:
            return ""
        return self.visual_motif.prompt_text()

    def _mood_grade_context(self) -> str:
        if self.mood_grade is None:
            return ""
        return self.mood_grade.prompt_text()

    def _detail_accent_context(self) -> str:
        if self.detail_accent is None:
            return ""
        return self.detail_accent.prompt_text()

    def _creative_signature(self) -> str:
        parts = [
            f"look:{self.look_preset.id if self.look_preset else 'base'}",
            f"variety:{self.variety_card.id if self.variety_card else 'base'}",
            (
                f"arc:{self.active_arc.arc_id}:{self.active_arc.stage_index}"
                if self.active_arc is not None
                else "arc:base"
            ),
            f"scene:{self.scene_mix.signature if self.scene_mix else 'base'}",
            f"motif:{self.visual_motif.id if self.visual_motif else 'base'}",
            f"mood:{self.mood_grade.id if self.mood_grade else 'base'}",
            f"detail:{self.detail_accent.id if self.detail_accent else 'base'}",
        ]
        return "|".join(parts)

    def _anti_repetition_context(self) -> str:
        if self.anti_repetition_repository is None or self.conversations is None:
            return ""
        return self.anti_repetition_repository.guidance(
            self.conversations.active_id(),
            self._creative_signature(),
        )

    def _system_prompt(self) -> str:
        memory_notes = (
            self.store.list_active_memory_summaries(limit=12)
            if self.settings.adaptive_memory_enabled
            else []
        )
        core_memory_notes = self.core_memory.active_prompt_entries(limit=12)
        return build_system_prompt(
            self._effective_persona(),
            self._effective_tags(),
            memory_notes,
            core_memory_notes,
            self._scene_context(),
            self._variety_context(),
            self._look_context(),
            self._arc_context(),
            self._scene_mix_context(),
            self._visual_motif_context(),
            self._mood_grade_context(),
            self._detail_accent_context(),
            self._anti_repetition_context(),
        )

    def _model_completed(self, reply: str) -> None:
        # Finish the current response and its media planning with the context that
        # produced it. Any automatic rotation below applies only to the next turn.
        super()._model_completed(reply)
        conversation_id = self.conversations.active_id() if self.conversations is not None else None
        if conversation_id and self.anti_repetition_repository is not None:
            self.anti_repetition_repository.record_reply(
                conversation_id,
                reply,
                self._creative_signature(),
            )
        if self.creative_director is None or conversation_id is None:
            return
        result = self.creative_director.maybe_rotate(
            conversation_id,
            assistant_count=self.store.assistant_message_count(),
        )
        if result is None or not result.changed_anything:
            return
        self.refresh_creative_overlays()
        labels = {
            "look": "Look",
            "variety": "Impuls",
            "arc": "Arc",
            "scene_mix": "Scene Mixer",
            "visual_motif": "Visual-Motiv",
            "mood_grade": "Mood-Grade",
            "detail_accent": "Detail-Akzent",
        }
        summary = ", ".join(labels.get(item, item) for item in result.changed)
        self.status.setText(f"Kreative Regie für nächste Antwort: {summary}")
        self.creative_context_changed.emit()

    def _start_media_generation(self, user_text: str, assistant_text: str) -> None:
        if not self.media_service or not self.media_service.enabled:
            return
        if self._media_worker is not None and self._media_worker.isRunning():
            return

        planner_parts = [user_text]
        scene_context = self._scene_context()
        if scene_context:
            planner_parts.append(f"Active user-selected scene: {scene_context}")
        variety_context = self._variety_context()
        if variety_context:
            planner_parts.append(f"Temporary variety spark: {variety_context}")
        look_context = self._look_context()
        if look_context:
            planner_parts.append(f"Temporary look preset: {look_context}")
        arc_context = self._arc_context()
        if arc_context:
            planner_parts.append(f"Current session arc phase: {arc_context}")
        mix_context = self._scene_mix_context()
        if mix_context:
            planner_parts.append(f"Temporary scene mixer layer: {mix_context}")
        motif_context = self._visual_motif_context()
        if motif_context:
            planner_parts.append(f"Temporary visual motif: {motif_context}")
        mood_context = self._mood_grade_context()
        if mood_context:
            planner_parts.append(f"Temporary mood grade: {mood_context}")
        detail_context = self._detail_accent_context()
        if detail_context:
            planner_parts.append(f"Temporary detail accent: {detail_context}")
        anti_context = self._anti_repetition_context()
        if anti_context:
            planner_parts.append(f"Local anti-repetition guidance: {anti_context}")
        planner_user_text = "\n\n".join(planner_parts)

        self.media_preview.setVisible(True)
        self.status.setText("KI plant optional ein lokales Bild …")
        worker = MediaWorker(
            self.media_service,
            user_text=planner_user_text,
            assistant_text=assistant_text,
            persona=self._effective_persona(),
            preference_tags=self._effective_tags(),
            parent=self,
        )
        worker.generated.connect(self._media_generated)
        worker.skipped.connect(self._media_skipped)
        worker.failed.connect(self._media_failed)
        worker.finished.connect(self._media_finished)
        self._media_worker = worker
        worker.start()
