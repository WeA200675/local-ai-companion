from __future__ import annotations

import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.media.capabilities import inspect_workflow_profile
from app.media.profiles import WorkflowProfile, load_workflow_catalog
from app.media.suitability import SuitabilityProbeResult, run_suitability_suite
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings
from app.ui.media_preview import MediaPreview


class SuitabilityWorker(QThread):
    progress = Signal(int, int, str)
    result_ready = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        profile: WorkflowProfile,
        store: StateStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)
        self._profile = profile.model_copy(deep=True)
        self._store = store

    def run(self) -> None:
        try:
            results = run_suitability_suite(
                self._settings,
                self._profile,
                self._store,
                on_progress=self.progress.emit,
                on_result=self.result_ready.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(results)


class MediaSuitabilityWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local AI Companion — Medien-Eignungslabor")
        self.resize(1040, 780)

        self.store = StateStore(make_session_factory())
        self.settings = self.store.load_settings(AppSettings.from_env())
        self.profiles: list[WorkflowProfile] = []
        self._worker: SuitabilityWorker | None = None
        self._results: list[SuitabilityProbeResult] = []

        title = QLabel("Lokales Checkpoint-/Workflow-Eignungslabor")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        intro = QLabel(
            "Das Labor rendert vier kleine lokale Vergleichsbilder: Portrait, Ganzkörper, Materialdetail und Umgebung. "
            "Es bewertet die Pixel nicht automatisch. Du markierst die Ergebnisse mit Gut/Schlecht; diese expliziten "
            "Bewertungen fließen danach als weiches Signal in die automatische Workflow-Auswahl ein."
        )
        intro.setWordWrap(True)

        self.profile_combo = QComboBox()
        self.run_button = QPushButton("4 Eignungsbilder lokal rendern")
        self.run_button.setEnabled(False)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Workflow-Profil"))
        profile_row.addWidget(self.profile_combo, 1)
        profile_row.addWidget(self.run_button)

        self.status = QLabel("Lade lokale Workflow-Profile …")
        self.status.setWordWrap(True)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Test", "Datei", "Bewertung", "Media-ID"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.preview = MediaPreview()
        self.preview.setVisible(False)

        self.good_button = QPushButton("👍 Gut für diesen Bildtyp")
        self.bad_button = QPushButton("👎 Schlecht für diesen Bildtyp")
        self.clear_button = QPushButton("Bewertung löschen")
        self.good_button.setEnabled(False)
        self.bad_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        feedback_row = QHBoxLayout()
        feedback_row.addWidget(self.bad_button)
        feedback_row.addWidget(self.clear_button)
        feedback_row.addWidget(self.good_button)
        feedback_row.addStretch(1)

        note = QLabel(
            "Die Tests sind absichtlich nicht-grafisch und dienen nur Komposition/Renderqualität. "
            "Es wird nichts heruntergeladen, kein Cloud-Dienst verwendet und keine Checkpoint-Lizenz aus dem Dateinamen abgeleitet."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addLayout(profile_row)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 2)
        layout.addWidget(self.preview, 3)
        layout.addLayout(feedback_row)
        layout.addWidget(note)

        self.run_button.clicked.connect(self.run_suite)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.good_button.clicked.connect(lambda: self._set_feedback("positive"))
        self.bad_button.clicked.connect(lambda: self._set_feedback("negative"))
        self.clear_button.clicked.connect(lambda: self._set_feedback(None))

        self._load_profiles()

    def _load_profiles(self) -> None:
        catalog_path = self.settings.profile_catalog_path
        if catalog_path is None:
            self.status.setText(
                "Kein Workflow-Profilkatalog konfiguriert. Richte zuerst ComfyUI über media_setup_windows.cmd ein."
            )
            return
        try:
            catalog = load_workflow_catalog(catalog_path)
        except (OSError, ValueError) as exc:
            self.status.setText(f"Workflow-Profilkatalog konnte nicht geladen werden: {exc}")
            return

        self.profiles = [
            profile
            for profile in catalog.profiles
            if "image" in profile.kinds and inspect_workflow_profile(profile).runnable
        ]
        self.profile_combo.clear()
        for profile in self.profiles:
            checkpoint = f" · {profile.checkpoint_name}" if profile.checkpoint_name else ""
            self.profile_combo.addItem(f"{profile.label or profile.id}{checkpoint}", profile.id)
        self.run_button.setEnabled(bool(self.profiles))
        if self.profiles:
            self.status.setText(
                f"{len(self.profiles)} lokal lauffähige(s) Bild-Workflow-Profil(e) gefunden."
            )
        else:
            self.status.setText("Kein lauffähiges Bild-Workflow-Profil gefunden.")

    def _selected_profile(self) -> WorkflowProfile | None:
        index = self.profile_combo.currentIndex()
        if index < 0 or index >= len(self.profiles):
            return None
        return self.profiles[index]

    def _set_busy(self, busy: bool) -> None:
        self.profile_combo.setEnabled(not busy)
        self.run_button.setEnabled(not busy and bool(self.profiles))
        self.good_button.setEnabled(False if busy else self.table.currentRow() >= 0)
        self.bad_button.setEnabled(False if busy else self.table.currentRow() >= 0)
        self.clear_button.setEnabled(False if busy else self.table.currentRow() >= 0)

    def run_suite(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        profile = self._selected_profile()
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "Lokalen Eignungstest starten",
            "Es werden vier kleine Bilder nacheinander mit dem ausgewählten lokalen Workflow berechnet. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._results = []
        self.table.setRowCount(0)
        self.preview.setVisible(False)
        self._set_busy(True)
        self.status.setText(f"Starte lokale Eignungsbilder mit {profile.label or profile.id} …")
        worker = SuitabilityWorker(self.settings, profile, self.store, self)
        worker.progress.connect(self._progress)
        worker.result_ready.connect(self._result_ready)
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        self._worker = worker
        worker.start()

    def _progress(self, index: int, total: int, label: str) -> None:
        self.status.setText(f"Render {index}/{total}: {label} …")

    def _result_ready(self, result: SuitabilityProbeResult) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._results.append(result)
        self.table.setItem(row, 0, QTableWidgetItem(result.probe.label))
        self.table.setItem(row, 1, QTableWidgetItem(str(result.generated.path)))
        self.table.setItem(row, 2, QTableWidgetItem("noch nicht bewertet"))
        self.table.setItem(row, 3, QTableWidgetItem(str(result.media_id)))
        self.table.selectRow(row)
        self.preview.show_media(
            str(result.generated.path),
            description=f"Eignungstest: {result.probe.label}",
        )
        self.preview.setVisible(True)

    def _completed(self, results: list[SuitabilityProbeResult]) -> None:
        self.status.setText(
            f"{len(results)} Eignungsbilder fertig. Wähle jede Zeile aus und bewerte sie mit Gut oder Schlecht."
        )

    def _failed(self, error: str) -> None:
        self.status.setText(f"[FEHLER] Eignungstest abgebrochen: {error}")

    def _finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._set_busy(False)
        self._selection_changed()
        if worker is not None:
            worker.deleteLater()

    def _selection_changed(self) -> None:
        row = self.table.currentRow()
        valid = 0 <= row < len(self._results)
        busy = self._worker is not None and self._worker.isRunning()
        self.good_button.setEnabled(valid and not busy)
        self.bad_button.setEnabled(valid and not busy)
        self.clear_button.setEnabled(valid and not busy)
        if not valid:
            return
        result = self._results[row]
        self.preview.show_media(
            str(result.generated.path),
            description=f"Eignungstest: {result.probe.label}",
        )
        self.preview.setVisible(True)

    def _set_feedback(self, feedback: str | None) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._results):
            return
        result = self._results[row]
        try:
            self.store.set_media_feedback(result.media_id, feedback)
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Medienfeedback", str(exc))
            return
        label = {
            "positive": "GUT",
            "negative": "SCHLECHT",
            None: "noch nicht bewertet",
        }[feedback]
        item = self.table.item(row, 2)
        if item is not None:
            item.setText(label)
        self.status.setText(
            f"{result.probe.label}: {label}. Die automatische Workflow-Auswahl nutzt dieses Feedback lokal als weiches Signal."
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Companion Media Suitability Lab")
    window = MediaSuitabilityWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
