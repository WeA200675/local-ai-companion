from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from app.ai.model import OllamaClient
from app.ai.persona import PersonaState
from app.media.comfyui import ComfyUIClient
from app.media.service import MediaService
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.ui.chat import ChatWidget
from app.ui.persona_lab import PersonaLab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local AI Companion — v0.1.0-alpha")
        self.resize(1000, 820)

        self.session_factory = make_session_factory()
        self.store = StateStore(self.session_factory)
        self.persona = self.store.load_persona()
        self.store.save_persona(self.persona)
        preference_tags = self.store.load_preference_tags()

        self.model = OllamaClient(
            model=os.getenv("LOCAL_AI_MODEL", "qwen2.5:7b"),
            base_url=os.getenv("LOCAL_AI_URL", "http://127.0.0.1:11434"),
        )
        self.media_backend = ComfyUIClient(
            base_url=os.getenv("LOCAL_MEDIA_URL", "http://127.0.0.1:8188"),
            workflow_path=os.getenv("LOCAL_MEDIA_WORKFLOW") or None,
            positive_node=os.getenv("LOCAL_MEDIA_POSITIVE_NODE", "6"),
            negative_node=os.getenv("LOCAL_MEDIA_NEGATIVE_NODE", "7"),
            seed_node=os.getenv("LOCAL_MEDIA_SEED_NODE", "3"),
            output_dir=os.getenv("LOCAL_MEDIA_OUTPUT", "data/generated_media"),
        )
        self.media_service = MediaService(self.model, self.media_backend)

        self.chat = ChatWidget(
            store=self.store,
            model=self.model,
            persona=self.persona,
            preference_tags=preference_tags,
            media_service=self.media_service,
        )
        self.persona_lab = PersonaLab(
            store=self.store,
            session_factory=self.session_factory,
            persona=self.persona,
            preference_tags=preference_tags,
        )
        self.persona_lab.persona_changed.connect(self._persona_changed)
        self.persona_lab.preference_tags_changed.connect(self._preference_tags_changed)

        tabs = QTabWidget()
        tabs.addTab(self.chat, "Chat")
        tabs.addTab(self.persona_lab, "Persona Lab")
        self.setCentralWidget(tabs)

    def _persona_changed(self, persona: PersonaState) -> None:
        self.persona = persona
        self.chat.persona = persona

    def _preference_tags_changed(self, tags: list[str]) -> None:
        self.chat.preference_tags = tags

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.store.save_persona(self.persona)
        self.media_service.close()
        self.model.close()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Companion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
