from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
from app.media.character_continuity_lab import (
    CharacterContinuityResult,
    run_character_continuity_suite,
)
from app.media.continuity import CharacterProfile
from app.media.profiles import WorkflowProfile, load_workflow_catalog
from app.memory.store import StateStore
from app.settings import AppSettings
from app.ui.media_preview import MediaPreview


class CharacterContinuityWorker(QThread):
    progress = Signal(int, int, str)
    result_ready = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        profile: WorkflowProfile,
        character: CharacterProfile,
        store: StateStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)
        self._profile = profile.model_copy(deep=True)
        self._character = character.model_copy(deep=True)
        self._store = store

    def run(self) -> None:
        try:
            results = run_character_continuity_suite(
                self._settings,
                self._profile,
                self._character,
                self._store,
                on_progress=self.progress.emit,
                on_result=self.result_ready.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(results)


class CharacterContinuityLab(QDialog):
    feedback_changed = Signal()
    media_created = Signal()

    def __init__(
        self,
        store: StateStore,
        *,
        continuity_key: str = "persona-main",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = store.load_settings(AppSettings.from_env())
        self.character = store.load_character_profile(continuity_key)
        self.profiles: list[WorkflowProfile] = []
        self._worker: CharacterContinuityWorker | None = None
        self._results: list[CharacterContinuityResult] = []

        self.setWindowTitle("Local AI Companion — Character-Continuity-Labor")
        self.resize(1060, 820)

        title = QLabel("Character-Continuity-Labor")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        intro = QLabel(
            "Dieses Labor prüft einen lokalen Referenz-Workflow mit derselben festgelegten Character-Referenz "
            "über mehrere Bildausschnitte hinweg. Es gibt bewusst keine automatische Pixelbewertung: Du markierst "
            "die Ergebnisse als gut oder schlecht, und diese Rückmeldung fließt in die bestehende lokale Workflow-Auswahl ein."
        )
        intro.setWordWrap(True)

        self.reference_label = QLabel()
        self.reference_label.setWordWrap(True)
        self.reference_preview = MediaPreview()
        self.reference_preview.setVisible(False)

        self.profile_combo = QComboBox()
        self.run_button = QPushButton("3 Continuity-Bilder lokal rendern")
        self.run_button.setEnabled(False)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Referenz-Workflow"))
        profile_row.addWidget(self.profile_combo, 1)
        profile_row.addWidget(self.run_button)

        self.status = QLabel("Lade Character-Referenz und lokale Workflows …")
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

        self.good_button = QPushButton("👍 Identität gut erhalten")
        self.bad_button = QPushButton("👎 Identität driftet")
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
            "Die Kalibrierung bleibt vollständig lokal und verwendet nur die bereits festgelegte Referenz, "
            "den vorhandenen ComfyUI-Workflow und den gespeicherten Character-Seed. Es wird nichts heruntergeladen. "
            "Die Testmotive sind nicht-grafisch und zeigen nur klar erwachsene Figuren."
        )
        note.setWordWrap(True)

        close_button = QPushButton("Schließen")
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.reference_label)
        layout.addWidget(self.reference_preview, 1)
        layout.addLayout(profile_row)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 2)
        layout.addWidget(self.preview, 3)
        layout.addLayout(feedback_row)
        layout.addWidget(note)
        layout.addLayout(close_row)

        self.run_button.clicked.connect(self.run_suite)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.good_button.clicked.connect(lambda: self._set_feedback("positive"))
        self.bad_button.clicked.connect(lambda: self._set_feedback("negative"))
        self.clear_button.clicked.connect(lambda: self._set_feedback(None))
        close_button.clicked.connect(self.close)

        self._load_state()

    def _load_state(self) -> None:
        reference = Path(str(self.character.reference_media_path or "")).expanduser()
        if self.character.reference_media_path and reference.exists() and reference.is_file():
            self.reference_label.setText(
                f"Character: {self.character.key} · feste Referenz #{self.character.reference_media_id or '?'} · {reference}"
            )
            self.reference_preview.show_media(
                str(reference),
                description="Feste Character-Referenz",
            )
            self.reference_preview.setVisible(True)
        else:
            self.reference_label.setText(
                "Keine nutzbare feste Character-Referenz vorhanden. Pinne zuerst in Medien → Historie & Render ein passendes Bild als Charakter-Referenz."
            )
            self.reference_preview.setVisible(False)

        catalog_path = self.settings.profile_catalog_path
        if catalog_path is None:
            self.status.setText("Kein Workflow-Profilkatalog konfiguriert.")
            return
        try:
            catalog = load_workflow_catalog(catalog_path)
        except (OSError, ValueError) as exc:
            self.status.setText(f"Workflow-Profilkatalog konnte nicht geladen werden: {exc}")
            return

        self.profiles = []
        for profile in catalog.profiles:
            if "image" not in profile.kinds:
                continue
            capability = inspect_workflow_profile(profile)
            if capability.runnable and capability.reference_supported:
                self.profiles.append(profile)

        self.profile_combo.clear()
        for profile in self.profiles:
            checkpoint = f" · {profile.checkpoint_name}" if profile.checkpoint_name else ""
            self.profile_combo.addItem(f"{profile.label or profile.id}{checkpoint}", profile.id)

        ready_reference = bool(
            self.character.reference_media_path
            and reference.exists()
            and reference.is_file()
        )
        self.run_button.setEnabled(ready_reference and bool(self.profiles))
        if ready_reference and self.profiles:
            self.status.setText(
                f"{len(self.profiles)} referenzfähige(s) lokale(s) Bild-Workflow-Profil(e) gefunden."
            )
        elif ready_reference:
            self.status.setText(
                "Die Referenz ist vorhanden, aber kein lauffähiges Workflow-Profil besitzt einen validierten Referenzbild-Eingang."
            )

    def _selected_profile(self) -> WorkflowProfile | None:
        index = self.profile_combo.currentIndex()
        if index < 0 or index >= len(self.profiles):
            return None
        return self.profiles[index]

    def _set_busy(self, busy: bool) -> None:
        self.profile_combo.setEnabled(not busy)
        reference = Path(str(self.character.reference_media_path or "")).expanduser()
        self.run_button.setEnabled(
            not busy and bool(self.profiles) and reference.exists() and reference.is_file()
        )
        valid = 0 <= self.table.currentRow() < len(self._results)
        self.good_button.setEnabled(valid and not busy)
        self.bad_button.setEnabled(valid and not busy)
        self.clear_button.setEnabled(valid and not busy)

    def run_suite(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        profile = self._selected_profile()
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "Character-Continuity testen",
            "Es werden drei kleine lokale Vergleichsbilder mit derselben festen Character-Referenz berechnet. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._results = []
        self.table.setRowCount(0)
        self.preview.setVisible(False)
        self._set_busy(True)
        self.status.setText(f"Starte Continuity-Test mit {profile.label or profile.id} …")
        worker = CharacterContinuityWorker(
            self.settings,
            profile,
            self.character,
            self.store,
            self,
        )
        worker.progress.connect(self._progress)
        worker.result_ready.connect(self._result_ready)
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        self._worker = worker
        worker.start()

    def _progress(self, index: int, total: int, label: str) -> None:
        self.status.setText(f"Continuity-Render {index}/{total}: {label} …")

    def _result_ready(self, result: CharacterContinuityResult) -> None:
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
            description=f"Character-Continuity: {result.probe.label}",
        )
        self.preview.setVisible(True)
        self.media_created.emit()

    def _completed(self, results: list[CharacterContinuityResult]) -> None:
        self.character = self.store.load_character_profile(self.character.key)
        self.status.setText(
            f"{len(results)} Continuity-Bilder fertig. Bewerte pro Zeile, ob die Character-Identität gut erhalten wurde."
        )

    def _failed(self, error: str) -> None:
        self.status.setText(f"[FEHLER] Character-Continuity-Test abgebrochen: {error}")

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
            description=f"Character-Continuity: {result.probe.label}",
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
            QMessageBox.warning(self, "Continuity-Feedback", str(exc))
            return
        label = {
            "positive": "IDENTITÄT GUT",
            "negative": "IDENTITÄT DRIFTET",
            None: "noch nicht bewertet",
        }[feedback]
        item = self.table.item(row, 2)
        if item is not None:
            item.setText(label)
        self.status.setText(
            f"{result.probe.label}: {label}. Dieses Feedback beeinflusst die lokale Workflow-Auswahl für Character-Szenen."
        )
        self.feedback_changed.emit()
