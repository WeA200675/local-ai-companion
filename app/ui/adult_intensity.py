from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ai.adult_intensity import (
    KINK_LEVELS,
    SEXUALITY_LEVELS,
    AdultIntensityConfig,
    AdultIntensityRepository,
)


class AdultIntensityWidget(QWidget):
    """Conversation-scoped user controls for adult tone and kink intensity."""

    config_changed = Signal(object)

    def __init__(
        self,
        repository: AdultIntensityRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id
        self._loading = False

        intro = QLabel(
            "Steuert getrennt, wie sexuell und wie kink-/perversitätsorientiert die aktuelle Unterhaltung "
            "werden darf. Die Werte gelten nur für diese Unterhaltung und verändern weder Persona noch Memory."
        )
        intro.setWordWrap(True)

        self.sexuality_current = QComboBox()
        self.sexuality_current.addItems(list(SEXUALITY_LEVELS))
        self.sexuality_max = QComboBox()
        self.sexuality_max.addItems(list(SEXUALITY_LEVELS))
        self.sexuality_locked = QCheckBox("Aktuelle Sexualitätsstufe sperren")

        sexuality_box = QGroupBox("Sexualität")
        sexuality_form = QFormLayout(sexuality_box)
        sexuality_form.addRow("Aktuelle Stufe", self.sexuality_current)
        sexuality_form.addRow("Erlaubtes Maximum", self.sexuality_max)
        sexuality_form.addRow("", self.sexuality_locked)

        self.kink_current = QComboBox()
        self.kink_current.addItems(list(KINK_LEVELS))
        self.kink_max = QComboBox()
        self.kink_max.addItems(list(KINK_LEVELS))
        self.kink_locked = QCheckBox("Aktuelle Kink-/Perversitätsstufe sperren")

        kink_box = QGroupBox("Kink / Perversitätsintensität")
        kink_form = QFormLayout(kink_box)
        kink_form.addRow("Aktuelle Stufe", self.kink_current)
        kink_form.addRow("Erlaubtes Maximum", self.kink_max)
        kink_form.addRow("", self.kink_locked)

        self.dynamic = QCheckBox(
            "Dynamische Steigerung: bei einem klaren Wunsch nach mehr Intensität schrittweise mitgehen"
        )
        self.dynamic.setToolTip(
            "Erhöht nur die aktuelle Session-Stufe bis zum eingestellten Maximum. Maxima, Locks, Persona und Memory bleiben unverändert."
        )

        self.preferences = QPlainTextEdit()
        self.preferences.setPlaceholderText(
            "Erwünschte Kinks/Themen, durch Komma oder neue Zeile getrennt …"
        )
        self.preferences.setMaximumHeight(90)

        self.boundaries = QPlainTextEdit()
        self.boundaries.setPlaceholderText(
            "Harte Grenzen/Tabus, durch Komma oder neue Zeile getrennt …"
        )
        self.boundaries.setMaximumHeight(90)

        preference_box = QGroupBox("Wünsche & Grenzen")
        preference_form = QFormLayout(preference_box)
        preference_form.addRow("Erwünscht", self.preferences)
        preference_form.addRow("Tabu / Grenze", self.boundaries)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.save_button = QPushButton("Intimitätsprofil speichern")
        self.reset_button = QPushButton("Aktuelle Stufen auf sanften Einstieg zurücksetzen")

        button_row = QHBoxLayout()
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.reset_button)
        button_row.addStretch(1)

        note = QLabel(
            "Die dynamische Steigerung reagiert nur auf direkte Signale des Benutzers. Ein Wunsch nach weniger "
            "oder nach Stopp senkt die Session-Stufe sofort. Visuelle Medien bleiben unabhängig davon auf "
            "erwachsene, nicht-grafische Darstellung begrenzt."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(sexuality_box)
        layout.addWidget(kink_box)
        layout.addWidget(self.dynamic)
        layout.addWidget(preference_box)
        layout.addLayout(button_row)
        layout.addWidget(self.status)
        layout.addWidget(note)
        layout.addStretch(1)

        self.save_button.clicked.connect(self.save)
        self.reset_button.clicked.connect(self.reset_levels)
        self.sexuality_max.currentIndexChanged.connect(self._keep_sexuality_in_bounds)
        self.kink_max.currentIndexChanged.connect(self._keep_kink_in_bounds)

        self.refresh()

    @staticmethod
    def _lines(text: str) -> list[str]:
        return [item.strip() for item in text.replace("\n", ",").split(",") if item.strip()]

    def _keep_sexuality_in_bounds(self) -> None:
        if self.sexuality_current.currentIndex() > self.sexuality_max.currentIndex():
            self.sexuality_current.setCurrentIndex(self.sexuality_max.currentIndex())

    def _keep_kink_in_bounds(self) -> None:
        if self.kink_current.currentIndex() > self.kink_max.currentIndex():
            self.kink_current.setCurrentIndex(self.kink_max.currentIndex())

    def _from_controls(self) -> AdultIntensityConfig:
        return AdultIntensityConfig(
            sexuality_current=self.sexuality_current.currentIndex(),
            sexuality_max=self.sexuality_max.currentIndex(),
            sexuality_locked=self.sexuality_locked.isChecked(),
            kink_current=self.kink_current.currentIndex(),
            kink_max=self.kink_max.currentIndex(),
            kink_locked=self.kink_locked.isChecked(),
            dynamic_escalation=self.dynamic.isChecked(),
            kink_preferences=self._lines(self.preferences.toPlainText()),
            boundaries=self._lines(self.boundaries.toPlainText()),
        )

    def refresh(self) -> None:
        config = self.repository.config(self.conversation_id)
        self._loading = True
        try:
            self.sexuality_current.setCurrentIndex(config.sexuality_current)
            self.sexuality_max.setCurrentIndex(config.sexuality_max)
            self.sexuality_locked.setChecked(config.sexuality_locked)
            self.kink_current.setCurrentIndex(config.kink_current)
            self.kink_max.setCurrentIndex(config.kink_max)
            self.kink_locked.setChecked(config.kink_locked)
            self.dynamic.setChecked(config.dynamic_escalation)
            self.preferences.setPlainText("\n".join(config.kink_preferences))
            self.boundaries.setPlainText("\n".join(config.boundaries))
            self._set_status(config)
        finally:
            self._loading = False

    def _set_status(self, config: AdultIntensityConfig) -> None:
        dynamic = "an" if config.dynamic_escalation else "aus"
        self.status.setText(
            f"Aktiv: Sexualität {config.sexuality_label} ({config.sexuality_current}/4, max {config.sexuality_max}/4) · "
            f"Kink {config.kink_label} ({config.kink_current}/4, max {config.kink_max}/4) · Dynamik {dynamic}"
        )

    def save(self) -> None:
        config = self.repository.set_config(self.conversation_id, self._from_controls())
        self._set_status(config)
        self.config_changed.emit(config.model_copy(deep=True))

    def reset_levels(self) -> None:
        config = self._from_controls()
        saved = self.repository.set_config(self.conversation_id, config)
        saved = self.repository.reset_session_levels(self.conversation_id)
        self.refresh()
        self.config_changed.emit(saved.model_copy(deep=True))

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()
