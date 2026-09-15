from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ai.scenario_seeds import (
    ScenarioSeedEngine,
    ScenarioSeedRepository,
    ScenarioSeedSelection,
)


class ScenarioSeedWidget(QWidget):
    """Generate coherent temporary session bundles from compatible creative layers."""

    changed = Signal(object)

    def __init__(
        self,
        engine: ScenarioSeedEngine,
        repository: ScenarioSeedRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.repository = repository
        self.conversation_id = conversation_id
        self.assistant_count_provider = assistant_count_provider

        intro = QLabel(
            "Session Studio kombiniert Look, Impuls, Arc, Scene Mixer, Visual-Motiv, Mood, Details, "
            "Scene Evolution und Ritual aus zueinander passenden Pools. Kreative Locks bleiben erhalten. "
            "Die Auswahl ist nur temporärer Session-Kontext und verändert weder Persona noch Memory."
        )
        intro.setWordWrap(True)

        self.template_combo = QComboBox()
        self.template_combo.addItem("🎲 Überraschung — kompatibel gemischt", "")
        for template in self.engine.templates():
            self.template_combo.addItem(template.name, template.id)

        self.include_evolution = QCheckBox("Scene Evolution einbeziehen")
        self.include_evolution.setChecked(True)
        self.include_ritual = QCheckBox("Ritual einbeziehen")
        self.include_ritual.setChecked(True)
        self.automatic_sequences = QCheckBox("Evolution und Ritual automatisch weiterführen")
        self.automatic_sequences.setChecked(True)

        form = QFormLayout()
        form.addRow("Session-Thema", self.template_combo)
        form.addRow("", self.include_evolution)
        form.addRow("", self.include_ritual)
        form.addRow("", self.automatic_sequences)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        self.apply_button = QPushButton("🎲 Stimmige Session erzeugen")
        self.restore_button = QPushButton("↶ Vorherigen Zustand wiederherstellen")
        self.clear_button = QPushButton("Seed-Markierung lösen")

        buttons = QHBoxLayout()
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(self.details, 1)
        layout.addLayout(buttons)

        self.apply_button.clicked.connect(self.apply_seed)
        self.restore_button.clicked.connect(self.restore_previous)
        self.clear_button.clicked.connect(self.clear_marker)
        self.refresh_from_repository()

    def _render(self, selection: ScenarioSeedSelection | None) -> None:
        enabled = selection is not None
        self.restore_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        if selection is None:
            self.status.setText("Kein Session-Seed aktiv. Einzelne kreative Ebenen können trotzdem aktiv sein.")
            self.details.setPlainText(
                "Ein Session-Seed ist ein reversibler Ausgangspunkt, kein Lock. Nach dem Anwenden kannst du "
                "jede kreative Ebene weiterhin einzeln verändern."
            )
            return

        media = {
            "auto": "automatisch",
            "image": "Bild bevorzugt",
            "motion": "Motion bevorzugt, sofern lokaler Workflow verfügbar",
        }[selection.media_preference]
        preserved = ", ".join(selection.preserved_layers) or "keine"
        self.status.setText(
            f"Aktiv: {selection.template_name} · Kompatibilität {selection.compatibility_score}% · "
            f"Medienmodus: {media}"
        )

        lines = [
            selection.description,
            "",
            f"Reproduzierbarer Zufalls-Seed: {selection.random_seed}",
            f"Erhaltene/gesperrte Ebenen: {preserved}",
            "",
            "Ausgewählte Ebenen:",
        ]
        for label, value in selection.layer_summary.items():
            lines.append(f"  • {label}: {value}")
        if selection.compatibility_notes:
            lines.extend(["", "Kompatibilitäts-Hinweise:"])
            lines.extend(f"  • {item}" for item in selection.compatibility_notes)
        lines.extend(
            [
                "",
                "Der Seed ist nur der Session-Ursprung. Manuelle Änderungen danach bleiben möglich und werden "
                "nicht automatisch zurückgedreht.",
            ]
        )
        self.details.setPlainText("\n".join(lines))

    def apply_seed(self) -> None:
        template_id = str(self.template_combo.currentData() or "") or None
        selection = self.engine.generate(
            self.conversation_id,
            template_id=template_id,
            include_evolution=self.include_evolution.isChecked(),
            include_ritual=self.include_ritual.isChecked(),
            automatic_sequences=self.automatic_sequences.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(selection)
        self.changed.emit(selection)

    def restore_previous(self) -> None:
        if not self.engine.restore_previous(self.conversation_id):
            return
        self._render(None)
        self.changed.emit(None)

    def clear_marker(self) -> None:
        self.repository.clear(self.conversation_id)
        self._render(None)
        self.changed.emit(None)

    def refresh_from_repository(self) -> None:
        self._render(self.repository.active(self.conversation_id))

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh_from_repository()
