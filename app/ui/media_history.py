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
    QVBoxLayout,
    QWidget,
)

from app.memory.store import StateStore
from app.ui.media_preview import MediaPreview

_IMAGE_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class MediaHistoryWidget(QWidget):
    """Local history, feedback, workflow trace, and character-reference UI."""

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

        self.list_widget = QListWidget()
        self.preview = MediaPreview()
        self.meta = QLabel("Noch kein Medium ausgewählt")
        self.meta.setWordWrap(True)
        self.feedback_note = QLabel(
            "Bildbewertungen lernen Stilpräferenzen. Ein festes Referenzbild kann zusätzlich die visuelle Identität derselben Figur stabilisieren."
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
        self.refresh_button = QPushButton("Historie aktualisieren")

        row = QHBoxLayout()
        row.addWidget(self.negative)
        row.addWidget(self.positive)
        row.addWidget(self.clear_feedback)
        row.addWidget(self.pin_reference)
        row.addWidget(self.clear_reference)
        row.addStretch(1)
        row.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.feedback_note)
        layout.addLayout(row)

        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.positive.clicked.connect(lambda: self._rate("positive"))
        self.negative.clicked.connect(lambda: self._rate("negative"))
        self.clear_feedback.clicked.connect(lambda: self._rate(None))
        self.pin_reference.clicked.connect(self._pin_reference)
        self.clear_reference.clicked.connect(self._clear_reference)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

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

    def _selected_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

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
        if isinstance(intent, dict):
            description = " · ".join(
                str(intent.get(key, "")).strip()
                for key in ("mood", "theme", "visual_style")
                if str(intent.get(key, "")).strip()
            )
            workflow_profile = str(intent.get("workflow_profile") or "standard")
        self.preview.show_media(str(event["path"]), description=description)
        continuity_key = str(event.get("continuity_key") or "")
        is_reference = self._reference_ids.get(continuity_key) == media_id
        self.meta.setText(
            f"ID #{media_id} · Seed {event['seed']} · "
            f"Workflow {workflow_profile} · "
            f"Continuity {continuity_key or 'aus'} · "
            f"Bewertung {event.get('feedback') or 'keine'} · "
            f"Referenz {'fest' if is_reference else 'nein'}"
        )

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
