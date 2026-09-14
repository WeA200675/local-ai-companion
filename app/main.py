from __future__ import annotations

import sys

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTabWidget,
)

from app import __version__
from app.ai.model import OllamaClient
from app.ai.persona import PersonaState
from app.backup import BackupError, apply_pending_restore
from app.media.comfyui import ComfyUIClient
from app.media.service import MediaService
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.privacy import PrivacyConfig, PrivacyStore
from app.settings import AppSettings
from app.ui.backup import BackupWidget
from app.ui.character_studio import CharacterStudio
from app.ui.media_history import MediaHistoryWidget
from app.ui.memory_lab import MemoryLab
from app.ui.mode_chat import ModeAwareChatWidget
from app.ui.persona_lab import PersonaLab
from app.ui.privacy import PrivacyActivityMonitor, PrivacyLockScreen, PrivacySettingsWidget
from app.ui.scene_presets import ScenePresetsWidget
from app.ui.session_modes import SessionModesWidget
from app.ui.settings import SettingsWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Local AI Companion — v{__version__}")
        self.resize(1120, 860)
        self._startup_notice: tuple[str, str, str] | None = None

        self.session_factory = make_session_factory()
        self.store = StateStore(self.session_factory)
        self.persona = self.store.load_persona()
        self.store.save_persona(self.persona)
        preference_tags = self.store.load_preference_tags()
        self.settings = self.store.load_settings(AppSettings.from_env())
        self.privacy_repository = PrivacyStore(self.store)
        self.privacy_config = self.privacy_repository.load()

        self.model, self.media_service = self._build_services(self.settings)
        self.session_modes = SessionModesWidget(self.store)
        self.scene_presets = ScenePresetsWidget(self.store)

        self.chat = ModeAwareChatWidget(
            store=self.store,
            model=self.model,
            persona=self.persona,
            preference_tags=preference_tags,
            media_service=self.media_service,
            settings=self.settings,
            on_persona_changed=self._persona_changed,
            session_mode=self.session_modes.active_mode(),
            scene_preset=self.scene_presets.active_scene(),
        )
        self.persona_lab = PersonaLab(
            store=self.store,
            session_factory=self.session_factory,
            persona=self.persona,
            preference_tags=preference_tags,
        )
        self.memory_lab = MemoryLab(self.store)
        self.character_studio = CharacterStudio(
            self.store,
            key=self.settings.continuity_key,
        )
        self.media_history = MediaHistoryWidget(
            self.store,
            limit=self.settings.media_history_limit,
        )
        self.settings_widget = SettingsWidget(self.store, self.settings)
        self.privacy_settings = PrivacySettingsWidget(self.store)
        self.backup_widget = BackupWidget()

        self.persona_lab.persona_changed.connect(self._persona_changed)
        self.persona_lab.preference_tags_changed.connect(self._preference_tags_changed)
        self.session_modes.active_mode_changed.connect(self.chat.set_session_mode)
        self.scene_presets.active_scene_changed.connect(self.chat.set_scene_preset)
        self.chat.memory_changed.connect(self.memory_lab.refresh)
        self.chat.media_history_changed.connect(self.media_history.refresh)
        self.chat.media_history_changed.connect(self.character_studio.load_profile)
        self.media_history.feedback_changed.connect(
            self.settings_widget._refresh_preference_summary
        )
        self.media_history.feedback_changed.connect(self.character_studio.load_profile)
        self.media_history.reference_changed.connect(self.character_studio.load_profile)
        self.character_studio.profile_changed.connect(lambda _key: self.media_history.refresh())
        self.settings_widget.settings_saved.connect(self._settings_saved)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.chat, "Chat")
        self.tabs.addTab(self.session_modes, "Session-Modi")
        self.tabs.addTab(self.scene_presets, "Szenen")
        self.tabs.addTab(self.persona_lab, "Persona Lab")
        self.tabs.addTab(self.memory_lab, "Memory")
        self.tabs.addTab(self.character_studio, "Character Studio")
        self.tabs.addTab(self.media_history, "Medien")
        self.tabs.addTab(self.settings_widget, "Einstellungen")
        self.tabs.addTab(self.privacy_settings, "Privatsphäre")
        self.tabs.addTab(self.backup_widget, "Backup")

        self.lock_screen = PrivacyLockScreen(self.store)
        self.lock_screen.unlocked.connect(self._unlock_privacy)
        self.privacy_settings.config_changed.connect(self._privacy_config_changed)
        self.privacy_settings.lock_requested.connect(self.lock_privacy)

        self.shell = QStackedWidget()
        self.shell.addWidget(self.lock_screen)
        self.shell.addWidget(self.tabs)
        self.setCentralWidget(self.shell)

        self.privacy_monitor = PrivacyActivityMonitor(self)
        self.privacy_monitor.lock_due.connect(self.lock_privacy)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self.privacy_monitor)

        self.lock_shortcut = QShortcut(QKeySequence("Ctrl+Shift+L"), self)
        self.lock_shortcut.activated.connect(self.lock_privacy)

        if self.privacy_config.enabled:
            self.lock_privacy()
        else:
            self._unlock_privacy()

    @property
    def privacy_locked(self) -> bool:
        return self.shell.currentWidget() is self.lock_screen

    def queue_startup_notice(self, kind: str, title: str, message: str) -> None:
        self._startup_notice = (kind, title, message)
        if not self.privacy_locked:
            self._show_startup_notice()

    def _show_startup_notice(self) -> None:
        notice = self._startup_notice
        self._startup_notice = None
        if notice is None:
            return
        kind, title, message = notice
        if kind == "warning":
            QMessageBox.warning(self, title, message)
        else:
            QMessageBox.information(self, title, message)

    def lock_privacy(self) -> None:
        self.privacy_config = self.privacy_repository.load()
        if not self.privacy_config.enabled or not self.privacy_config.has_passphrase:
            return
        self.lock_screen.reload_config()
        self.shell.setCurrentWidget(self.lock_screen)
        self.privacy_monitor.configure(self.privacy_config.auto_lock_minutes, active=False)
        self.lock_screen.focus_passphrase()

    def _unlock_privacy(self) -> None:
        self.privacy_config = self.privacy_repository.load()
        self.shell.setCurrentWidget(self.tabs)
        self.privacy_monitor.configure(
            self.privacy_config.auto_lock_minutes,
            active=self.privacy_config.enabled,
        )
        self.privacy_settings.refresh()
        self._show_startup_notice()

    def _privacy_config_changed(self, config: PrivacyConfig) -> None:
        self.privacy_config = config.model_copy(deep=True)
        self.lock_screen.reload_config()
        self.privacy_monitor.configure(
            self.privacy_config.auto_lock_minutes,
            active=self.privacy_config.enabled and not self.privacy_locked,
        )
        if not self.privacy_config.enabled and self.privacy_locked:
            self._unlock_privacy()

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
            reference_node=settings.media_reference_node,
            reference_input_key=settings.media_reference_input_key,
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
        self.character_studio.set_key(settings.continuity_key)

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

    previous_backup = None
    restore_error = None
    try:
        previous_backup = apply_pending_restore()
    except BackupError as exc:
        restore_error = str(exc)

    window = MainWindow()
    window.show()

    if restore_error:
        window.queue_startup_notice(
            "warning",
            "Backup-Wiederherstellung fehlgeschlagen",
            "Der bisherige lokale Stand wurde weiter verwendet. Die vorgemerkte Wiederherstellung wurde nicht angewendet.\n\n"
            + restore_error,
        )
    elif previous_backup is not None:
        window.queue_startup_notice(
            "information",
            "Backup wiederhergestellt",
            f"Der importierte Stand ist aktiv. Der vorherige SQLite-Stand wurde vorher gesichert unter:\n{previous_backup}",
        )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
