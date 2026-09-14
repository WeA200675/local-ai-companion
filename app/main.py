from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from app import __version__
from app.ai.model import OllamaClient
from app.ai.persona import PersonaState
from app.media.comfyui import ComfyUIClient
from app.media.service import MediaService
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings
from app.ui.chat import ChatWidget
from app.ui.media_history import MediaHistoryWidget
from app.ui.persona_lab import PersonaLab
from app.ui.settings import SettingsWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Local AI Companion — v{__version__}")
        self.resize(1120, 860)

        self.session_factory = make_session_factory()
        self.store = StateStore(self.session_factory)
        self.persona = self.store.load_persona()
        self.store.save_persona(self.persona)
        preference_tags = self.store.load_preference_tags()
        self.settings = self.store.load_settings(AppSettings.from_env())

        self.model, self.media_service = self._build_services(self.settings)

        self.chat = ChatWidget(
            store=self.store,
            model=self.model,
            persona=self.persona,
            preference_tags=preference_tags,
            media_service=self.media_service,
            settings=self.settings,
            on_persona_changed=self._persona_changed,
        )
        self.persona_lab = PersonaLab(
            store=self.store,
            session_factory=self.session_factory,
            persona=self.persona,
            preference_tags=preference_tags,
        )
        self.media_history = MediaHistoryWidget(
            self.store,
            limit=self.settings.media_history_limit,
        )
        self.settings_widget = SettingsWidget(self.store, self.settings)

        self.persona_lab.persona_changed.connect(self._persona_changed)
        self.persona_lab.preference_tags_changed.connect(self._preference_tags_changed)
        self.chat.media_history_changed.connect(self.media_history.refresh)
        self.media_history.feedback_changed.connect(
            self.settings_widget._refresh_preference_summary
        )
        self.settings_widget.settings_saved.connect(self._settings_saved)

        tabs = QTabWidget()
        tabs.addTab(self.chat, "Chat")
        tabs.addTab(self.persona_lab, "Persona Lab")
        tabs.addTab(self.media_history, "Medien")
        tabs.addTab(self.settings_widget, "Einstellungen")
        self.setCentralWidget(tabs)

    def _build_services(self, settings: AppSettings) -> tuple[OllamaClient, MediaService]:
        model = OllamaClient(
            model=settings.model_name,
            base_url=settings.model_url,
        )
        media_backend = ComfyUIClient(
            base_url=settings.media_url,
            workflow_path=settings.workflow_path,
            positive_node=settings.media_positive_node,
            negative_node=settings.media_negative_node,
            seed_node=settings.media_seed_node,
            output_dir=settings.output_path,
        )
        media_service = MediaService(
            model,
            media_backend,
            store=self.store,
            settings=settings,
        )
        return model, media_service

    def _settings_saved(self, settings: AppSettings) -> None:
        self.settings = settings.model_copy(deep=True)
        self.media_history.set_limit(settings.media_history_limit)

        if not self.chat.can_reconfigure():
            QMessageBox.information(
                self,
                "Einstellungen gespeichert",
                "Ein lokaler KI-Job läuft gerade. Die neuen Backend-Einstellungen werden beim nächsten App-Start vollständig aktiv.",
            )
            return

        old_model = self.model
        old_media_service = self.media_service
        new_model, new_media_service = self._build_services(settings)
        try:
            self.chat.set_services(new_model, new_media_service, settings)
        except RuntimeError as exc:
            new_media_service.close()
            new_model.close()
            QMessageBox.information(self, "Einstellungen gespeichert", str(exc))
            return

        self.model = new_model
        self.media_service = new_media_service
        old_media_service.close()
        old_model.close()

    def _persona_changed(self, persona: PersonaState) -> None:
        self.persona = persona
        self.chat.persona = persona
        if hasattr(self, "persona_lab"):
            self.persona_lab.set_persona(persona)

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
