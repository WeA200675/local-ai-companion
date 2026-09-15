from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from app.media.standard_workflow import (
    ComfyUICheckpointInventory,
    discover_checkpoint_inventory,
    save_standard_image_workflow,
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
        checkpoint_license_confirmed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)
        self._workflow_path = workflow_path
        self._run_render_test = run_render_test
        self._checkpoint_license_confirmed = checkpoint_license_confirmed

    def run(self) -> None:
        try:
            setup = inspect_for_auto_setup(
                self._workflow_path,
                checkpoint_license_confirmed=self._checkpoint_license_confirmed,
            )
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


class CheckpointDiscoveryWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        try:
            inventory = discover_checkpoint_inventory(self._base_url)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(inventory)


class MediaSetupWizard(QDialog):
    """One-click local ComfyUI setup with workflow generation and smoke rendering."""

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
        self._checkpoint_worker: CheckpointDiscoveryWorker | None = None
        self._inspection: WorkflowAutoSetup | None = None
        self._checkpoint_inventory: ComfyUICheckpointInventory | None = None
        self._license_confirmed_workflow_path = ""

        self.setWindowTitle("Local AI Companion — Medien automatisch einrichten")
        self.resize(960, 790)

        intro = QLabel(
            "Der Assistent kann jetzt entweder einen vorhandenen ComfyUI-API-Workflow analysieren oder "
            "aus einem bereits lokal installierten Checkpoint selbst einen Standard-Bildworkflow aus "
            "ComfyUI-Core-Nodes erzeugen. Danach werden Prompt-/Seed-Nodes erkannt, ein lokaler "
            "Profilkatalog erstellt und optional ein echter kleiner Test-Render ausgeführt."
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

        checkpoint_title = QLabel("Standard-Workflow automatisch erzeugen")
        checkpoint_title.setStyleSheet("font-weight: 600;")
        checkpoint_intro = QLabel(
            "ComfyUI kann seine bereits installierten Bild-Checkpoints über /object_info melden. "
            "Der Assistent lädt dabei nichts herunter. Wähle einen Checkpoint und erzeuge daraus einen "
            "minimalen Bildworkflow mit CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, "
            "KSampler, VAEDecode und SaveImage."
        )
        checkpoint_intro.setWordWrap(True)

        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setEnabled(False)
        self.checkpoint_combo.setMinimumWidth(420)
        self.discover_checkpoints_button = QPushButton("Installierte Checkpoints erkennen")
        self.generate_workflow_button = QPushButton("Standard-Bildworkflow erzeugen")
        self.generate_workflow_button.setEnabled(False)
        checkpoint_row = QHBoxLayout()
        checkpoint_row.addWidget(self.checkpoint_combo, 1)
        checkpoint_row.addWidget(self.discover_checkpoints_button)
        checkpoint_row.addWidget(self.generate_workflow_button)

        self.checkpoint_license_confirmed = QCheckBox(
            "Ich habe die Lizenz des ausgewählten Bild-Checkpoints separat geprüft und sie ist für dieses Open-Source-Projekt geeignet."
        )
        self.checkpoint_license_confirmed.setToolTip(
            "ComfyUI liefert über object_info nur technische Namen, keine verlässliche Lizenzmetadatenbank. "
            "Die App speichert nur deine explizite Bestätigung, nicht eine aus dem Dateinamen abgeleitete Lizenz."
        )

        self.status = QLabel("Noch kein Workflow geprüft.")
        self.status.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Erkannte Checkpoints, Nodes, Fähigkeiten und Test-Ergebnis erscheinen hier.")

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
            "Alles bleibt lokal. Der Assistent installiert keine Modelle, Checkpoints, LoRAs oder Custom Nodes und "
            "kontaktiert keine Cloud-Dienste. Der Test-Render verwendet nur eine einfache leere Studio-Szene. "
            "Ein automatisch gefundener Checkpoint gilt nicht automatisch als Open Source; seine Lizenz muss separat geprüft werden."
        )
        privacy_note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(checkpoint_title)
        layout.addWidget(checkpoint_intro)
        layout.addLayout(checkpoint_row)
        layout.addWidget(self.checkpoint_license_confirmed)
        layout.addWidget(self.status)
        layout.addWidget(self.output, 1)
        layout.addWidget(self.preview, 2)
        layout.addLayout(buttons)
        layout.addWidget(privacy_note)

        browse_workflow.clicked.connect(self._choose_workflow)
        browse_output.clicked.connect(self._choose_output)
        self.workflow_path.textChanged.connect(self._workflow_changed)
        self.comfy_url.textChanged.connect(self._endpoint_changed)
        self.checkpoint_combo.currentIndexChanged.connect(self._checkpoint_changed)
        self.checkpoint_license_confirmed.toggled.connect(self._checkpoint_license_toggled)
        self.discover_checkpoints_button.clicked.connect(self.discover_checkpoints)
        self.generate_workflow_button.clicked.connect(self.generate_standard_workflow)
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
        current = self.workflow_path.text().strip()
        if current != self._license_confirmed_workflow_path:
            self._license_confirmed_workflow_path = ""
        self._inspection = None
        self.run_button.setEnabled(False)
        self.preview.setVisible(False)
        self.status.setText("Workflow geändert — bitte erneut analysieren.")

    def _endpoint_changed(self) -> None:
        self._checkpoint_inventory = None
        self._license_confirmed_workflow_path = ""
        self.checkpoint_combo.clear()
        self.checkpoint_combo.setEnabled(False)
        self.checkpoint_license_confirmed.setChecked(False)
        self._refresh_generate_button()

    def _checkpoint_changed(self) -> None:
        self._license_confirmed_workflow_path = ""
        if self.checkpoint_license_confirmed.isChecked():
            self.checkpoint_license_confirmed.setChecked(False)
        self._refresh_generate_button()

    def _checkpoint_license_toggled(self, checked: bool) -> None:
        if not checked:
            self._license_confirmed_workflow_path = ""
        self._refresh_generate_button()

    def _refresh_generate_button(self) -> None:
        ready = bool(
            self._checkpoint_inventory
            and self.checkpoint_combo.currentText().strip()
            and self.checkpoint_license_confirmed.isChecked()
            and not (self._checkpoint_worker and self._checkpoint_worker.isRunning())
        )
        self.generate_workflow_button.setEnabled(ready)

    def _current_workflow_license_confirmed(self) -> bool:
        current = self.workflow_path.text().strip()
        return bool(current and current == self._license_confirmed_workflow_path)

    def discover_checkpoints(self) -> None:
        if self._checkpoint_worker is not None and self._checkpoint_worker.isRunning():
            return
        base_url = self.comfy_url.text().strip()
        if not base_url:
            QMessageBox.information(self, "ComfyUI", "Bitte zuerst eine lokale ComfyUI-URL eintragen.")
            return
        self.discover_checkpoints_button.setEnabled(False)
        self.generate_workflow_button.setEnabled(False)
        self.status.setText("Lese installierte Checkpoints direkt aus dem lokalen ComfyUI object_info …")
        worker = CheckpointDiscoveryWorker(base_url, self)
        worker.completed.connect(self._checkpoints_discovered)
        worker.failed.connect(self._checkpoint_discovery_failed)
        worker.finished.connect(self._checkpoint_discovery_finished)
        self._checkpoint_worker = worker
        worker.start()

    def _checkpoints_discovered(self, inventory: ComfyUICheckpointInventory) -> None:
        self._checkpoint_inventory = inventory
        self._license_confirmed_workflow_path = ""
        self.checkpoint_license_confirmed.setChecked(False)
        self.checkpoint_combo.clear()
        for checkpoint in inventory.checkpoints:
            self.checkpoint_combo.addItem(checkpoint)
        self.checkpoint_combo.setEnabled(bool(inventory.checkpoints))
        self.status.setText(
            f"{len(inventory.checkpoints)} lokale(r) Checkpoint(s) erkannt. "
            "Wähle einen aus und bestätige seine separat geprüfte Lizenz."
        )
        lines = ["[OK] ComfyUI object_info gelesen.", "Installierte Checkpoints:"]
        lines.extend(f"- {name}" for name in inventory.checkpoints)
        if inventory.sampler_names:
            lines.append(f"Sampler: {', '.join(inventory.sampler_names[:12])}")
        if inventory.schedulers:
            lines.append(f"Scheduler: {', '.join(inventory.schedulers[:12])}")
        lines.append("")
        lines.append(
            "Lizenz-Hinweis: Diese Namen stammen technisch aus ComfyUI. Daraus wird keine Open-Source-Lizenz abgeleitet."
        )
        self.output.setPlainText("\n".join(lines))
        self._refresh_generate_button()

    def _checkpoint_discovery_failed(self, error: str) -> None:
        self._checkpoint_inventory = None
        self._license_confirmed_workflow_path = ""
        self.checkpoint_combo.clear()
        self.checkpoint_combo.setEnabled(False)
        self.checkpoint_license_confirmed.setChecked(False)
        self.status.setText("Checkpoint-Erkennung fehlgeschlagen.")
        self.output.setPlainText(f"[FEHLER] {error}")

    def _checkpoint_discovery_finished(self) -> None:
        worker = self._checkpoint_worker
        self._checkpoint_worker = None
        self.discover_checkpoints_button.setEnabled(True)
        self._refresh_generate_button()
        if worker is not None:
            worker.deleteLater()

    def generate_standard_workflow(self) -> None:
        inventory = self._checkpoint_inventory
        checkpoint = self.checkpoint_combo.currentText().strip()
        if inventory is None or not checkpoint:
            return
        if not self.checkpoint_license_confirmed.isChecked():
            QMessageBox.information(
                self,
                "Checkpoint-Lizenz",
                "Bitte bestätige zuerst, dass du die Lizenz dieses Bild-Checkpoints separat geprüft hast.",
            )
            return
        output_dir = self.output_dir.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Medien-Setup", "Bitte zuerst einen lokalen Ausgabeordner eintragen.")
            return
        try:
            path = save_standard_image_workflow(
                output_dir,
                checkpoint,
                sampler_names=inventory.sampler_names,
                schedulers=inventory.schedulers,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Standard-Workflow", str(exc))
            return

        self._license_confirmed_workflow_path = str(path)
        self.workflow_path.setText(str(path))
        self.output.setPlainText(
            "[OK] Lokaler Standard-Bildworkflow erzeugt.\n"
            f"Checkpoint: {checkpoint}\n"
            f"Datei: {path}\n"
            "Lizenz-Prüfung: vom Benutzer ausdrücklich bestätigt; keine Lizenz wurde aus dem Dateinamen abgeleitet.\n"
            "Nodes: CheckpointLoaderSimple → CLIPTextEncode (+/-) → EmptyLatentImage → KSampler → VAEDecode → SaveImage\n\n"
            "Der Checkpoint wurde nicht heruntergeladen oder verändert."
        )
        self.inspect_workflow()

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
                "Wähle einen exportierten ComfyUI API-Workflow oder erzeuge oben automatisch einen Standard-Bildworkflow.",
            )
            return
        setup = inspect_for_auto_setup(
            path,
            checkpoint_license_confirmed=self._current_workflow_license_confirmed(),
        )
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
        if setup.profile.checkpoint_name:
            lines.append(f"Checkpoint: {setup.profile.checkpoint_name}")
            lines.append(
                "Checkpoint-Lizenz-Prüfung: "
                + (
                    "explizit bestätigt"
                    if setup.profile.checkpoint_license_confirmed
                    else "nicht im Profil bestätigt"
                )
            )
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
            checkpoint_license_confirmed=self._current_workflow_license_confirmed(),
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
        if setup.profile is not None and setup.profile.checkpoint_name:
            lines.append(f"Checkpoint: {setup.profile.checkpoint_name}")
            lines.append(
                "Lizenz-Prüfstatus im Profil: "
                + (
                    "explizite Benutzerbestätigung gespeichert"
                    if setup.profile.checkpoint_license_confirmed
                    else "nicht bestätigt"
                )
            )
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
