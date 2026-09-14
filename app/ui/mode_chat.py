from __future__ import annotations

from app.ai.prompting import build_system_prompt
from app.ai.scene_presets import ScenePreset
from app.ai.session_modes import SessionMode
from app.ai.variety import VarietyCard, VarietyRepository
from app.memory.conversations import ConversationRepository
from app.memory.core_memory import CoreMemoryRepository
from app.ui.chat import ChatWidget, MediaWorker


class ModeAwareChatWidget(ChatWidget):
    """ChatWidget variant with temporary SessionMode, ScenePreset and Variety overlays."""

    def __init__(
        self,
        *args,
        session_mode: SessionMode | None = None,
        scene_preset: ScenePreset | None = None,
        conversation_repository: ConversationRepository | None = None,
        variety_repository: VarietyRepository | None = None,
        variety_card: VarietyCard | None = None,
        **kwargs,
    ) -> None:
        self.session_mode = session_mode
        self.scene_preset = scene_preset
        self.conversations = conversation_repository
        self.variety_repository = variety_repository
        self.variety_card = variety_card
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

    def set_conversation(self, conversation_id: str) -> None:
        if self.conversations is None:
            return
        if not self.can_reconfigure():
            raise RuntimeError("Unterhaltung kann während eines lokalen Jobs nicht gewechselt werden")
        self.conversations.set_active(conversation_id)
        if self.variety_repository is not None:
            self.variety_card = self.variety_repository.active(conversation_id)
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
        )

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
