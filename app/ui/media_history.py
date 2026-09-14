from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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


class MediaHistoryWidget(QWidget):
    """Local history and feedback UI for generated media."""

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

        self.list_widget = QListWidget()
        self.preview = MediaPreview()
        self.meta = QLabel("Noch kein Medium ausgewählt")
        self.meta.setWordWrap(True)

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
        self.refresh_button = QPushButton("Historie aktualisieren")

        row = QHBoxLayout()
        row.addWidget(self.negative)
        row.addWidget(self.positive)
        row.addWidget(self.clear_feedback)
        row.addStretch(1)
        row.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(row)

        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.positive.clicked.connect(lambda: self._rate("positive"))
        self.negative.clicked.connect(lambda: self._rate("negative"))
        self.clear_feedback.clicked.connect(lambda: self._rate(None))
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def set_limit(self, limit: int) -> None:
        self.limit = max(10, limit)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self._selected_id()
        self.list_widget.clear()
        self._events.clear()

        for event in self.store.list_media_events(limit=self.limit):
            media_id = int(event["id"])
            self._events[media_id] = event
            created_at = event["created_at"]
            stamp = created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            intent = event.get("intent") or {}
            mood = str(intent.get("mood", "")) if isinstance(intent, dict) else ""
            theme = str(intent.get("theme", "")) if isinstance(intent, dict) else ""
            feedback = event.get("feedback")
            marker = "👍" if feedback == "positive" else "👎" if feedback == "negative" else "·"
            title = " · ".join(part for part in (mood, theme) if part) or Path(str(event["path"])).name
            item = QListWidgetItem(f"{marker}  {stamp}  {title}")
            item.setData(Qt.ItemDataRole.UserRole, media_id)
            self.list_widget.addItem(item)
            if media_id == selected_id:
                self.list_widget.setCurrentItem(item)

        if self.list_widget.count() and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)

    def _selected_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        media_id = int(current.data(Qt.ItemDataRole.UserRole))
        event = self._events.get(media_id)
        if event is None:
            return
        intent = event.get("intent") or {}
        description = ""
        if isinstance(intent, dict):
            description = " · ".join(
                str(intent.get(key, "")).strip()
                for key in ("mood", "theme", "visual_style")
                if str(intent.get(key, "")).strip()
            )
        self.preview.show_media(str(event["path"]), description=description)
        self.meta.setText(
            f"ID #{media_id} · Seed {event['seed']} · "
            f"Continuity {event.get('continuity_key') or 'aus'} · "
            f"Bewertung {event.get('feedback') or 'keine'}"
        )

    def _rate(self, feedback: str | None) -> None:
        media_id = self._selected_id()
        if media_id is None:
            return
        self.store.set_media_feedback(media_id, feedback)
        self.refresh()
