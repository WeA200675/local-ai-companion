from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.media.setup_assistant import (
    MediaSetupError,
    WorkflowAutoSetup,
    WorkflowSmokeTestResult,
    generated_catalog_path,
    inspect_for_auto_setup,
    run_workflow_smoke_test,
    save_generated_profile,
    settings_with_auto_setup,
)
from app.memory.store import StateStore
from app.settings import AppSettings
from app.ui.media_preview import MediaPreview


class MediaSetupWorker(QThread):
    completed = Signal(object, object, str, object)
    failed = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        workflow_path: str,
        *,
        run_render_test: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)
        self._workflow_path = workflow_path
        self._run_render_test = run_render_test

    def run(self) -> None:
        try:
            setup = inspect_for_auto_setup(self._workflow_path)
            if not setup.ready:
                details = [setup.inspection.error, *setup.warnings]
                message = "\n".join(item for item in details if item) or "Workflow nicht automatisch nutzbar"
                raise MediaSetupError(message)
            catalog = generated_catalog_path(self._settings)
            catalog = save_generated_profile(setup, catalog)
            configured = settings_with_auto_setup(self._settings, setup, catalog)
            render_result = (
                run_workflow_smoke_test(configured, setup)
                if self._run_render_test
                else None
            )
        except Exception as exc:  # wizard boundary: never crash the GUI thread
            self.failed.emit(str(exc))
            return
        self.completed.emit(setup, render_result, str(catalog), configured)


