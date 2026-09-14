from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.anti_repetition import AntiRepetitionConfig, AntiRepetitionRepository
from app.ai.creative_accents import (
    DetailAccent,
    DetailAccentRepository,
    MoodGrade,
    MoodGradeRepository,
)


class MoodGradeWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: MoodGradeRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Mood-Grades verändern nur die temporäre Licht-/Farbstimmung für Chat und lokale Medien. "
            "Character-Identität, Persona und Memory bleiben unverändert."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.activate_button = QPushButton("Mood aktivieren")
        self.draw_button = QPushButton("🎲 Mood wechseln")
        self.clear_button = QPushButton("Basis-Mood")

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.draw_button)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.activate_button.clicked.connect(self.activate_selected)
        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear)
        self._reload()

    def _reload(self) -> None:
        active = self.repository.active(self.conversation_id)
        active_id = active.id if active else None
        self.combo.clear()
        for grade in self.repository.list_grades():
            self.combo.addItem(grade.name, grade.id)
        if active_id:
            index = self.combo.findData(active_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, grade: MoodGrade | None) -> None:
        if grade is None:
            self.status.setText("Kein zusätzliches Mood-Grade aktiv.")
            return
        self.status.setText(f"Aktiv: {grade.name}\n{grade.description}\n{grade.prompt}")

    def activate_selected(self) -> None:
        grade_id = str(self.combo.currentData() or "")
        if not grade_id:
            return
        grade = self.repository.set_active(self.conversation_id, grade_id)
        self._render(grade)
        self.changed.emit(grade)

    def draw(self) -> None:
        grade = self.repository.draw(self.conversation_id)
        self._reload()
        self.changed.emit(grade)

    def clear(self) -> None:
        self.repository.set_active(self.conversation_id, None)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class DetailAccentWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: DetailAccentRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Detail-Akzente streuen kleine Props, Materialien oder Bilddetails ein. Sie sind temporär und "
            "sollen wiederkehrende Posen und Szenenbilder aufbrechen, ohne Langzeitlernen auszulösen."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.activate_button = QPushButton("Detail aktivieren")
        self.draw_button = QPushButton("🎲 Detail wechseln")
        self.clear_button = QPushButton("Ohne Zusatzdetail")

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.draw_button)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.activate_button.clicked.connect(self.activate_selected)
        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear)
        self._reload()

    def _reload(self) -> None:
        active = self.repository.active(self.conversation_id)
        active_id = active.id if active else None
        self.combo.clear()
        for accent in self.repository.list_accents():
            self.combo.addItem(accent.name, accent.id)
        if active_id:
            index = self.combo.findData(active_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, accent: DetailAccent | None) -> None:
        if accent is None:
            self.status.setText("Kein zusätzlicher Detail-Akzent aktiv.")
            return
        self.status.setText(f"Aktiv: {accent.name}\n{accent.description}\n{accent.prompt}")

    def activate_selected(self) -> None:
        accent_id = str(self.combo.currentData() or "")
        if not accent_id:
            return
        accent = self.repository.set_active(self.conversation_id, accent_id)
        self._render(accent)
        self.changed.emit(accent)

    def draw(self) -> None:
        accent = self.repository.draw(self.conversation_id)
        self._reload()
        self.changed.emit(accent)

    def clear(self) -> None:
        self.repository.set_active(self.conversation_id, None)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class AntiRepetitionWidget(QWidget):
    config_changed = Signal()

    def __init__(
        self,
        repository: AntiRepetitionRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Der Anti-Wiederholungs-Tracker arbeitet vollständig lokal. Er merkt sich nur kompakte Muster "
            "der letzten Antworten und gibt der nächsten Antwort einen weichen Hinweis, wenn Formulierungen "
            "oder dieselbe kreative Kombination zu oft wiederkehren. Persona und Memory werden nicht verändert."
        )
        intro.setWordWrap(True)
        self.enabled = QCheckBox("Anti-Wiederholung aktiv")
        self.window = QSpinBox()
        self.window.setRange(4, 20)
        self.window.setSuffix(" Antworten")
        self.opening_threshold = QSpinBox()
        self.opening_threshold.setRange(2, 5)
        self.creative_threshold = QSpinBox()
        self.creative_threshold.setRange(2, 8)

        form = QFormLayout()
        form.addRow("Aktiv", self.enabled)
        form.addRow("Betrachtetes Fenster", self.window)
        form.addRow("Gleicher Antwortanfang ab", self.opening_threshold)
        form.addRow("Gleiche kreative Kombination ab", self.creative_threshold)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.save_button = QPushButton("Anti-Wiederholung speichern")
        self.reset_button = QPushButton("Musterverlauf zurücksetzen")
        row = QHBoxLayout()
        row.addWidget(self.reset_button)
        row.addStretch(1)
        row.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.save_button.clicked.connect(self.save_config)
        self.reset_button.clicked.connect(self.reset_history)
        self.refresh()

    def refresh(self) -> None:
        config = self.repository.config(self.conversation_id)
        self.enabled.setChecked(config.enabled)
        self.window.setValue(config.window)
        self.opening_threshold.setValue(config.opening_threshold)
        self.creative_threshold.setValue(config.creative_threshold)
        count = len(self.repository.recent(self.conversation_id))
        state = "an" if config.enabled else "aus"
        self.status.setText(
            f"Status: {state} · {count} lokale Muster im aktuellen Analysefenster."
        )

    def save_config(self) -> None:
        config = AntiRepetitionConfig(
            enabled=self.enabled.isChecked(),
            window=self.window.value(),
            opening_threshold=self.opening_threshold.value(),
            creative_threshold=self.creative_threshold.value(),
        )
        self.repository.set_config(self.conversation_id, config)
        self.refresh()
        self.config_changed.emit()

    def reset_history(self) -> None:
        self.repository.reset(self.conversation_id)
        self.refresh()
        self.config_changed.emit()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()


class CreativeAccentsPanel(QWidget):
    mood_changed = Signal(object)
    detail_changed = Signal(object)
    anti_repetition_changed = Signal()

    def __init__(
        self,
        moods: MoodGradeRepository,
        details: DetailAccentRepository,
        anti_repetition: AntiRepetitionRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.moods = MoodGradeWidget(moods, conversation_id)
        self.details = DetailAccentWidget(details, conversation_id)
        self.anti_repetition = AntiRepetitionWidget(anti_repetition, conversation_id)

        tabs = QTabWidget()
        tabs.addTab(self.moods, "Mood-Grading")
        tabs.addTab(self.details, "Details & Props")
        tabs.addTab(self.anti_repetition, "Anti-Wiederholung")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self.moods.changed.connect(self.mood_changed)
        self.details.changed.connect(self.detail_changed)
        self.anti_repetition.config_changed.connect(self.anti_repetition_changed)

    def refresh_from_repositories(self) -> None:
        self.moods.set_conversation(self.conversation_id)
        self.details.set_conversation(self.conversation_id)
        self.anti_repetition.set_conversation(self.conversation_id)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh_from_repositories()
