from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.memory.store import StateStore
from app.privacy import PrivacyConfig, PrivacyStore


class PrivacyLockScreen(QWidget):
    unlocked = Signal()

    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = PrivacyStore(store)
        self.config = self.repository.load()

        title = QLabel("🔒 Local AI Companion gesperrt")
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        subtitle = QLabel(
            "Chat, Memory, Medien und Einstellungen bleiben verborgen, bis die lokale Sperre aufgehoben wird."
        )
        subtitle.setWordWrap(True)

        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("Lokale Passphrase")
        self.passphrase.setMaximumWidth(420)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.unlock_button = QPushButton("Entsperren")

        form = QFormLayout()
        form.addRow("Passphrase", self.passphrase)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.unlock_button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addStretch(2)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addLayout(actions)
        layout.addStretch(3)

        self.unlock_button.clicked.connect(self.try_unlock)
        self.passphrase.returnPressed.connect(self.try_unlock)

    def reload_config(self) -> None:
        self.config = self.repository.load()
        self.passphrase.clear()
        self.status.clear()

    def focus_passphrase(self) -> None:
        self.passphrase.setFocus()

    def try_unlock(self) -> None:
        self.config = self.repository.load()
        if not self.config.enabled:
            self.passphrase.clear()
            self.unlocked.emit()
            return
        if self.config.verify(self.passphrase.text()):
            self.passphrase.clear()
            self.status.clear()
            self.unlocked.emit()
            return
        self.passphrase.clear()
        self.status.setText("Passphrase stimmt nicht.")
        self.passphrase.setFocus()


class PrivacySettingsWidget(QWidget):
    config_changed = Signal(object)
    lock_requested = Signal()

    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = PrivacyStore(store)
        self.config = self.repository.load()

        self.state_label = QLabel()
        self.state_label.setWordWrap(True)

        self.current_passphrase = QLineEdit()
        self.current_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_passphrase.setPlaceholderText("nur bei bestehender Sperre nötig")
        self.new_passphrase = QLineEdit()
        self.new_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_passphrase.setPlaceholderText("mindestens 6 Zeichen")
        self.confirm_passphrase = QLineEdit()
        self.confirm_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_passphrase.setPlaceholderText("neue Passphrase wiederholen")

        self.auto_lock = QSpinBox()
        self.auto_lock.setRange(0, 720)
        self.auto_lock.setSpecialValueText("Aus")
        self.auto_lock.setSuffix(" min")
        self.auto_lock.setValue(self.config.auto_lock_minutes)
        self.auto_lock.setToolTip(
            "Sperrt die Oberfläche nach Inaktivität. 0 deaktiviert die automatische Sperre."
        )

        form = QFormLayout()
        form.addRow("Status", self.state_label)
        form.addRow("Aktuelle Passphrase", self.current_passphrase)
        form.addRow("Neue Passphrase", self.new_passphrase)
        form.addRow("Bestätigung", self.confirm_passphrase)
        form.addRow("Automatisch sperren", self.auto_lock)

        self.set_button = QPushButton("Passphrase setzen / ändern")
        self.remove_button = QPushButton("Sperre entfernen")
        self.lock_button = QPushButton("🔒 Jetzt sperren")
        self.save_timer_button = QPushButton("Auto-Sperre speichern")

        row = QHBoxLayout()
        row.addWidget(self.remove_button)
        row.addWidget(self.set_button)
        row.addStretch(1)
        row.addWidget(self.save_timer_button)
        row.addWidget(self.lock_button)

        note = QLabel(
            "Die Passphrase wird niemals im Klartext gespeichert. Lokal liegt nur ein PBKDF2-SHA256-Prüfwert mit zufälligem Salt. Strg+Umschalt+L sperrt die App sofort. Die Sperre ist eine Privatsphäre-Barriere für die Oberfläche und ersetzt keine Festplattenverschlüsselung."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch(1)
        layout.addLayout(row)

        self.set_button.clicked.connect(self.set_or_change_passphrase)
        self.remove_button.clicked.connect(self.remove_lock)
        self.lock_button.clicked.connect(self.request_lock)
        self.save_timer_button.clicked.connect(self.save_auto_lock)
        self.refresh()

    def refresh(self) -> None:
        self.config = self.repository.load()
        self.auto_lock.setValue(self.config.auto_lock_minutes)
        if self.config.enabled and self.config.has_passphrase:
            self.state_label.setText("Aktiv — Start und manuelle Sperre schützen die Oberfläche.")
            self.remove_button.setEnabled(True)
            self.lock_button.setEnabled(True)
        else:
            self.state_label.setText("Aus — zuerst eine lokale Passphrase setzen.")
            self.remove_button.setEnabled(False)
            self.lock_button.setEnabled(False)
        self._clear_secret_fields()

    def _clear_secret_fields(self) -> None:
        self.current_passphrase.clear()
        self.new_passphrase.clear()
        self.confirm_passphrase.clear()

    def _current_authorized(self) -> bool:
        if not self.config.enabled:
            return True
        if self.config.verify(self.current_passphrase.text()):
            return True
        QMessageBox.warning(
            self,
            "Privatsphäre-Sperre",
            "Die aktuelle Passphrase stimmt nicht.",
        )
        return False

    def set_or_change_passphrase(self) -> None:
        self.config = self.repository.load()
        if not self._current_authorized():
            self._clear_secret_fields()
            return
        new = self.new_passphrase.text()
        if new != self.confirm_passphrase.text():
            QMessageBox.warning(
                self,
                "Privatsphäre-Sperre",
                "Die beiden neuen Passphrasen stimmen nicht überein.",
            )
            return
        try:
            self.config.set_passphrase(new)
        except ValueError as exc:
            QMessageBox.warning(self, "Privatsphäre-Sperre", str(exc))
            return
        self.config.auto_lock_minutes = self.auto_lock.value()
        self.repository.save(self.config)
        self.refresh()
        self.config_changed.emit(self.config.model_copy(deep=True))

    def remove_lock(self) -> None:
        self.config = self.repository.load()
        if not self.config.enabled:
            return
        if not self._current_authorized():
            self._clear_secret_fields()
            return
        answer = QMessageBox.question(
            self,
            "Privatsphäre-Sperre entfernen",
            "Lokale Oberflächen-Sperre wirklich deaktivieren? Chat- und Mediendaten werden dabei nicht gelöscht.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.config.clear_passphrase()
        self.repository.save(self.config)
        self.refresh()
        self.config_changed.emit(self.config.model_copy(deep=True))

    def save_auto_lock(self) -> None:
        self.config = self.repository.load()
        self.config.auto_lock_minutes = self.auto_lock.value() if self.config.enabled else 0
        self.repository.save(self.config)
        self.refresh()
        self.config_changed.emit(self.config.model_copy(deep=True))

    def request_lock(self) -> None:
        self.config = self.repository.load()
        if self.config.enabled and self.config.has_passphrase:
            self.lock_requested.emit()


class PrivacyActivityMonitor(QObject):
    lock_due = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._minutes = 0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.lock_due)

    def configure(self, minutes: int, *, active: bool) -> None:
        self._minutes = max(0, int(minutes))
        self._active = bool(active)
        self._restart()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if self._active and event.type() in {
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.TouchBegin,
        }:
            self._restart()
        return super().eventFilter(watched, event)

    def _restart(self) -> None:
        self._timer.stop()
        if self._active and self._minutes > 0:
            self._timer.start(self._minutes * 60 * 1000)