class MediaSetupWizard(QDialog):
    """One-click local ComfyUI workflow setup with an optional real smoke render."""

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
        self._worker: MediaSetupWorker | None = None
        self._inspection: WorkflowAutoSetup | None = None

        self.setWindowTitle("Local AI Companion — Medien automatisch einrichten")
        self.resize(900, 720)

        intro = QLabel(
            "Wähle einen exportierten ComfyUI-Workflow im API-JSON-Format. Der Assistent erkennt "
            "Prompt-/Seed-Nodes, erstellt lokal einen Workflow-Profilkatalog und kann anschließend "
            "einen echten, kleinen Test-Render ausführen. Bei Erfolg werden die Medien-Einstellungen "
            "direkt in der lokalen App-Datenbank gespeichert."
        )
        intro.setWordWrap(True)

        self.comfy_url = QLineEdit(settings.media_url)
        self.workflow_path = QLineEdit(settings.media_workflow)
        self.output_dir = QLineEdit(settings.media_output_dir)
        self.run_render_test = QCheckBox("Echten lokalen Test-Render ausführen")
        self.run_render_test.setChecked(True)
        self.run_render_test.setToolTip(
            "Empfohlen. Verifiziert Queue, Workflow-Ausführung, History und lokalen Download statt nur das JSON statisch zu prüfen."
        )

        workflow_row = QWidget()
        workflow_layout = QHBoxLayout(workflow_row)
        workflow_layout.setContentsMargins(0, 0, 0, 0)
        workflow_layout.addWidget(self.workflow_path, 1)
        browse_workflow = QPushButton("…")
        workflow_layout.addWidget(browse_workflow)

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output_dir, 1)
        browse_output = QPushButton("…")
        output_layout.addWidget(browse_output)

        form = QFormLayout()
        form.addRow("ComfyUI-URL", self.comfy_url)
        form.addRow("API-Workflow", workflow_row)
        form.addRow("Lokaler Ausgabeordner", output_row)
        form.addRow("Render-Verifikation", self.run_render_test)

        self.status = QLabel("Noch kein Workflow geprüft.")
        self.status.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Erkannte Nodes, Fähigkeiten und Test-Ergebnis erscheinen hier.")

        self.preview = MediaPreview()
        self.preview.setVisible(False)

        self.inspect_button = QPushButton("1 · Workflow analysieren")
        self.run_button = QPushButton("2 · Automatisch einrichten, testen & speichern")
        self.run_button.setEnabled(False)
        self.close_button = QPushButton("Schließen")

        buttons = QHBoxLayout()
        buttons.addWidget(self.inspect_button)
        buttons.addWidget(self.run_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)

        privacy_note = QLabel(
            "Alles bleibt lokal. Der Assistent installiert keine Modelle, LoRAs oder Custom Nodes und "
            "kontaktiert keine Cloud-Dienste. Der Test-Render verwendet nur eine einfache leere Studio-Szene."
        )
        privacy_note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(self.output, 1)
        layout.addWidget(self.preview, 2)
        layout.addLayout(buttons)
        layout.addWidget(privacy_note)

        browse_workflow.clicked.connect(self._choose_workflow)
        browse_output.clicked.connect(self._choose_output)
        self.workflow_path.textChanged.connect(self._workflow_changed)
        self.inspect_button.clicked.connect(self.inspect_workflow)
        self.run_button.clicked.connect(self.run_setup)
        self.close_button.clicked.connect(self.close)

        if settings.media_workflow:
            self.inspect_workflow()

    def _choose_workflow(self) -> None:
        current = self.workflow_path.text().strip()
        start = str(Path(current).parent) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "ComfyUI API-Workflow auswählen",
            start,
            "JSON (*.json);;Alle Dateien (*)",
        )
        if path:
            self.workflow_path.setText(path)
            self.inspect_workflow()

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Lokalen Medien-Ausgabeordner auswählen",
            self.output_dir.text().strip(),
        )
        if path:
            self.output_dir.setText(path)

    def _workflow_changed(self) -> None:
        self._inspection = None
        self.run_button.setEnabled(False)
        self.preview.setVisible(False)
        self.status.setText("Workflow geändert — bitte erneut analysieren.")

    def _settings_from_form(self) -> AppSettings:
        return self.settings.model_copy(
            update={
                "media_url": self.comfy_url.text().strip(),
                "media_workflow": self.workflow_path.text().strip(),
                "media_output_dir": self.output_dir.text().strip(),
            }
        )

    def inspect_workflow(self) -> None:
        path = self.workflow_path.text().strip()
        if not path:
            QMessageBox.information(
                self,
                "Medien-Setup",
                "Bitte zuerst einen exportierten ComfyUI API-Workflow auswählen.",
            )
            return
        setup = inspect_for_auto_setup(path)
        self._inspection = setup
        self.run_button.setEnabled(setup.ready)

        if not setup.ready or setup.profile is None or setup.capability is None:
            lines = ["[FEHLER] Workflow konnte nicht vollständig automatisch zugeordnet werden."]
            if setup.inspection.error:
                lines.append(setup.inspection.error)
            lines.extend(f"- {warning}" for warning in setup.warnings)
            self.output.setPlainText("\n".join(lines))
            self.status.setText("Automatisches Setup noch nicht möglich.")
            return

        controls = ", ".join(setup.capability.render_controls) or "Workflow-Defaults"
        lines = [
            "[OK] Workflow statisch nutzbar.",
            f"Profil: {setup.profile.id}",
            f"Positive Prompt Node: {setup.profile.positive_node}",
            f"Negative Prompt Node: {setup.profile.negative_node}",
            f"Seed Node: {setup.profile.seed_node}",
            f"Medienarten: {', '.join(setup.profile.kinds)}",
            f"Render-Steuerung: {controls}",
        ]
        if setup.warnings:
            lines.append("")
            lines.append("Hinweise:")
            lines.extend(f"- {warning}" for warning in setup.warnings)
        self.output.setPlainText("\n".join(lines))
        self.status.setText(
            "Analyse erfolgreich. Der nächste Schritt erstellt den lokalen Profilkatalog und verifiziert den Workflow."
        )

    def run_setup(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if self._inspection is None or not self._inspection.ready:
            self.inspect_workflow()
            if self._inspection is None or not self._inspection.ready:
                return
        try:
            settings = self._settings_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return

        self.inspect_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.status.setText(
            "Erstelle lokalen Profilkatalog und führe den ComfyUI-Test aus …"
            if self.run_render_test.isChecked()
            else "Erstelle lokalen Profilkatalog …"
        )
        self.output.appendPlainText("\n[START] Automatisches Medien-Setup läuft …")
        worker = MediaSetupWorker(
            settings,
            self.workflow_path.text().strip(),
            run_render_test=self.run_render_test.isChecked(),
            parent=self,
        )
        worker.completed.connect(self._setup_completed)
        worker.failed.connect(self._setup_failed)
        worker.finished.connect(self._setup_finished)
        self._worker = worker
        worker.start()

    def _setup_completed(
        self,
        setup: WorkflowAutoSetup,
        render_result: WorkflowSmokeTestResult | None,
        catalog: str,
        configured: AppSettings,
    ) -> None:
        self.store.save_settings(configured)
        self.settings = configured.model_copy(deep=True)
        self.settings_saved.emit(configured.model_copy(deep=True))

        lines = [
            "[OK] Automatisches Medien-Setup abgeschlossen.",
            f"Workflow-Profil: {setup.profile.id if setup.profile else 'unbekannt'}",
            f"Profilkatalog: {catalog}",
            "[OK] Mediengenerierung wurde in den lokalen App-Einstellungen aktiviert.",
        ]
        if render_result is not None:
            lines.extend(
                [
                    f"[OK] {render_result.summary()}",
                    f"Hardware: {render_result.hardware.summary()}",
                ]
            )
            self.preview.show_media(
                str(render_result.generated.path),
                description="Lokaler ComfyUI Setup-Test",
            )
            self.preview.setVisible(True)
        else:
            lines.append("[HINWEIS] Render-Test wurde übersprungen; die statische Workflow-Prüfung war erfolgreich.")
        self.output.setPlainText("\n".join(lines))
        self.status.setText(
            "Fertig. Beim nächsten App-Start wird der automatisch erzeugte Workflow-Profilkatalog verwendet."
        )

    def _setup_failed(self, error: str) -> None:
        self.output.appendPlainText(f"\n[FEHLER] {error}")
        self.status.setText(
            "Setup nicht gespeichert. Bestehende App-Einstellungen wurden nicht verändert."
        )

    def _setup_finished(self) -> None:
        self.inspect_button.setEnabled(True)
        self.run_button.setEnabled(bool(self._inspection and self._inspection.ready))
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
