from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.media.coverage import VisualCoverageRepository
from app.media_suitability_gui import MediaSuitabilityWindow
from app.memory.store import StateStore
from app.ui.media_preview import MediaPreview
from app.ui.visual_coverage import VisualCoverageWidget

_IMAGE_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class MediaHistoryWidget(QWidget):
    """Local history, feedback, render trace, character reference, and coverage UI."""

    feedback_changed = Signal()
    reference_changed = Signal()

    def __init__(
        self,
        store: StateStore,
        *,
        limit: int = 200,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.limit = limit
        self._events: dict[int, dict[str, object]] = {}
        self._reference_ids: dict[str, int] = {}
        self._suitability_window: MediaSuitabilityWindow | None = None
        self.coverage_repository = VisualCoverageRepository(store)

        self.list_widget = QListWidget()
        self.preview = MediaPreview()
        self.meta = QLabel("Noch kein Medium ausgewählt")
        self.meta.setWordWrap(True)
        self.feedback_note = QLabel(
            "Bildbewertungen lernen Stilpräferenzen und die Eignung lokaler Workflows für Portrait, Ganzkörper, Detail, Umgebung und Character-Continuity. "
            "Die Medienhistorie zeigt Gestaltung, Routing und Render-Berechnung, damit nachvollziehbar bleibt, was an ComfyUI übergeben wurde."
        )
        self.feedback_note.setWordWrap(True)

        splitter = QSplitter()
        splitter.addWidget(self.list_widget)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.preview, 1)
        right_layout.addWidget(self.meta)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self.positive = QPushButton("👍 Bild gefällt mir")
        self.negative = QPushButton("👎 Bild gefällt mir nicht")
        self.clear_feedback = QPushButton("Bewertung löschen")
        self.pin_reference = QPushButton("📌 Als Charakter-Referenz")
        self.pin_reference.setToolTip(
            "Dieses lokale Bild als feste visuelle Referenz für denselben Continuity-Key verwenden"
        )
        self.clear_reference = QPushButton("Referenz lösen")
        self.pin_reference.setEnabled(False)
        self.clear_reference.setEnabled(False)
        self.suitability_lab = QPushButton("🧪 Medien-Eignungslabor")
        self.suitability_lab.setToolTip(
            "Vier kleine lokale Testbilder rendern und Workflows für Portrait, Ganzkörper, Detail und Umgebung bewerten"
        )
        self.refresh_button = QPushButton("Historie aktualisieren")

        row = QHBoxLayout()
        row.addWidget(self.negative)
        row.addWidget(self.positive)
        row.addWidget(self.clear_feedback)
        row.addWidget(self.pin_reference)
        row.addWidget(self.clear_reference)
        row.addStretch(1)
        row.addWidget(self.suitability_lab)
        row.addWidget(self.refresh_button)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.addWidget(splitter, 1)
        history_layout.addWidget(self.feedback_note)
        history_layout.addLayout(row)

        self.coverage_widget = VisualCoverageWidget(
            self.coverage_repository,
            self._active_conversation_id(),
        )
        tabs = QTabWidget()
        tabs.addTab(history_page, "Historie & Render")
        tabs.addTab(self.coverage_widget, "Visual Coverage")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.positive.clicked.connect(lambda: self._rate("positive"))
        self.negative.clicked.connect(lambda: self._rate("negative"))
        self.clear_feedback.clicked.connect(lambda: self._rate(None))
        self.pin_reference.clicked.connect(self._pin_reference)
        self.clear_reference.clicked.connect(self._clear_reference)
        self.suitability_lab.clicked.connect(self._open_suitability_lab)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def _active_conversation_id(self) -> str:
        value = self.store._load_app_state("active_conversation_id")  # noqa: SLF001
        return value.strip() if value and value.strip() else "main"

    def set_limit(self, limit: int) -> None:
        self.limit = max(10, limit)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self._selected_id()
        self.list_widget.clear()
        self._events.clear()
        self._reference_ids.clear()

        events = self.store.list_media_events(limit=self.limit)
        continuity_keys = {
            str(event.get("continuity_key"))
            for event in events
            if event.get("continuity_key")
        }
        for key in continuity_keys:
            profile = self.store.load_character_profile(key)
            if profile.reference_media_id is not None:
                self._reference_ids[key] = profile.reference_media_id

        for event in events:
            media_id = int(event["id"])
            self._events[media_id] = event
            created_at = event["created_at"]
            stamp = created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            intent = event.get("intent") or {}
            mood = str(intent.get("mood", "")) if isinstance(intent, dict) else ""
            theme = str(intent.get("theme", "")) if isinstance(intent, dict) else ""
            feedback = event.get("feedback")
            continuity_key = str(event.get("continuity_key") or "")
            is_reference = self._reference_ids.get(continuity_key) == media_id
            if is_reference:
                marker = "📌"
            elif feedback == "positive":
                marker = "👍"
            elif feedback == "negative":
                marker = "👎"
            else:
                marker = "·"
            title = " · ".join(part for part in (mood, theme) if part) or Path(str(event["path"])).name
            item = QListWidgetItem(f"{marker}  {stamp}  {title}")
            item.setData(Qt.ItemDataRole.UserRole, media_id)
            self.list_widget.addItem(item)
            if media_id == selected_id:
                self.list_widget.setCurrentItem(item)

        if self.list_widget.count() and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)
        elif not self.list_widget.count():
            self.pin_reference.setEnabled(False)
            self.clear_reference.setEnabled(False)

        self.coverage_widget.set_conversation(self._active_conversation_id())

    def _selected_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    @staticmethod
    def _render_summary(intent: dict[str, object]) -> tuple[str, str]:
        render = intent.get("render_plan")
        if not isinstance(render, dict):
            return "Render-Berechnung: ältere Historie / nicht vorhanden", ""

        width = render.get("width", "?")
        height = render.get("height", "?")
        aspect = render.get("aspect_ratio", "?")
        steps = render.get("steps", "?")
        cfg = render.get("cfg", "?")
        denoise = render.get("denoise", "?")
        quality = render.get("quality", "?")
        work = render.get("estimated_work_units", "?")
        kind = render.get("kind", "image")
        motion = ""
        if kind != "image":
            motion = (
                f" · {render.get('frames', '?')} Frames @ {render.get('fps', '?')} fps"
                f" (~{render.get('duration_seconds', '?')} s)"
            )

        hardware_tier = str(render.get("hardware_tier") or "unknown")
        hardware_device = str(render.get("hardware_device") or "unknown")
        hardware_vram = render.get("hardware_vram_free_gb")
        hardware = f" · Hardware {hardware_tier}: {hardware_device}"
        if isinstance(hardware_vram, (int, float)):
            hardware += f" · freie VRAM ~{float(hardware_vram):.1f} GB"

        target = (
            f"Render-Ziel: {width}×{height} · {aspect} · {quality} · {steps} Steps · "
            f"CFG {cfg} · Denoise {denoise}{motion} · Work ~{work}{hardware}"
        )

        applied = intent.get("render_parameters_applied")
        if isinstance(applied, list) and applied:
            applied_text = "ComfyUI gesetzt: " + ", ".join(str(item) for item in applied)
        else:
            applied_text = (
                "ComfyUI gesetzt: keine automatisch erkannten numerischen Eingänge; "
                "der Workflow behält für diese Werte seine eigenen Defaults."
            )
        return target, applied_text

    @staticmethod
    def _routing_summary(intent: dict[str, object]) -> list[str]:
        lines: list[str] = []
        checkpoint = str(intent.get("workflow_checkpoint") or "").strip()
        if checkpoint:
            lines.append(f"Checkpoint: {checkpoint}")
        focus = intent.get("workflow_focus_tags")
        if isinstance(focus, list) and focus:
            lines.append("Routing-Fokus: " + ", ".join(str(item) for item in focus))
        score = intent.get("workflow_feedback_score_before")
        samples = intent.get("workflow_feedback_samples_before")
        if isinstance(score, (int, float)):
            sample_text = f" · {samples} bewertete Render(s)" if isinstance(samples, int) else ""
            lines.append(f"Gelernter Workflow-Score vor Render: {score:+g}{sample_text}")
        probe = str(intent.get("suitability_probe") or "").strip()
        if probe:
            lines.append(f"Eignungstest: {probe}")
        return lines

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self.pin_reference.setEnabled(False)
            self.clear_reference.setEnabled(False)
            return
        media_id = int(current.data(Qt.ItemDataRole.UserRole))
        event = self._events.get(media_id)
        if event is None:
            return
        intent = event.get("intent") or {}
        description = ""
        workflow_profile = "standard"
        render_summary = ""
        applied_summary = ""
        direction_summary = ""
        routing_lines: list[str] = []
        if isinstance(intent, dict):
            description = " · ".join(
                str(intent.get(key, "")).strip()
                for key in ("mood", "theme", "visual_style")
                if str(intent.get(key, "")).strip()
            )
            workflow_profile = str(intent.get("workflow_profile") or "standard")
            direction_parts = [
                str(intent.get("framing") or "").strip(),
                str(intent.get("camera_angle") or "").strip(),
                str(intent.get("lighting") or "").strip(),
                str(intent.get("composition") or "").strip(),
            ]
            direction_summary = " · ".join(item for item in direction_parts if item)
            render_summary, applied_summary = self._render_summary(intent)
            routing_lines = self._routing_summary(intent)
        self.preview.show_media(str(event["path"]), description=description)
        continuity_key = str(event.get("continuity_key") or "")
        is_reference = self._reference_ids.get(continuity_key) == media_id
        meta_lines = [
            f"ID #{media_id} · Seed {event['seed']} · Workflow {workflow_profile}",
            f"Continuity {continuity_key or 'aus'} · Bewertung {event.get('feedback') or 'keine'} · Referenz {'fest' if is_reference else 'nein'}",
        ]
        meta_lines.extend(routing_lines)
        if direction_summary:
            meta_lines.append(f"Gestaltung: {direction_summary}")
        if render_summary:
            meta_lines.append(render_summary)
        if applied_summary:
            meta_lines.append(applied_summary)
        self.meta.setText("\n".join(meta_lines))

        path = Path(str(event.get("path") or "")).expanduser()
        usable_image = (
            bool(continuity_key)
            and path.suffix.lower() in _IMAGE_REFERENCE_SUFFIXES
            and path.exists()
            and path.is_file()
        )
        self.pin_reference.setEnabled(usable_image and not is_reference)
        self.clear_reference.setEnabled(bool(continuity_key) and is_reference)

    def _rate(self, feedback: str | None) -> None:
        media_id = self._selected_id()
        if media_id is None:
            return
        self.store.set_media_feedback(media_id, feedback)
        self.refresh()
        self.feedback_changed.emit()

    def _open_suitability_lab(self) -> None:
        window = self._suitability_window
        if window is not None and window.isVisible():
            window.raise_()
            window.activateWindow()
            return
        window = MediaSuitabilityWindow(store=self.store, parent=None)
        window.media_created.connect(self.refresh)
        window.feedback_changed.connect(self._suitability_feedback_changed)
        window.destroyed.connect(self._suitability_closed)
        self._suitability_window = window
        window.show()

    def _suitability_feedback_changed(self) -> None:
        self.refresh()
        self.feedback_changed.emit()

    def _suitability_closed(self, _object=None) -> None:
        self._suitability_window = None

    def _pin_reference(self) -> None:
        media_id = self._selected_id()
        if media_id is None:
            return
        event = self._events.get(media_id)
        if event is None:
            return
        continuity_key = str(event.get("continuity_key") or "").strip()
        path = Path(str(event.get("path") or "")).expanduser()
        if (
            not continuity_key
            or path.suffix.lower() not in _IMAGE_REFERENCE_SUFFIXES
            or not path.exists()
            or not path.is_file()
        ):
            return
        profile = self.store.load_character_profile(continuity_key)
        profile.set_reference(media_id, str(path))
        self.store.save_character_profile(profile)
        self.refresh()
        self.reference_changed.emit()

    def _clear_reference(self) -> None:
        media_id = self._selected_id()
        if media_id is None:
            return
        event = self._events.get(media_id)
        if event is None:
            return
        continuity_key = str(event.get("continuity_key") or "").strip()
        if not continuity_key:
            return
        profile = self.store.load_character_profile(continuity_key)
        if profile.reference_media_id != media_id:
            return
        profile.clear_reference()
        self.store.save_character_profile(profile)
        self.refresh()
        self.reference_changed.emit()
