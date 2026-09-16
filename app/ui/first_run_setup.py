from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
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
from app.ai.model_recovery import (
    ModelRecoveryReport,
    recover_first_working_model,
    recovery_candidates,
    recommended_install_commands,
)
from app.ai.model_compatibility import (
    AdultModelCompatibilityReport,
    AdultModelCompatibilityRepository,
    run_adult_model_compatibility,
)
from app.diagnostics import DiagnosticResult, run_diagnostics
from app.memory.store import StateStore
from app.settings import AppSettings
from app.setup_flow import FirstRunSetupRepository, candidate_settings, core_setup_status


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


class ModelRecoveryWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        installed_models: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)
        self._installed_models = list(installed_models)

    def run(self) -> None:
        try:
            self.completed.emit(
                recover_first_working_model(self._settings, self._installed_models)
            )
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
        self.setup_repository = FirstRunSetupRepository(store)
        self.compatibility_repository = AdultModelCompatibilityRepository(store)
        self._discovery_worker: ModelDiscoveryWorker | None = None
        self._diagnostic_worker: CoreDiagnosticWorker | None = None
        self._recovery_worker: ModelRecoveryWorker | None = None
        self._compatibility_worker: CompatibilityWorker | None = None
        self._last_diagnostics: list[DiagnosticResult] = []
        self._installed_models: list[str] = []
        self._pending_recovered_model: str | None = None
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
        self.recovery_button = QPushButton("Funktionierendes Ersatzmodell suchen")
        self.recovery_button.setEnabled(False)
        self.copy_diagnostics_button = QPushButton("Diagnose kopieren")
        self.copy_diagnostics_button.setEnabled(False)
        self.copy_install_button = QPushButton("Kleine OSS-Modelle als Befehle kopieren")

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
        recovery_actions = QHBoxLayout()
        recovery_actions.addWidget(self.recovery_button)
        recovery_actions.addWidget(self.copy_diagnostics_button)
        recovery_actions.addWidget(self.copy_install_button)
        layout.addLayout(recovery_actions)
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
        self.recovery_button.clicked.connect(self.run_model_recovery)
        self.copy_diagnostics_button.clicked.connect(self.copy_diagnostics)
        self.copy_install_button.clicked.connect(self.copy_install_commands)
        self.compatibility_button.clicked.connect(self.run_compatibility)
        self.finish_button.clicked.connect(self.finish_setup)
        self.skip_button.clicked.connect(self.skip_future_setup)
        self.later_button.clicked.connect(self.reject)

        QTimer.singleShot(150, self.discover_models)

    def _candidate(self) -> AppSettings:
        return candidate_settings(
            self.settings,
            model_name=self.model_name.currentText(),
            model_url=self.model_url.text(),
        )

    def _selection_changed(self) -> None:
        self._technical_ready = False
        self._last_diagnostics = []
        self.finish_button.setEnabled(False)
        self.compatibility_button.setEnabled(False)
        self.recovery_button.setEnabled(False)
        self.copy_diagnostics_button.setEnabled(False)
        self.core_status.setText("Auswahl geändert — bitte die echte Mini-Inferenz erneut testen.")

    def _set_busy(self, busy: bool) -> None:
        self.model_url.setEnabled(not busy)
        self.model_name.setEnabled(not busy)
        self.load_models_button.setEnabled(not busy)
        self.test_button.setEnabled(not busy)
        alternatives = recovery_candidates(
            self._installed_models,
            self.model_name.currentText(),
        )
        self.recovery_button.setEnabled(
            not busy and not self._technical_ready and bool(alternatives)
        )
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
        self._installed_models = list(models)
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
        self.copy_diagnostics_button.setEnabled(bool(relevant))
        if core.ready:
            self.status.setText(
                "Der lokale Text-Backendpfad ist technisch bereit. Als Nächstes kann die Adult-/Kink-Eignung geprüft werden."
            )
        else:
            alternatives = recovery_candidates(
                self._installed_models,
                self.model_name.currentText(),
            )
            if alternatives:
                self.status.setText(
                    "Die gewählte Inferenz ist fehlgeschlagen. Du kannst jetzt bereits installierte, "
                    "kleinere Open-Source-Modelle automatisch und nacheinander testen."
                )
            else:
                self.status.setText(
                    "Die lokale Modell-Inferenz ist noch nicht bereit. Es wurde kein anderes installiertes "
                    "Modell aus dem strikten Open-Source-Katalog gefunden. Die App lädt nichts automatisch herunter."
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

    def copy_diagnostics(self) -> None:
        text = self.diagnostics_output.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("Diagnose wurde in die Zwischenablage kopiert.")

    def copy_install_commands(self) -> None:
        commands = recommended_install_commands(self._installed_models)
        if not commands:
            QMessageBox.information(
                self,
                "Kleine OSS-Modelle",
                "Alle kleinen Empfehlungen aus dem strikten Open-Source-Katalog sind bereits installiert.",
            )
            return
        QApplication.clipboard().setText("\n".join(commands))
        QMessageBox.information(
            self,
            "Befehle kopiert",
            "Die folgenden optionalen Befehle wurden kopiert. Die App führt sie nicht aus und lädt nichts selbst herunter:\n\n"
            + "\n".join(commands),
        )

    def run_model_recovery(self) -> None:
        if self._recovery_worker is not None and self._recovery_worker.isRunning():
            return
        try:
            settings = self._candidate()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return
        alternatives = recovery_candidates(self._installed_models, settings.model_name)
        if not alternatives:
            QMessageBox.information(
                self,
                "Kein Ersatzmodell",
                "Kein anderes installiertes Modell aus dem strikten Open-Source-Katalog ist verfügbar. "
                "Es wird nichts automatisch heruntergeladen.",
            )
            return
        self._pending_recovered_model = None
        self._set_busy(True)
        self.core_status.setText(
            "Teste installierte Open-Source-Ersatzmodelle, beginnend mit dem kleinsten …"
        )
        self.diagnostics_output.setPlainText(
            "Getestet werden ausschließlich bereits installierte Modelle. "
            "Gespeicherte Einstellungen bleiben bis zum erfolgreichen Abschluss unverändert."
        )
        worker = ModelRecoveryWorker(settings, self._installed_models, self)
        worker.completed.connect(self._recovery_completed)
        worker.failed.connect(self._recovery_failed)
        worker.finished.connect(self._recovery_finished)
        self._recovery_worker = worker
        worker.start()

    def _recovery_completed(self, report: ModelRecoveryReport) -> None:
        lines = [
            f"[{'OK' if attempt.ready else 'FEHLER'}] {attempt.model_name}: {attempt.detail}"
            for attempt in report.attempts
        ]
        self.diagnostics_output.setPlainText("\n".join(lines))
        if report.selected_model is None:
            self.core_status.setText(
                "Keines der installierten Open-Source-Ersatzmodelle konnte die echte Mini-Inferenz abschließen."
            )
            self.status.setText(
                "Die gespeicherten Einstellungen wurden nicht verändert. Prüfe Ollama, RAM/VRAM und Treiber."
            )
            return
        self._pending_recovered_model = report.selected_model
        self.model_name.blockSignals(True)
        self.model_name.setCurrentText(report.selected_model)
        self.model_name.blockSignals(False)
        self.core_status.setText(
            f"{report.selected_model} hat den Wiederherstellungstest bestanden; die vollständige Diagnose folgt."
        )
        self.status.setText(
            "Ein lokales Ersatzmodell funktioniert. Es wird jetzt mit dem normalen Setup-Test bestätigt."
        )

    def _recovery_failed(self, error: str) -> None:
        self._pending_recovered_model = None
        self.core_status.setText("Die automatische Modellwiederherstellung ist fehlgeschlagen.")
        self.diagnostics_output.setPlainText(error)

    def _recovery_finished(self) -> None:
        worker = self._recovery_worker
        self._recovery_worker = None
        recovered = self._pending_recovered_model
        self._pending_recovered_model = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()
        if recovered:
            QTimer.singleShot(0, self.run_core_diagnostics)

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
            settings = self._candidate()
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Einstellungen", str(exc))
            return
        self.store.save_settings(settings)
        self.setup_repository.mark_completed()
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
        self.setup_repository.mark_completed()
        self.accept()
