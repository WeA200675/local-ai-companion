from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ai.model import OllamaClient
from app.ai.model_compatibility import (
    AdultModelCompatibilityReport,
    AdultModelCompatibilityRepository,
    run_adult_model_compatibility,
)
from app.diagnostics import DiagnosticResult, run_diagnostics
from app.memory.store import StateStore
from app.settings import AppSettings
from app.setup_flow import candidate_settings, core_setup_status


class ModelDiscoveryWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url.strip()

    def run(self) -> None:
        client = OllamaClient(model="discovery", base_url=self._base_url, timeout=10.0)
        try:
            self.completed.emit(client.list_models())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            client.close()


class CoreDiagnosticWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Media is intentionally disabled for this first-run core check. A broken
        # optional ComfyUI setup must not hide whether text inference works.
        self._settings = settings.model_copy(update={"media_enabled": False}, deep=True)

    def run(self) -> None:
        try:
            self.completed.emit(run_diagnostics(self._settings))
        except Exception as exc:
            self.failed.emit(str(exc))


class CompatibilityWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)

    def run(self) -> None:
        client = OllamaClient(
            model=self._settings.model_name,
            base_url=self._settings.model_url,
            timeout=90.0,
        )
        try:
            self.completed.emit(run_adult_model_compatibility(client))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            client.close()


