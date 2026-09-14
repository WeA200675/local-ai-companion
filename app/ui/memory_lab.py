from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.memory.store import StateStore


class MemoryLab(QWidget):
    """Review and reversibly enable/disable local adaptive memories."""

    memory_changed = Signal()

    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._observations: dict[int, dict[str, object]] = {}

        intro = QLabel(
            "Die KI kann kompakte Langzeit-Beobachtungen lokal speichern. "
            "Jeder Eintrag bleibt sichtbar und kann deaktiviert oder wieder aktiviert werden."
        )
        intro.setWordWrap(True)

        self.list_widget = QListWidget()
        self.details = QLabel("Noch kein Memory ausgewählt")
        self.details.setWordWrap(True)

        self.toggle_button = QPushButton("Aktiv/Inaktiv umschalten")
        self.refresh_button = QPushButton("Memory aktualisieren")

        buttons = QHBoxLayout()
        buttons.addWidget(self.toggle_button)
        buttons.addStretch(1)
        buttons.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.details)
        layout.addLayout(buttons)

        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.toggle_button.clicked.connect(self.toggle_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self._selected_id()
        self.list_widget.clear()
        self._observations.clear()

        for observation in self.store.list_memory_observations(limit=250):
            observation_id = int(observation["id"])
            self._observations[observation_id] = observation
            active = bool(observation["active"])
            marker = "●" if active else "○"
            confidence = round(float(observation["confidence"]) * 100)
            category = str(observation["category"]).replace("_", " ")
            item = QListWidgetItem(
                f"{marker}  {confidence:>3}%  {category}: {observation['summary']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, observation_id)
            self.list_widget.addItem(item)
            if observation_id == selected_id:
                self.list_widget.setCurrentItem(item)

        if self.list_widget.count() and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)
        elif not self.list_widget.count():
            self.details.setText("Noch keine Langzeit-Beobachtungen gespeichert.")

    def _selected_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        observation_id = int(current.data(Qt.ItemDataRole.UserRole))
        observation = self._observations.get(observation_id)
        if observation is None:
            return
        state = "aktiv" if observation["active"] else "inaktiv"
        updated_at = observation["updated_at"]
        stamp = updated_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.details.setText(
            f"ID #{observation_id} · {state} · Kategorie {observation['category']} · "
            f"Konfidenz {float(observation['confidence']):.2f} · "
            f"{observation['source_count']} Beobachtung(en) · zuletzt {stamp}"
        )

    def toggle_selected(self) -> None:
        observation_id = self._selected_id()
        if observation_id is None:
            return
        observation = self._observations.get(observation_id)
        if observation is None:
            return
        self.store.set_memory_observation_active(
            observation_id, not bool(observation["active"])
        )
        self.refresh()
        self.memory_changed.emit()
