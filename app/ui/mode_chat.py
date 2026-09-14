from __future__ import annotations

from app.ai.prompting import build_system_prompt
from app.ai.scene_presets import ScenePreset
from app.ai.session_modes import SessionMode
from app.memory.core_memory import CoreMemoryRepository
from app.ui.chat import ChatWidget, MediaWorker


class ModeAwareChatWidget(ChatWidget):
    """ChatWidget variant with temporary SessionMode and ScenePreset overlays."""

    def __init__(
        self,
        *args,
        session_mode: SessionMode | None = None,
        scene_preset: ScenePreset | None = None,
        **kwargs,
    ) -> None:
        self.session_mode = session_mode
        self.scene_preset = scene_preset
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
        )

    def _start_media_generation(self, user_text: str, assistant_text: str) -> None:
        if not self.media_service or not self.media_service.enabled:
            return
        if self._media_worker is not None and self._media_worker.isRunning():
            return

        planner_user_text = user_text
        scene_context = self._scene_context()
        if scene_context:
            planner_user_text = f"{user_text}\n\nActive user-selected scene: {scene_context}"

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
