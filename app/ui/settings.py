from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.diagnostics import DiagnosticResult, run_diagnostics
from app.memory.store import StateStore
from app.settings import AppSettings


class DiagnosticsWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)

    def run(self) -> None:
        try:
            results = run_diagnostics(self._settings)
        except Exception as exc:  # diagnostics must never crash settings UI
            self.failed.emit(str(exc))
            return
        self.completed.emit(results)


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
        self._diagnostics_worker: DiagnosticsWorker | None = None

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
        self.adaptive_memory_enabled = QCheckBox("Lokales adaptives Langzeit-Memory aktivieren")
        self.adaptive_memory_enabled.setChecked(settings.adaptive_memory_enabled)
        self.adaptive_memory_interval = QSpinBox()
        self.adaptive_memory_interval.setRange(1, 20)
        self.adaptive_memory_interval.setSuffix(" Antworten")
        self.adaptive_memory_interval.setValue(settings.adaptive_memory_interval)
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
        form.addRow("Adaptives Memory", self.adaptive_memory_enabled)
        form.addRow("Memory-Prüfung alle", self.adaptive_memory_interval)
        form.addRow("Medienhistorie max.", self.history_limit)

        self.preference_summary = QLabel()
        self.preference_summary.setWordWrap(True)
        self._refresh_preference_summary()

        self.status = QLabel(
            "Alle Einstellungen, Memory-Einträge und Lernzustände werden nur lokal gespeichert."
        )
        self.status.setWordWrap(True)
        self.diagnostics_output = QPlainTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setMaximumHeight(130)
        self.diagnostics_output.setPlaceholderText("Lokale Diagnose noch nicht ausgeführt.")

        self.test_button = QPushButton("Lokale Verbindungen testen")
        self.save_button = QPushButton("Einstellungen speichern")
        action_row = QHBoxLayout()
        action_row.addWidget(self.test_button)
        action_row.addStretch(1)
        action_row.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Gelernte visuelle Präferenzen"))
        layout.addWidget(self.preference_summary)
        layout.addWidget(self.status)
        layout.addWidget(self.diagnostics_output)
        layout.addStretch(1)
        layout.addLayout(action_row)

        workflow_browse.clicked.connect(self._choose_workflow)
        output_browse.clicked.connect(self._choose_output_dir)
        self.test_button.clicked.connect(self.run_diagnostics)
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

    def _settings_from_form(self) -> AppSettings:
        return AppSettings(
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
            adaptive_memory_enabled=self.adaptive_memory_enabled.isChecked(),
            adaptive_memory_interval=self.adaptive_memory_interval.value(),
            media_history_limit=self.history_limit.value(),
        )

    def _refresh_preference_summary(self) -> None:
        profile = self.store.load_visual_preferences()
        liked, disliked = profile.describe(limit=6)
        self.preference_summary.setText(
            f"Bevorzugt: {liked}\nEher vermeiden: {disliked}"
        )

    def run_diagnostics(self) -> None:
        if self._diagnostics_worker is not None and self._diagnostics_worker.isRunning():
            return
        try:
            settings = self._settings_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return

        self.test_button.setEnabled(False)
        self.diagnostics_output.setPlainText("Prüfe nur lokale Endpoints und Dateien …")
        worker = DiagnosticsWorker(settings, self)
        worker.completed.connect(self._diagnostics_completed)
        worker.failed.connect(self._diagnostics_failed)
        worker.finished.connect(self._diagnostics_finished)
        self._diagnostics_worker = worker
        worker.start()

    def _diagnostics_completed(self, results: list[DiagnosticResult]) -> None:
        lines = [f"[{result.marker}] {result.name}: {result.detail}" for result in results]
        self.diagnostics_output.setPlainText("\n".join(lines))

    def _diagnostics_failed(self, error: str) -> None:
        self.diagnostics_output.setPlainText(f"[FEHLER] Diagnose: {error}")

    def _diagnostics_finished(self) -> None:
        self.test_button.setEnabled(True)
        worker = self._diagnostics_worker
        self._diagnostics_worker = None
        if worker is not None:
            worker.deleteLater()

    def save(self) -> None:
        try:
            settings = self._settings_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return

        self.settings = settings
        self.store.save_settings(settings)
        self._refresh_preference_summary()
        self.status.setText("Gespeichert. Lokale Backends werden jetzt neu konfiguriert.")
        self.settings_saved.emit(settings)
