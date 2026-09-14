from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.memory.core_memory import CoreMemoryRepository
from app.memory.store import StateStore


class MemoryLab(QWidget):
    """Review deliberate Core Memory and reversible adaptive observations."""

    memory_changed = Signal()

    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.core_memory = CoreMemoryRepository(store)
        self._observations: dict[int, dict[str, object]] = {}
        self._core_ids: list[str] = []

        intro = QLabel(
            "Core Memory wird bewusst von dir festgelegt und von der KI nicht selbst umgeschrieben. "
            "Darunter bleiben automatisch gelernte Beobachtungen separat sichtbar und reversibel."
        )
        intro.setWordWrap(True)

        self.core_group = QGroupBox("📌 Core Memory — bewusst fest angeheftet")
        self.core_list = QListWidget()
        self.core_title = QLineEdit()
        self.core_title.setMaxLength(80)
        self.core_title.setPlaceholderText("z. B. Kommunikationsstil")
        self.core_content = QPlainTextEdit()
        self.core_content.setMaximumHeight(95)
        self.core_content.setPlaceholderText(
            "Was die Companion-Persona dauerhaft als bewussten Kontext berücksichtigen soll …"
        )
        self.core_priority = QSpinBox()
        self.core_priority.setRange(0, 100)
        self.core_priority.setValue(50)
        self.core_priority.setToolTip("Höhere Priorität wird im Prompt weiter oben einsortiert.")
        self.core_active = QCheckBox("Aktiv")
        self.core_active.setChecked(True)

        core_form = QFormLayout()
        core_form.addRow("Titel", self.core_title)
        core_form.addRow("Inhalt", self.core_content)
        core_form.addRow("Priorität", self.core_priority)
        core_form.addRow("Status", self.core_active)

        self.core_new_button = QPushButton("Neu")
        self.core_save_button = QPushButton("Speichern")
        self.core_delete_button = QPushButton("Löschen")
        core_buttons = QHBoxLayout()
        core_buttons.addWidget(self.core_new_button)
        core_buttons.addWidget(self.core_delete_button)
        core_buttons.addStretch(1)
        core_buttons.addWidget(self.core_save_button)

        core_layout = QVBoxLayout(self.core_group)
        core_layout.addWidget(self.core_list)
        core_layout.addLayout(core_form)
        core_layout.addLayout(core_buttons)

        self.adaptive_group = QGroupBox("Adaptive Beobachtungen — automatisch gelernt, fallibel")
        self.list_widget = QListWidget()
        self.details = QLabel("Noch kein adaptives Memory ausgewählt")
        self.details.setWordWrap(True)
        self.toggle_button = QPushButton("Aktiv/Inaktiv umschalten")
        self.promote_button = QPushButton("📌 Als Core Memory übernehmen")
        self.promote_button.setToolTip(
            "Kopiert die gelernte Beobachtung in den bewusst bearbeitbaren Core-Memory-Bereich."
        )
        self.refresh_button = QPushButton("Memory aktualisieren")

        adaptive_buttons = QHBoxLayout()
        adaptive_buttons.addWidget(self.toggle_button)
        adaptive_buttons.addWidget(self.promote_button)
        adaptive_buttons.addStretch(1)
        adaptive_buttons.addWidget(self.refresh_button)

        adaptive_layout = QVBoxLayout(self.adaptive_group)
        adaptive_layout.addWidget(self.list_widget)
        adaptive_layout.addWidget(self.details)
        adaptive_layout.addLayout(adaptive_buttons)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.core_group)
        splitter.addWidget(self.adaptive_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(splitter, 1)

        self.core_list.currentItemChanged.connect(self._core_selection_changed)
        self.core_new_button.clicked.connect(self._new_core_memory)
        self.core_save_button.clicked.connect(self._save_core_memory)
        self.core_delete_button.clicked.connect(self._delete_core_memory)
        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.toggle_button.clicked.connect(self.toggle_selected)
        self.promote_button.clicked.connect(self.promote_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self._refresh_core()
        self._refresh_adaptive()

    def _refresh_core(self, select_id: str | None = None) -> None:
        selected_id = select_id or self._selected_core_id()
        self.core_list.clear()
        self._core_ids.clear()

        for memory in self.core_memory.list():
            self._core_ids.append(memory.id)
            marker = "📌" if memory.active else "○"
            item = QListWidgetItem(
                f"{marker}  P{memory.priority:03d}  {memory.title}: {memory.content}"
            )
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            self.core_list.addItem(item)
            if memory.id == selected_id:
                self.core_list.setCurrentItem(item)

        if self.core_list.count() and self.core_list.currentItem() is None:
            self.core_list.setCurrentRow(0)
        elif not self.core_list.count():
            self._new_core_memory()

    def _refresh_adaptive(self) -> None:
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
            self.details.setText("Noch keine adaptiven Langzeit-Beobachtungen gespeichert.")
            self.toggle_button.setEnabled(False)
            self.promote_button.setEnabled(False)

    def _selected_core_id(self) -> str | None:
        item = self.core_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _core_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        memory_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
        memory = self.core_memory.get(memory_id)
        if memory is None:
            return
        self.core_title.setText(memory.title)
        self.core_content.setPlainText(memory.content)
        self.core_priority.setValue(memory.priority)
        self.core_active.setChecked(memory.active)
        self.core_delete_button.setEnabled(True)

    def _new_core_memory(self) -> None:
        self.core_list.clearSelection()
        self.core_list.setCurrentItem(None)
        self.core_title.clear()
        self.core_content.clear()
        self.core_priority.setValue(50)
        self.core_active.setChecked(True)
        self.core_delete_button.setEnabled(False)
        self.core_title.setFocus()

    def _save_core_memory(self) -> None:
        title = self.core_title.text().strip()
        content = self.core_content.toPlainText().strip()
        if not title or not content:
            QMessageBox.warning(
                self,
                "Core Memory",
                "Bitte Titel und Inhalt für das Core Memory eintragen.",
            )
            return
        try:
            saved = self.core_memory.upsert(
                memory_id=self._selected_core_id(),
                title=title,
                content=content,
                priority=self.core_priority.value(),
                active=self.core_active.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Core Memory", str(exc))
            return
        self._refresh_core(select_id=saved.id)
        self.memory_changed.emit()

    def _delete_core_memory(self) -> None:
        memory_id = self._selected_core_id()
        if memory_id is None:
            return
        memory = self.core_memory.get(memory_id)
        if memory is None:
            return
        answer = QMessageBox.question(
            self,
            "Core Memory löschen",
            f"Core Memory „{memory.title}“ wirklich löschen?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.core_memory.delete(memory_id)
        self._refresh_core()
        self.memory_changed.emit()

    def _selected_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self.toggle_button.setEnabled(False)
            self.promote_button.setEnabled(False)
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
        self.toggle_button.setEnabled(True)
        self.promote_button.setEnabled(True)

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
        self._refresh_adaptive()
        self.memory_changed.emit()

    def promote_selected(self) -> None:
        observation_id = self._selected_id()
        if observation_id is None:
            return
        observation = self._observations.get(observation_id)
        if observation is None:
            return
        category = str(observation.get("category") or "Beobachtung").replace("_", " ").strip()
        summary = str(observation.get("summary") or "").strip()
        if not summary:
            return
        saved = self.core_memory.upsert(
            memory_id=None,
            title=f"Bestätigt: {category}"[:80],
            content=summary,
            priority=60,
            active=True,
        )
        self._refresh_core(select_id=saved.id)
        self.memory_changed.emit()
