from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
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
from app.settings import AppSettings


class SettingsWidget(QWidget):
    settings_saved = Signal(object)

    def __init__(
        self,
        store: StateStore,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings.model_copy(deep=True)

        self.model_name = QLineEdit(settings.model_name)
        self.model_url = QLineEdit(settings.model_url)
        self.media_enabled = QCheckBox("Lokale Mediengenerierung aktivieren")
        self.media_enabled.setChecked(settings.media_enabled)
        self.media_url = QLineEdit(settings.media_url)
        self.media_workflow = QLineEdit(settings.media_workflow)
        self.media_positive_node = QLineEdit(settings.media_positive_node)
        self.media_negative_node = QLineEdit(settings.media_negative_node)
        self.media_seed_node = QLineEdit(settings.media_seed_node)
        self.media_output_dir = QLineEdit(settings.media_output_dir)
        self.continuity_enabled = QCheckBox("Wiederkehrende Figur visuell stabil halten")
        self.continuity_enabled.setChecked(settings.continuity_enabled)
        self.continuity_key = QLineEdit(settings.continuity_key)
        self.learning_snapshots = QCheckBox("Vor/nach Lernschritten automatisch Snapshots anlegen")
        self.learning_snapshots.setChecked(settings.learning_snapshots)
        self.history_limit = QSpinBox()
        self.history_limit.setRange(10, 5000)
        self.history_limit.setValue(settings.media_history_limit)

        workflow_row = QWidget()
        workflow_layout = QHBoxLayout(workflow_row)
        workflow_layout.setContentsMargins(0, 0, 0, 0)
        workflow_layout.addWidget(self.media_workflow, 1)
        workflow_browse = QPushButton("…")
        workflow_browse.setToolTip("ComfyUI API-Workflow auswählen")
        workflow_layout.addWidget(workflow_browse)

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.media_output_dir, 1)
        output_browse = QPushButton("…")
        output_browse.setToolTip("Lokalen Ausgabeordner auswählen")
        output_layout.addWidget(output_browse)

        form = QFormLayout()
        form.addRow("Lokales Sprachmodell", self.model_name)
        form.addRow("Ollama/API-URL", self.model_url)
        form.addRow("Medien", self.media_enabled)
        form.addRow("ComfyUI-URL", self.media_url)
        form.addRow("API-Workflow", workflow_row)
        form.addRow("Positive Prompt Node", self.media_positive_node)
        form.addRow("Negative Prompt Node", self.media_negative_node)
        form.addRow("Seed Node", self.media_seed_node)
        form.addRow("Medien-Ausgabe", output_row)
        form.addRow("Character-Continuity", self.continuity_enabled)
        form.addRow("Continuity-Key", self.continuity_key)
        form.addRow("Lern-Snapshots", self.learning_snapshots)
        form.addRow("Medienhistorie max.", self.history_limit)

        self.status = QLabel(
            "Alle Einstellungen werden nur lokal in data/companion.sqlite3 gespeichert."
        )
        self.status.setWordWrap(True)
        self.save_button = QPushButton("Einstellungen speichern")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addWidget(self.save_button)

        workflow_browse.clicked.connect(self._choose_workflow)
        output_browse.clicked.connect(self._choose_output_dir)
        self.save_button.clicked.connect(self.save)

    def _choose_workflow(self) -> None:
        current = self.media_workflow.text().strip()
        start = str(Path(current).parent) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "ComfyUI API-Workflow auswählen",
            start,
            "JSON (*.json);;Alle Dateien (*)",
        )
        if path:
            self.media_workflow.setText(path)

    def _choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Ausgabeordner auswählen",
            self.media_output_dir.text().strip(),
        )
        if path:
            self.media_output_dir.setText(path)

    def save(self) -> None:
        try:
            settings = AppSettings(
                model_name=self.model_name.text(),
                model_url=self.model_url.text(),
                media_enabled=self.media_enabled.isChecked(),
                media_url=self.media_url.text(),
                media_workflow=self.media_workflow.text(),
                media_positive_node=self.media_positive_node.text(),
                media_negative_node=self.media_negative_node.text(),
                media_seed_node=self.media_seed_node.text(),
                media_output_dir=self.media_output_dir.text(),
                continuity_enabled=self.continuity_enabled.isChecked(),
                continuity_key=self.continuity_key.text(),
                learning_snapshots=self.learning_snapshots.isChecked(),
                media_history_limit=self.history_limit.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return

        self.settings = settings
        self.store.save_settings(settings)
        self.status.setText("Gespeichert. Lokale Backends werden jetzt neu konfiguriert.")
        self.settings_saved.emit(settings)
