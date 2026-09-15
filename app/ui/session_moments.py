from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.twist_deck import TwistCard, TwistConfig, TwistDeckRepository
from app.memory.session_moments import SessionMoment, SessionMomentRepository


class SessionMomentsWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: SessionMomentRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id
        self._moments: dict[str, SessionMoment] = {}

        intro = QLabel(
            "Momente speichern den letzten vollständigen Austausch als bewusst gewählten Wiedereinstieg. "
            "Sie sind kein Core Memory und werden nur als temporärer Kontext verwendet, wenn du sie aktivierst."
        )
        intro.setWordWrap(True)

        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Name des Moments")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optionaler Hinweis für den späteren Wiedereinstieg")
        self.capture_button = QPushButton("Letzten Austausch als Moment speichern")
        self.activate_button = QPushButton("Als Wiedereinstieg aktivieren")
        self.clear_button = QPushButton("Wiedereinstieg beenden")
        self.delete_button = QPushButton("Moment löschen")

        form = QFormLayout()
        form.addRow("Name", self.title)
        form.addRow("Hinweis", self.note)

        row = QHBoxLayout()
        row.addWidget(self.delete_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.capture_button)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.combo.currentIndexChanged.connect(self._render)
        self.capture_button.clicked.connect(self.capture)
        self.activate_button.clicked.connect(self.activate_selected)
        self.clear_button.clicked.connect(self.clear)
        self.delete_button.clicked.connect(self.delete_selected)
        self.refresh()

    def refresh(self, select_id: str | None = None) -> None:
        moments = self.repository.list_moments(self.conversation_id)
        self._moments = {item.id: item for item in moments}
        active = self.repository.active(self.conversation_id)
        wanted = select_id or (active.id if active else str(self.combo.currentData() or ""))
        self.combo.blockSignals(True)
        self.combo.clear()
        for moment in moments:
            marker = " • aktiv" if active and moment.id == active.id else ""
            self.combo.addItem(f"{moment.title}{marker}", moment.id)
        index = self.combo.findData(wanted)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)
        self._render()

    def _selected(self) -> SessionMoment | None:
        return self._moments.get(str(self.combo.currentData() or ""))

    def _render(self) -> None:
        moment = self._selected()
        active = self.repository.active(self.conversation_id)
        self.clear_button.setEnabled(active is not None)
        self.activate_button.setEnabled(moment is not None)
        self.delete_button.setEnabled(moment is not None)
        if moment is None:
            self.status.setText("Noch kein gespeicherter Moment in dieser Unterhaltung.")
            return
        note = f"\nHinweis: {moment.note}" if moment.note else ""
        active_text = "\nAktuell als Wiedereinstieg aktiv." if active and active.id == moment.id else ""
        self.status.setText(
            f"{moment.title}{active_text}{note}\n\nDu: {moment.user_excerpt}\nCompanion: {moment.assistant_excerpt}"
        )

    def capture(self) -> None:
        title = self.title.text().strip()
        if not title:
            QMessageBox.information(self, "Session-Moment", "Bitte einen Namen für den Moment eingeben.")
            return
        try:
            moment = self.repository.capture_latest(
                self.conversation_id,
                title=title,
                note=self.note.text(),
            )
        except ValueError as exc:
            QMessageBox.information(self, "Session-Moment", str(exc))
            return
        self.title.clear()
        self.note.clear()
        self.refresh(select_id=moment.id)

    def activate_selected(self) -> None:
        moment = self._selected()
        if moment is None:
            return
        active = self.repository.set_active(self.conversation_id, moment.id)
        self.refresh(select_id=moment.id)
        self.changed.emit(active)

    def clear(self) -> None:
        self.repository.clear(self.conversation_id)
        self.refresh()
        self.changed.emit(None)

    def delete_selected(self) -> None:
        moment = self._selected()
        if moment is None:
            return
        answer = QMessageBox.question(
            self,
            "Session-Moment löschen",
            f"Moment „{moment.title}“ wirklich löschen?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        was_active = self.repository.active(self.conversation_id)
        self.repository.delete(moment.id)
        self.refresh()
        if was_active and was_active.id == moment.id:
            self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()


class TwistDeckWidget(QWidget):
    changed = Signal(object)
    config_changed = Signal()

    def __init__(
        self,
        repository: TwistDeckRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Twists sind einmalige kreative Impulse für die nächste Antwort: kleine Licht-, Kamera-, "
            "Raum-, Dialog- oder Detailwechsel. Nach der verwendeten Antwort verschwinden sie automatisch."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.activate_button = QPushButton("Ausgewählten Twist aktivieren")
        self.draw_button = QPushButton("🎲 Twist ziehen")
        self.clear_button = QPushButton("Twist entfernen")

        self.auto_enabled = QCheckBox("Twists gelegentlich automatisch vorbereiten")
        self.interval = QSpinBox()
        self.interval.setRange(2, 20)
        self.interval.setSuffix(" Antworten")
        self.save_config_button = QPushButton("Twist-Automatik speichern")
        form = QFormLayout()
        form.addRow("Automatik", self.auto_enabled)
        form.addRow("Mindestabstand", self.interval)

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.draw_button)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addLayout(form)
        layout.addWidget(self.save_config_button)
        layout.addStretch(1)
        layout.addLayout(row)

        self.activate_button.clicked.connect(self.activate_selected)
        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear)
        self.save_config_button.clicked.connect(self.save_config)
        self.refresh()

    def refresh(self) -> None:
        active = self.repository.active(self.conversation_id)
        active_id = active.id if active else None
        current = active_id or str(self.combo.currentData() or "")
        self.combo.blockSignals(True)
        self.combo.clear()
        for card in self.repository.list_cards():
            self.combo.addItem(f"{card.name} · {card.category}", card.id)
        index = self.combo.findData(current)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)

        config = self.repository.config(self.conversation_id)
        self.auto_enabled.setChecked(config.enabled)
        self.interval.setValue(config.interval)
        self.clear_button.setEnabled(active is not None)
        if active is None:
            state = "Automatik an" if config.enabled else "Automatik aus"
            self.status.setText(f"Kein Twist für die nächste Antwort aktiv. {state}.")
        else:
            self.status.setText(
                f"Nächste Antwort: {active.name}\n{active.instruction}\nDanach wird dieser Twist automatisch entfernt."
            )

    def activate_selected(self) -> None:
        card_id = str(self.combo.currentData() or "")
        if not card_id:
            return
        card = self.repository.set_active(self.conversation_id, card_id)
        self.refresh()
        self.changed.emit(card)

    def draw(self) -> None:
        card = self.repository.draw(self.conversation_id)
        self.refresh()
        self.changed.emit(card)

    def clear(self) -> None:
        self.repository.clear(self.conversation_id)
        self.refresh()
        self.changed.emit(None)

    def save_config(self) -> None:
        self.repository.set_config(
            self.conversation_id,
            TwistConfig(enabled=self.auto_enabled.isChecked(), interval=self.interval.value()),
        )
        self.refresh()
        self.config_changed.emit()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()


class SessionMomentsTwistsPanel(QWidget):
    moment_changed = Signal(object)
    twist_changed = Signal(object)
    twist_config_changed = Signal()

    def __init__(
        self,
        moment_repository: SessionMomentRepository,
        twist_repository: TwistDeckRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.moments = SessionMomentsWidget(moment_repository, conversation_id)
        self.twists = TwistDeckWidget(twist_repository, conversation_id)

        tabs = QTabWidget()
        tabs.addTab(self.moments, "Momente")
        tabs.addTab(self.twists, "Twist-Deck")
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self.moments.changed.connect(self.moment_changed)
        self.twists.changed.connect(self.twist_changed)
        self.twists.config_changed.connect(self.twist_config_changed)

    def refresh_from_repositories(self) -> None:
        self.moments.refresh()
        self.twists.refresh()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.moments.set_conversation(conversation_id)
        self.twists.set_conversation(conversation_id)