class FirstRunSetupDialog(QDialog):
    """One-time, local-only setup for Ollama/model readiness.

    The dialog does not install software or download models. It proves that the
    selected already-local model can perform a real mini inference and offers the
    app's non-graphic Adult-/Kink compatibility probe before the desktop app starts.
    """

    def __init__(
        self,
        store: StateStore,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings.model_copy(deep=True)
        self.compatibility_repository = AdultModelCompatibilityRepository(store)
        self._discovery_worker: ModelDiscoveryWorker | None = None
        self._diagnostic_worker: CoreDiagnosticWorker | None = None
        self._compatibility_worker: CompatibilityWorker | None = None
        self._last_diagnostics: list[DiagnosticResult] = []
        self._technical_ready = False

        self.setWindowTitle("Ersteinrichtung — Local AI Companion")
        self.setModal(True)
        self.resize(760, 650)

        title = QLabel("Lokale Ersteinrichtung")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        intro = QLabel(
            "Dieser Assistent prüft ausschließlich lokale Komponenten. Er installiert nichts, "
            "lädt keine Modelle herunter und sendet weder Chatverlauf noch Persona- oder Memory-Daten ins Netz."
        )
        intro.setWordWrap(True)

        self.model_url = QLineEdit(settings.model_url)
        self.model_url.setPlaceholderText("http://127.0.0.1:11434")
        self.model_name = QComboBox()
        self.model_name.setEditable(True)
        self.model_name.addItem(settings.model_name)
        self.model_name.setCurrentText(settings.model_name)
        self.load_models_button = QPushButton("Installierte Modelle laden")

        endpoint_row = QHBoxLayout()
        endpoint_row.addWidget(QLabel("Ollama/API-URL"))
        endpoint_row.addWidget(self.model_url, 1)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Lokales Modell"))
        model_row.addWidget(self.model_name, 1)
        model_row.addWidget(self.load_models_button)

        self.core_status = QLabel("Noch kein echter lokaler Inferenztest ausgeführt.")
        self.core_status.setWordWrap(True)
        self.diagnostics_output = QPlainTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setMaximumHeight(180)
        self.diagnostics_output.setPlaceholderText(
            "Hier erscheinen Ollama-, Modell- und Mini-Inferenz-Ergebnisse."
        )
        self.test_button = QPushButton("Ollama & echte Mini-Inferenz testen")

        self.compatibility_status = QLabel(
            "Adult-/Kink-Kompatibilität noch nicht geprüft. Dieser Test ist lokal und absichtlich nicht-grafisch."
        )
        self.compatibility_status.setWordWrap(True)
        self.compatibility_output = QPlainTextEdit()
        self.compatibility_output.setReadOnly(True)
        self.compatibility_output.setMaximumHeight(150)
        self.compatibility_button = QPushButton("Adult-/Kink-Modelltest")
        self.compatibility_button.setEnabled(False)

        media_note = QLabel(
            "Lokale Bilder/Motion sind optional und blockieren den Text-Companion nicht. "
            "Nach dieser Ersteinrichtung kann ComfyUI separat über den Medien-Setup-Assistenten "
            "(`media_setup_windows.cmd`) automatisch geprüft und verbunden werden."
        )
        media_note.setWordWrap(True)

        self.status = QLabel("Bereit zur lokalen Prüfung.")
        self.status.setWordWrap(True)

        self.later_button = QPushButton("Später")
        self.skip_button = QPushButton("Nicht mehr automatisch anzeigen")
        self.finish_button = QPushButton("Einrichtung abschließen")
        self.finish_button.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(self.later_button)
        actions.addWidget(self.skip_button)
        actions.addStretch(1)
        actions.addWidget(self.finish_button)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addSpacing(8)
        layout.addLayout(endpoint_row)
        layout.addLayout(model_row)
        layout.addSpacing(8)
        layout.addWidget(self.test_button)
        layout.addWidget(self.core_status)
        layout.addWidget(self.diagnostics_output)
        layout.addSpacing(8)
        layout.addWidget(self.compatibility_button)
        layout.addWidget(self.compatibility_status)
        layout.addWidget(self.compatibility_output)
        layout.addSpacing(8)
        layout.addWidget(media_note)
        layout.addStretch(1)
        layout.addWidget(self.status)
        layout.addLayout(actions)

        self.model_url.textChanged.connect(self._selection_changed)
        self.model_name.currentTextChanged.connect(self._selection_changed)
        self.load_models_button.clicked.connect(self.discover_models)
        self.test_button.clicked.connect(self.run_core_diagnostics)
        self.compatibility_button.clicked.connect(self.run_compatibility)
        self.finish_button.clicked.connect(self.finish_setup)
        self.skip_button.clicked.connect(self.skip_future_setup)
        self.later_button.clicked.connect(self.reject)

        QTimer.singleShot(150, self.discover_models)

    def _candidate(self, *, completed: bool | None = None) -> AppSettings:
        return candidate_settings(
            self.settings,
            model_name=self.model_name.currentText(),
            model_url=self.model_url.text(),
            completed=completed,
        )

    def _selection_changed(self) -> None:
        self._technical_ready = False
        self._last_diagnostics = []
        self.finish_button.setEnabled(False)
        self.compatibility_button.setEnabled(False)
        self.core_status.setText("Auswahl geändert — bitte die echte Mini-Inferenz erneut testen.")

    def _set_busy(self, busy: bool) -> None:
        self.model_url.setEnabled(not busy)
        self.model_name.setEnabled(not busy)
        self.load_models_button.setEnabled(not busy)
        self.test_button.setEnabled(not busy)
        self.later_button.setEnabled(not busy)
        self.skip_button.setEnabled(not busy)
        self.finish_button.setEnabled(not busy and self._technical_ready)
        self.compatibility_button.setEnabled(not busy and self._technical_ready)

    def discover_models(self) -> None:
        if self._discovery_worker is not None and self._discovery_worker.isRunning():
            return
        base_url = self.model_url.text().strip()
        if not base_url:
            QMessageBox.warning(self, "Ollama", "Bitte zuerst eine lokale Ollama/API-URL eintragen.")
            return
        self._set_busy(True)
        self.status.setText("Prüfe lokalen Ollama-Endpunkt und lade die installierte Modellliste …")
        worker = ModelDiscoveryWorker(base_url, self)
        worker.completed.connect(self._models_discovered)
        worker.failed.connect(self._discovery_failed)
        worker.finished.connect(self._discovery_finished)
        self._discovery_worker = worker
        worker.start()

    def _models_discovered(self, models: list[str]) -> None:
        current = self.model_name.currentText().strip()
        self.model_name.blockSignals(True)
        self.model_name.clear()
        for model in models:
            self.model_name.addItem(model)
        if current and current in models:
            self.model_name.setCurrentText(current)
        elif models:
            self.model_name.setCurrentIndex(0)
        elif current:
            self.model_name.setCurrentText(current)
        self.model_name.blockSignals(False)
        self._selection_changed()
        if models:
            self.status.setText(
                f"Ollama antwortet. {len(models)} installierte(s) Modell(e) gefunden; bitte gewünschtes Modell prüfen."
            )
        else:
            self.status.setText(
                "Ollama antwortet, meldet aber keine installierten Modelle. Prüfe `ollama list`."
            )

    def _discovery_failed(self, error: str) -> None:
        self.status.setText(
            "Ollama ist unter der eingetragenen URL nicht erreichbar. Starte Ollama und versuche es erneut."
        )
        self.diagnostics_output.setPlainText(error)

    def _discovery_finished(self) -> None:
        worker = self._discovery_worker
        self._discovery_worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()

    def run_core_diagnostics(self) -> None:
        if self._diagnostic_worker is not None and self._diagnostic_worker.isRunning():
            return
        try:
            settings = self._candidate()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return
        self._set_busy(True)
        self.core_status.setText("Prüfe Installation und starte eine echte lokale Mini-Inferenz …")
        self.diagnostics_output.setPlainText(
            "Die erste Antwort kann bei einem kalten Modell länger dauern. Es werden keine Gesprächsdaten verwendet."
        )
        worker = CoreDiagnosticWorker(settings, self)
        worker.completed.connect(self._diagnostics_completed)
        worker.failed.connect(self._diagnostics_failed)
        worker.finished.connect(self._diagnostics_finished)
        self._diagnostic_worker = worker
        worker.start()

    def _diagnostics_completed(self, results: list[DiagnosticResult]) -> None:
        self._last_diagnostics = list(results)
        core = core_setup_status(results)
        self._technical_ready = core.ready
        self.core_status.setText(core.summary)
        relevant = [
            item for item in results if item.name in {"Sprachmodell", "Modell-Inferenz"}
        ]
        self.diagnostics_output.setPlainText(
            "\n".join(f"[{item.marker}] {item.name}: {item.detail}" for item in relevant)
        )
        if core.ready:
            self.status.setText(
                "Der lokale Text-Backendpfad ist technisch bereit. Als Nächstes kann die Adult-/Kink-Eignung geprüft werden."
            )
        else:
            self.status.setText(
                "Die lokale Modell-Inferenz ist noch nicht bereit. Behebe den angezeigten Ollama-/Modellfehler und teste erneut."
            )

    def _diagnostics_failed(self, error: str) -> None:
        self._technical_ready = False
        self.core_status.setText("Der lokale Setup-Check konnte nicht abgeschlossen werden.")
        self.diagnostics_output.setPlainText(error)

    def _diagnostics_finished(self) -> None:
        worker = self._diagnostic_worker
        self._diagnostic_worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()

    def run_compatibility(self) -> None:
        if not self._technical_ready:
            return
        if self._compatibility_worker is not None and self._compatibility_worker.isRunning():
            return
        try:
            settings = self._candidate()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return
        self._set_busy(True)
        self.compatibility_status.setText(
            "Prüfe lokal erotischen und kink-orientierten, nicht-grafischen Erwachsenenton …"
        )
        self.compatibility_output.clear()
        worker = CompatibilityWorker(settings, self)
        worker.completed.connect(self._compatibility_completed)
        worker.failed.connect(self._compatibility_failed)
        worker.finished.connect(self._compatibility_finished)
        self._compatibility_worker = worker
        worker.start()

    def _compatibility_completed(self, report: AdultModelCompatibilityReport) -> None:
        self.compatibility_repository.save_report(report)
        self.compatibility_status.setText(
            f"[{report.marker}] {report.model_name}: {report.score}/100 · {report.summary}"
        )
        self.compatibility_output.setPlainText(
            "\n".join(
                f"[{probe.status.upper()}] {probe.name}: {probe.detail}"
                for probe in report.probes
            )
        )
        self.status.setText(
            "Kompatibilitätstest gespeichert. Er ist eine lokale Heuristik; das Verhalten kann je nach Gespräch variieren."
        )

    def _compatibility_failed(self, error: str) -> None:
        self.compatibility_status.setText("Adult-/Kink-Kompatibilitätstest fehlgeschlagen.")
        self.compatibility_output.setPlainText(error)

    def _compatibility_finished(self) -> None:
        worker = self._compatibility_worker
        self._compatibility_worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()

    def finish_setup(self) -> None:
        if not self._technical_ready:
            QMessageBox.information(
                self,
                "Ersteinrichtung",
                "Bitte zuerst eine erfolgreiche echte lokale Mini-Inferenz durchführen.",
            )
            return
        try:
            settings = self._candidate(completed=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return
        self.store.save_settings(settings)
        self.settings = settings.model_copy(deep=True)
        self.accept()

    def skip_future_setup(self) -> None:
        answer = QMessageBox.question(
            self,
            "Ersteinrichtung nicht mehr automatisch anzeigen",
            "Der Assistent wird künftig beim Windows-Start nicht mehr automatisch geöffnet. "
            "Die bisherigen Einstellungen bleiben unverändert. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        settings = self.settings.model_copy(update={"setup_completed": True}, deep=True)
        self.store.save_settings(settings)
        self.settings = settings
        self.accept()
