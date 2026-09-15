from __future__ import annotations

import sys

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ai.model import OllamaClient
from app.ai.model_catalog import CatalogModel, pull_catalog_model, strict_open_source_models
from app.ai.model_compatibility import (
    AdultModelCompatibilityReport,
    AdultModelCompatibilityRepository,
    run_adult_model_compatibility,
)
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings

_FALLBACK_ALLOWED_STATUSES = {"compatible", "limited", "unclear"}


class DiscoveryWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        client = OllamaClient(model="discovery", base_url=self._base_url, timeout=15.0)
        try:
            self.completed.emit(client.list_models())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            client.close()


class PullWorker(QThread):
    progress = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, base_url: str, model_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model_name = model_name

    def run(self) -> None:
        try:
            pull_catalog_model(
                self._base_url,
                self._model_name,
                on_progress=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(self._model_name)


class CompatibilityWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str, model_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model_name = model_name

    def run(self) -> None:
        client = OllamaClient(model=self._model_name, base_url=self._base_url, timeout=90.0)
        try:
            self.completed.emit(run_adult_model_compatibility(client))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            client.close()


class ModelCatalogWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Open-Source-Modellkatalog — Local AI Companion")
        self.resize(1240, 760)

        self.store = StateStore(make_session_factory())
        self.settings = self.store.load_settings(AppSettings.from_env())
        self.compatibility_repository = AdultModelCompatibilityRepository(self.store)
        self.catalog = strict_open_source_models()
        self.installed: set[str] = set()

        self._discovery_worker: DiscoveryWorker | None = None
        self._pull_worker: PullWorker | None = None
        self._compatibility_worker: CompatibilityWorker | None = None

        title = QLabel("Geprüfter lokaler Open-Source-Modellkatalog")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        intro = QLabel(
            "Angezeigt werden nur kuratierte Ollama-Varianten mit dokumentierter Apache-2.0- oder MIT-Modelllizenz. "
            "Modelle werden niemals automatisch geladen oder umgestellt. Eine Kennzeichnung „(unzensiert)“ wird nur "
            "angezeigt, wenn die veröffentlichte Ollama-Modellbeschreibung diese Bezeichnung selbst verwendet."
        )
        intro.setWordWrap(True)

        self.endpoint = QLabel(f"Ollama: {self.settings.model_url}")
        self.active = QLabel(f"Aktives Chat-Modell: {self.settings.model_name}")
        self.fallback_summary = QLabel()
        self.fallback_summary.setWordWrap(True)
        self.status = QLabel("Lade lokale Modellliste …")
        self.status.setWordWrap(True)

        self.table = QTableWidget(len(self.catalog), 7)
        self.table.setHorizontalHeaderLabels(
            ["Status", "Modell", "Ollama-Name", "Größe", "Lizenz", "Schwerpunkt", "Adult/Kink-Test"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.refresh_button = QPushButton("Installationsstatus aktualisieren")
        self.install_button = QPushButton("Ausgewähltes Modell installieren")
        self.select_button = QPushButton("Als Chat-Modell auswählen")
        self.test_button = QPushButton("Adult-/Kink-Kompatibilität testen")
        self.fallback_button = QPushButton("Als Fallback zulassen")
        self.install_button.setEnabled(False)
        self.select_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.fallback_button.setEnabled(False)
        self.fallback_button.setToolTip(
            "Fallbacks müssen lokal installiert, mit dem Adult-/Kink-Test technisch lauffähig und Teil des strikten Open-Source-Katalogs sein."
        )

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.install_button)
        actions.addWidget(self.test_button)
        actions.addWidget(self.fallback_button)
        actions.addStretch(1)
        actions.addWidget(self.select_button)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.endpoint)
        layout.addWidget(self.active)
        layout.addWidget(self.fallback_summary)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        layout.addWidget(self.status)

        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.refresh_button.clicked.connect(self.refresh_installed)
        self.install_button.clicked.connect(self.install_selected)
        self.select_button.clicked.connect(self.select_selected)
        self.test_button.clicked.connect(self.test_selected)
        self.fallback_button.clicked.connect(self.toggle_fallback_selected)

        self._refresh_fallback_summary()
        self._render_table()
        self.refresh_installed()

    def _set_busy(self, busy: bool) -> None:
        self.table.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        if busy:
            self.install_button.setEnabled(False)
            self.select_button.setEnabled(False)
            self.test_button.setEnabled(False)
            self.fallback_button.setEnabled(False)
        else:
            self._selection_changed()

    def _selected_model(self) -> CatalogModel | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.catalog):
            return None
        return self.catalog[row]

    def _fallback_names(self) -> list[str]:
        return list(self.settings.model_fallbacks)

    def _is_configured_fallback(self, model_name: str) -> bool:
        folded = model_name.casefold()
        return any(name.casefold() == folded for name in self.settings.model_fallbacks)

    def _report_for(self, model_name: str) -> AdultModelCompatibilityReport | None:
        return self.compatibility_repository.report_for(model_name, self.settings.model_url)

    def _fallback_eligible(self, model: CatalogModel) -> bool:
        if model.ollama_model.casefold() not in self.installed:
            return False
        if model.ollama_model.casefold() == self.settings.model_name.casefold():
            return False
        report = self._report_for(model.ollama_model)
        return bool(
            report is not None
            and report.operational
            and report.status in _FALLBACK_ALLOWED_STATUSES
        )

    def _refresh_fallback_summary(self) -> None:
        fallbacks = self._fallback_names()
        if not self.settings.model_fallback_enabled or not fallbacks:
            self.fallback_summary.setText("Automatische Modell-Rückfallebene: aus")
            return
        self.fallback_summary.setText(
            "Automatische Modell-Rückfallebene: " + " → ".join(fallbacks)
        )

    def _render_table(self) -> None:
        active = self.settings.model_name.casefold()
        for row, model in enumerate(self.catalog):
            installed = model.ollama_model.casefold() in self.installed
            status_parts: list[str] = []
            if model.ollama_model.casefold() == active:
                status_parts.append("AKTIV")
            if self._is_configured_fallback(model.ollama_model):
                status_parts.append("FALLBACK")
            status_parts.append("installiert" if installed else "verfügbar")

            report = self._report_for(model.ollama_model)
            compatibility = "—"
            if report is not None:
                compatibility = f"{report.marker} · {report.score}/100"

            values = [
                " · ".join(status_parts),
                model.display_name,
                model.ollama_model,
                model.parameter_size,
                model.license_id,
                model.focus,
                compatibility,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, model.ollama_model)
                item.setToolTip(
                    f"Quelle: {model.source_url}\n{model.note}".rstrip()
                )
                self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(5, max(self.table.columnWidth(5), 260))
        self._refresh_fallback_summary()

    def _selection_changed(self) -> None:
        model = self._selected_model()
        if model is None:
            self.install_button.setEnabled(False)
            self.select_button.setEnabled(False)
            self.test_button.setEnabled(False)
            self.fallback_button.setEnabled(False)
            return
        installed = model.ollama_model.casefold() in self.installed
        self.install_button.setEnabled(not installed and self._pull_worker is None)
        self.select_button.setEnabled(installed)
        self.test_button.setEnabled(installed and self._compatibility_worker is None)

        configured = self._is_configured_fallback(model.ollama_model)
        self.fallback_button.setText(
            "Fallback entfernen" if configured else "Als Fallback zulassen"
        )
        self.fallback_button.setEnabled(configured or self._fallback_eligible(model))

    def refresh_installed(self) -> None:
        if self._discovery_worker is not None and self._discovery_worker.isRunning():
            return
        self._set_busy(True)
        self.status.setText("Prüfe lokal installierte Ollama-Modelle …")
        worker = DiscoveryWorker(self.settings.model_url, self)
        worker.completed.connect(self._discovery_completed)
        worker.failed.connect(self._discovery_failed)
        worker.finished.connect(self._discovery_finished)
        self._discovery_worker = worker
        worker.start()

    def _discovery_completed(self, models: list[str]) -> None:
        self.installed = {name.casefold() for name in models}
        self._render_table()
        count = sum(1 for item in self.catalog if item.ollama_model.casefold() in self.installed)
        self.status.setText(f"{count} Katalogmodell(e) sind lokal installiert. Insgesamt meldet Ollama {len(models)} Modell(e).")

    def _discovery_failed(self, error: str) -> None:
        self.status.setText(f"Ollama-Modellliste konnte nicht geladen werden: {error}")

    def _discovery_finished(self) -> None:
        worker = self._discovery_worker
        self._discovery_worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()

    def install_selected(self) -> None:
        model = self._selected_model()
        if model is None or model.ollama_model.casefold() in self.installed:
            return
        answer = QMessageBox.question(
            self,
            "Lokales Modell installieren",
            f"{model.display_name}\n{model.ollama_model}\nLizenz: {model.license_id}\n\n"
            "Das Modell wird jetzt ausdrücklich über deinen konfigurierten lokalen Ollama-Endpunkt heruntergeladen. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        self.status.setText(f"Lade {model.display_name} …")
        worker = PullWorker(self.settings.model_url, model.ollama_model, self)
        worker.progress.connect(lambda text: self.status.setText(f"{model.display_name}: {text}"))
        worker.completed.connect(self._pull_completed)
        worker.failed.connect(self._pull_failed)
        worker.finished.connect(self._pull_finished)
        self._pull_worker = worker
        worker.start()

    def _pull_completed(self, model_name: str) -> None:
        self.installed.add(model_name.casefold())
        self._render_table()
        self.status.setText(f"[OK] {model_name} wurde lokal installiert. Du kannst es jetzt testen oder auswählen.")

    def _pull_failed(self, error: str) -> None:
        self.status.setText(f"[FEHLER] Modellinstallation fehlgeschlagen: {error}")

    def _pull_finished(self) -> None:
        worker = self._pull_worker
        self._pull_worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()

    def select_selected(self) -> None:
        model = self._selected_model()
        if model is None or model.ollama_model.casefold() not in self.installed:
            return
        remaining_fallbacks = [
            name
            for name in self.settings.model_fallbacks
            if name.casefold() != model.ollama_model.casefold()
        ]
        updated = self.settings.model_copy(
            update={
                "model_name": model.ollama_model,
                "model_fallbacks": remaining_fallbacks,
                "model_fallback_enabled": bool(remaining_fallbacks),
            },
            deep=True,
        )
        self.store.save_settings(updated)
        self.settings = updated
        self.active.setText(f"Aktives Chat-Modell: {model.ollama_model}")
        self._render_table()
        self.status.setText(
            f"{model.display_name} wurde als Chat-Modell gespeichert. Eine bereits laufende Companion-App übernimmt die Änderung beim nächsten Start."
        )

    def toggle_fallback_selected(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        current = self._fallback_names()
        if self._is_configured_fallback(model.ollama_model):
            updated_fallbacks = [
                name for name in current if name.casefold() != model.ollama_model.casefold()
            ]
            action = "entfernt"
        else:
            if not self._fallback_eligible(model):
                QMessageBox.information(
                    self,
                    "Fallback nicht verfügbar",
                    "Das Modell muss installiert sein und zuerst den lokalen Adult-/Kink-Kompatibilitätstest technisch erfolgreich abschließen.",
                )
                return
            updated_fallbacks = [*current, model.ollama_model]
            action = "hinzugefügt"

        updated = self.settings.model_copy(
            update={
                "model_fallbacks": updated_fallbacks,
                "model_fallback_enabled": bool(updated_fallbacks),
            },
            deep=True,
        )
        self.store.save_settings(updated)
        self.settings = updated
        self._render_table()
        self._selection_changed()
        self.status.setText(
            f"{model.display_name} wurde der lokalen Fallback-Kette {action}. Die Companion-App übernimmt die Kette beim nächsten Start."
        )

    def test_selected(self) -> None:
        model = self._selected_model()
        if model is None or model.ollama_model.casefold() not in self.installed:
            return
        self._set_busy(True)
        self.status.setText(
            f"Teste {model.display_name} lokal mit technischer Inferenz und nicht-grafischen Adult-/Kink-Proben …"
        )
        worker = CompatibilityWorker(self.settings.model_url, model.ollama_model, self)
        worker.completed.connect(self._test_completed)
        worker.failed.connect(self._test_failed)
        worker.finished.connect(self._test_finished)
        self._compatibility_worker = worker
        worker.start()

    def _test_completed(self, report: AdultModelCompatibilityReport) -> None:
        self.compatibility_repository.save_report(report)
        self._render_table()
        self._selection_changed()
        self.status.setText(
            f"[{report.marker}] {report.model_name}: {report.score}/100 · {report.summary}"
        )

    def _test_failed(self, error: str) -> None:
        self.status.setText(f"[FEHLER] Kompatibilitätstest fehlgeschlagen: {error}")

    def _test_finished(self) -> None:
        worker = self._compatibility_worker
        self._compatibility_worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Companion Model Catalog")
    window = ModelCatalogWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
