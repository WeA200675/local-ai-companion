from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.media.coverage import VisualCoverageConfig, VisualCoverageRepository


class VisualCoverageWidget(QWidget):
    """Local transparency/control view for generated-media coverage balancing."""

    def __init__(
        self,
        repository: VisualCoverageRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Visual Coverage merkt sich lokal nur kompakte kreative Kategorien bereits erzeugter Medien. "
            "Es analysiert keine Bildpixel. Bei Wiederholungen kann es dem lokalen Medienplaner einen weichen "
            "Abwechslungs-Hinweis geben; aktuelle Wünsche, Locks und Character-Identität haben immer Vorrang."
        )
        intro.setWordWrap(True)

        self.enabled = QCheckBox("Abwechslungs-Hinweise für neue Medien aktivieren")
        self.window = QSpinBox()
        self.window.setRange(6, 60)
        self.window.setSuffix(" Medien")
        self.save_button = QPushButton("Einstellung speichern")
        self.reset_button = QPushButton("Coverage-Verlauf zurücksetzen")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Auswertungsfenster", self.window)
        form.addRow("", self.enabled)

        buttons = QHBoxLayout()
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        layout.addWidget(self.details, 1)

        self.save_button.clicked.connect(self.save_config)
        self.reset_button.clicked.connect(self.reset_history)
        self.refresh()

    def refresh(self) -> None:
        config = self.repository.config(self.conversation_id)
        self.enabled.setChecked(config.enabled)
        self.window.setValue(config.recent_window)
        summary = self.repository.summary(self.conversation_id)
        guidance = self.repository.guidance(self.conversation_id)
        self.status.setText(
            f"{summary.sample_count} erzeugte Medien im aktuellen Fenster · "
            f"Hinweise {'aktiv' if config.enabled else 'aus'}"
        )

        lines = [
            "Verteilung im aktuellen lokalen Fenster:",
            "",
        ]
        for dimension in summary.dimensions:
            used = [
                (dimension.labels[item_id], count)
                for item_id, count in dimension.counts.items()
                if count > 0
            ]
            used.sort(key=lambda item: (-item[1], item[0].casefold()))
            if used:
                values = ", ".join(f"{label} ×{count}" for label, count in used[:8])
            else:
                values = "noch keine Daten"
            lines.append(f"{dimension.label}: {values}")

        lines.extend(["", "Aktueller weicher Hinweis an den Medienplaner:"])
        lines.append(guidance or "Noch keiner — dafür sind mindestens vier erzeugte Medien nötig.")
        self.details.setPlainText("\n".join(lines))

    def save_config(self) -> None:
        self.repository.set_config(
            self.conversation_id,
            VisualCoverageConfig(
                enabled=self.enabled.isChecked(),
                recent_window=self.window.value(),
            ),
        )
        self.refresh()

    def reset_history(self) -> None:
        self.repository.reset(self.conversation_id)
        self.refresh()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.refresh()
        super().showEvent(event)
