from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.media.capabilities import inspect_workflow_profile
from app.media.profile_manager import (
    load_current_catalog,
    replace_profile,
    save_managed_catalog,
)
from app.media.profiles import RoutingFocus, WorkflowCatalog, WorkflowProfile
from app.media.workflow_routing import FOCUS_TAGS, WorkflowPerformanceRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings

_FOCUS_LABELS = {
    "portrait": "Portrait",
    "full_body": "Ganzkörper",
    "detail": "Detail",
    "environment": "Umgebung",
    "character": "Character",
    "motion": "Motion",
}


class WorkflowProfileManagerWindow(QWidget):
    """Edit local routing metadata without overwriting source workflow catalogs."""

    settings_saved = Signal(object)

    def __init__(
        self,
        store: StateStore | None = None,
        settings: AppSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Local AI Companion — Workflow-Profile & Routing")
        self.resize(1280, 820)

        self.store = store or StateStore(make_session_factory())
        loaded = settings or self.store.load_settings(AppSettings.from_env())
        self.settings = loaded.model_copy(deep=True)
        self.performance = WorkflowPerformanceRepository(
            self.store,
            history_limit=self.settings.media_history_limit,
        )
        try:
            self.catalog = load_current_catalog(self.settings)
        except (OSError, ValueError) as exc:
            self.catalog = WorkflowCatalog()
            self._load_error = str(exc)
        else:
            self._load_error = ""
        self._initial_profiles = {
            profile.id: profile.model_copy(deep=True)
            for profile in self.catalog.profiles
        }
        self._loading_controls = False

        title = QLabel("Workflow-Profile & automatische Medien-Routen")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        intro = QLabel(
            "Hier steuerst du, welcher bereits konfigurierte lokale ComfyUI-Workflow für Portrait, Ganzkörper, "
            "Detail, Umgebung, Character-Continuity oder Motion bevorzugt wird. Änderungen werden in eine "
            "app-eigene Kopie des Profilkatalogs geschrieben; der bisherige importierte oder automatisch erzeugte "
            "Quellkatalog wird nicht überschrieben."
        )
        intro.setWordWrap(True)

        source = str(self.settings.profile_catalog_path or "kein Profilkatalog")
        self.source_label = QLabel(f"Aktiver Profilkatalog: {source}")
        self.source_label.setWordWrap(True)
        self.status = QLabel()
        self.status.setWordWrap(True)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Profil",
                "Aktiv",
                "Prio",
                "Medienarten",
                "Routing-Fokus",
                "Referenz",
                "Checkpoint",
                "Lizenz bestätigt",
                "Gelernte Scores",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.enabled = QCheckBox("Profil für automatische Auswahl aktiv")
        self.priority = QSpinBox()
        self.priority.setRange(-100, 100)
        self.priority.setToolTip("Fester Routing-Grundwert. Gelernte Bildbewertungen bleiben ein begrenztes weiches Zusatzsignal.")
        self.prefer_character = QCheckBox("Bei wiederkehrendem Character bevorzugen")
        self.quality = QComboBox()
        self.quality.addItem("Draft", "draft")
        self.quality.addItem("Balanced", "balanced")
        self.quality.addItem("High", "high")

        self.focus_checks: dict[str, QCheckBox] = {}
        focus_widget = QWidget()
        focus_layout = QHBoxLayout(focus_widget)
        focus_layout.setContentsMargins(0, 0, 0, 0)
        for focus in FOCUS_TAGS:
            box = QCheckBox(_FOCUS_LABELS.get(focus, focus))
            self.focus_checks[focus] = box
            focus_layout.addWidget(box)
        focus_layout.addStretch(1)

        self.capability = QLabel("–")
        self.capability.setWordWrap(True)
        self.learned = QLabel("–")
        self.learned.setWordWrap(True)
        self.provenance = QLabel("–")
        self.provenance.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Aktiv", self.enabled)
        form.addRow("Priorität", self.priority)
        form.addRow("Character", self.prefer_character)
        form.addRow("Render-Qualität", self.quality)
        form.addRow("Routing-Fokus", focus_widget)
        form.addRow("Technische Fähigkeiten", self.capability)
        form.addRow("Gelernte Feedback-Scores", self.learned)
        form.addRow("Checkpoint / Lizenz", self.provenance)

        self.save_button = QPushButton("Profiländerungen speichern & aktivieren")
        self.reset_button = QPushButton("Ausgangswerte dieses Profils")
        self.refresh_button = QPushButton("Feedback-Scores aktualisieren")
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)

        note = QLabel(
            "Die angezeigten Feedback-Scores stammen nur aus deinen expliziten lokalen Gut/Schlecht-Bewertungen. "
            "Die App leitet keine Bildqualität oder Lizenz aus Dateinamen ab. Aktivierung, Priorität und Routing-Tags "
            "können einen technisch ungültigen Workflow nicht lauffähig machen."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.source_label)
        layout.addWidget(self.table, 2)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.status)
        layout.addWidget(note)

        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.save_button.clicked.connect(self.save_selected)
        self.reset_button.clicked.connect(self.reset_selected)
        self.refresh_button.clicked.connect(self.refresh)
        for widget in [self.enabled, self.prefer_character]:
            widget.toggled.connect(self._controls_changed)
        self.priority.valueChanged.connect(self._controls_changed)
        self.quality.currentIndexChanged.connect(self._controls_changed)
        for box in self.focus_checks.values():
            box.toggled.connect(self._controls_changed)

        self.refresh()
        if self._load_error:
            self.status.setText(f"[FEHLER] Profilkatalog konnte nicht geladen werden: {self._load_error}")

    def _profile(self, profile_id: str) -> WorkflowProfile | None:
        return next((item for item in self.catalog.profiles if item.id == profile_id), None)

    def _selected_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _score_summary(self, profile: WorkflowProfile) -> str:
        parts: list[str] = []
        for focus in FOCUS_TAGS:
            performance = self.performance.performance(profile.id, [focus])
            if performance.samples:
                label = _FOCUS_LABELS.get(focus, focus)
                parts.append(f"{label} {performance.score:+d}/{performance.samples}")
        return " · ".join(parts) if parts else "noch kein Feedback"

    def refresh(self) -> None:
        selected = self._selected_id()
        self.table.setRowCount(len(self.catalog.profiles))
        for row, profile in enumerate(self.catalog.profiles):
            capability = inspect_workflow_profile(profile)
            focus = ", ".join(_FOCUS_LABELS.get(tag, tag) for tag in profile.routing_tags) or "–"
            checkpoint = profile.checkpoint_name or "–"
            values = [
                profile.label or profile.id,
                "ja" if profile.enabled else "nein",
                str(profile.priority),
                "/".join(profile.kinds),
                focus,
                "ja" if capability.reference_supported else "nein",
                checkpoint,
                "ja" if profile.checkpoint_license_confirmed else "nein",
                self._score_summary(profile),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, profile.id)
                self.table.setItem(row, column, item)
                if profile.id == selected:
                    self.table.setCurrentCell(row, 0)

        self.table.resizeColumnsToContents()
        if self.table.rowCount() and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self._selection_changed()

    def _selection_changed(self) -> None:
        profile = self._profile(self._selected_id())
        self._loading_controls = True
        try:
            enabled = profile is not None
            for widget in [self.enabled, self.priority, self.prefer_character, self.quality]:
                widget.setEnabled(enabled)
            for box in self.focus_checks.values():
                box.setEnabled(enabled)
            self.save_button.setEnabled(False)
            self.reset_button.setEnabled(enabled)
            if profile is None:
                self.capability.setText("–")
                self.learned.setText("–")
                self.provenance.setText("–")
                return

            self.enabled.setChecked(profile.enabled)
            self.priority.setValue(profile.priority)
            self.prefer_character.setChecked(profile.prefer_for_character)
            quality_index = self.quality.findData(profile.render_quality)
            self.quality.setCurrentIndex(max(0, quality_index))
            declared = set(profile.routing_tags)
            for focus, box in self.focus_checks.items():
                box.setChecked(focus in declared)

            capability = inspect_workflow_profile(profile)
            controls = ", ".join(capability.render_controls) or "Workflow-Defaults"
            kinds = "/".join(capability.runnable_kinds) or "keine"
            self.capability.setText(
                f"{'bereit' if capability.runnable else 'nicht bereit'} · {kinds} · "
                f"Referenz {'ja' if capability.reference_supported else 'nein'} · Render [{controls}]"
            )
            self.learned.setText(self._score_summary(profile))
            license_text = "explizit bestätigt" if profile.checkpoint_license_confirmed else "nicht bestätigt"
            self.provenance.setText(
                f"{profile.checkpoint_name or 'kein technischer Checkpoint-Name'} · Lizenz {license_text}"
            )
        finally:
            self._loading_controls = False

    def _controls_changed(self, *_args) -> None:
        if not self._loading_controls and self._profile(self._selected_id()) is not None:
            self.save_button.setEnabled(True)

    def _profile_from_controls(self, profile: WorkflowProfile) -> WorkflowProfile:
        routing_tags = [
            focus
            for focus, box in self.focus_checks.items()
            if box.isChecked()
        ]
        return profile.model_copy(
            update={
                "enabled": self.enabled.isChecked(),
                "priority": self.priority.value(),
                "prefer_for_character": self.prefer_character.isChecked(),
                "routing_tags": routing_tags,
                "render_quality": str(self.quality.currentData() or "balanced"),
            },
            deep=True,
        )

    def save_selected(self) -> None:
        profile = self._profile(self._selected_id())
        if profile is None:
            return
        updated_profile = self._profile_from_controls(profile)
        updated_catalog = replace_profile(self.catalog, updated_profile)
        try:
            target, updated_settings = save_managed_catalog(self.settings, updated_catalog)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Workflow-Profile", str(exc))
            return

        self.catalog = updated_catalog
        self.settings = updated_settings
        self.store.save_settings(updated_settings)
        self.source_label.setText(f"Aktiver Profilkatalog: {target}")
        self.status.setText(
            f"[OK] {updated_profile.label or updated_profile.id} gespeichert. "
            "Der app-eigene Profilkatalog ist aktiv; eine bereits laufende Companion-App übernimmt die neue Route nach einem Backend-Neuladen oder Neustart."
        )
        self.settings_saved.emit(updated_settings.model_copy(deep=True))
        self.refresh()

    def reset_selected(self) -> None:
        profile_id = self._selected_id()
        original = self._initial_profiles.get(profile_id)
        if original is None:
            return
        current = self._profile(profile_id)
        if current is None:
            return
        self.catalog = replace_profile(self.catalog, original)
        self.status.setText(
            "Ausgangswerte in die Bearbeitung übernommen. Zum Aktivieren noch speichern."
        )
        self.refresh()
        self.save_button.setEnabled(True)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Companion Workflow Profile Manager")
    window = WorkflowProfileManagerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
