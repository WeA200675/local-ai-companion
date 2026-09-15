from __future__ import annotations

from PySide6.QtCore import Signal

from app.ai.adult_intensity import AdultIntensityConfig, AdultIntensityRepository
from app.ai.prompting import build_system_prompt
from app.ui.mode_chat import ModeAwareChatWidget


class AdultModeAwareChatWidget(ModeAwareChatWidget):
    """Mode-aware chat plus conversation-scoped adult intensity controls."""

    adult_intensity_changed = Signal(object)

    def __init__(
        self,
        *args,
        adult_intensity_repository: AdultIntensityRepository | None = None,
        adult_intensity: AdultIntensityConfig | None = None,
        **kwargs,
    ) -> None:
        self.adult_intensity_repository = adult_intensity_repository
        self.adult_intensity = (
            adult_intensity.model_copy(deep=True)
            if adult_intensity is not None
            else AdultIntensityConfig()
        )
        super().__init__(*args, **kwargs)

    def set_adult_intensity(self, config: AdultIntensityConfig) -> None:
        self.adult_intensity = config.model_copy(deep=True)
        self.status.setText(
            f"Intimität: {config.sexuality_label} · Kink: {config.kink_label}"
        )

    def refresh_adult_intensity(self) -> None:
        if self.adult_intensity_repository is None or self.conversations is None:
            return
        self.adult_intensity = self.adult_intensity_repository.config(
            self.conversations.active_id()
        )

    def set_conversation(self, conversation_id: str) -> None:
        super().set_conversation(conversation_id)
        self.refresh_adult_intensity()

    def send_current(self) -> None:
        if self.adult_intensity_repository is not None and self.conversations is not None:
            text = self.input.toPlainText().strip()
            if text:
                config, changed = self.adult_intensity_repository.observe_user_signal(
                    self.conversations.active_id(),
                    text,
                )
                self.adult_intensity = config
                if changed:
                    self.adult_intensity_changed.emit(config.model_copy(deep=True))
        super().send_current()

    def _adult_intensity_context(self) -> str:
        return self.adult_intensity.prompt_text()

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
            self._session_moment_context(),
            self._twist_context(),
            self._scene_evolution_context(),
            self._ritual_context(),
            self._adult_intensity_context(),
        )

    def _start_media_generation(self, user_text: str, assistant_text: str) -> None:
        # The media planner has its own non-graphic adult guardrails. Passing a
        # media-safe summary lets visual tone follow the session without turning
        # chat intensity into permission for graphic imagery.
        augmented = f"{user_text}\n\n{self.adult_intensity.visual_text()}"
        super()._start_media_generation(augmented, assistant_text)
