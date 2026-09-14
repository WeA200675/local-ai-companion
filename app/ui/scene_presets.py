from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ai.scene_presets import ScenePreset, ScenePresetRepository
from app.memory.store import StateStore


class ScenePresetsWidget(QWidget):
    """User-controlled temporary scene context for chat and local media planning."""

    active_scene_changed = Signal(object)

    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = ScenePresetRepository(store)
        self._items: dict[str, ScenePreset] = {}

        intro = QLabel(
            "Szenen sind temporäre Kontexte für Ort, Atmosphäre und Stil. Sie verändern weder "
            "die gelernte Persona noch Core Memory und können jederzeit auf Basis zurückgesetzt werden."
        )
        intro.setWordWrap(True)

        self.active_label = QLabel()
        self.active_label.setWordWrap(True)
        self.list_widget = QListWidget()

        self.name = QLineEdit()
        self.name.setMaxLength(80)
        self.name.setPlaceholderText("z. B. Dunkles Studio")
        self.context = QPlainTextEdit()
        self.context.setMaximumHeight(120)
        self.context.setPlaceholderText(
            "Temporärer Szenenkontext: Umgebung, Stimmung, Situation, visuelle Kontinuität …"
        )
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("cinematic, low light, elegant, close-up")
        self.tags.setToolTip("Kommagetrennte Stil-Tags; sie fließen auch in die lokale Medienplanung ein.")

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Szenenkontext", self.context)
        form.addRow("Stil-Tags", self.tags)

        self.new_button = QPushButton("Neu")
        self.save_button = QPushButton("Speichern")
        self.delete_button = QPushButton("Löschen")
        self.activate_button = QPushButton("▶ Szene aktivieren")
        self.base_button = QPushButton("Basis verwenden")

        row = QHBoxLayout()
        row.addWidget(self.new_button)
        row.addWidget(self.delete_button)
        row.addWidget(self.save_button)
        row.addStretch(1)
        row.addWidget(self.base_button)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.active_label)
        layout.addWidget(self.list_widget, 1)
        layout.addLayout(form)
        layout.addLayout(row)

        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.new_button.clicked.connect(self.new_scene)
        self.save_button.clicked.connect(self.save_scene)
        self.delete_button.clicked.connect(self.delete_scene)
        self.activate_button.clicked.connect(self.activate_selected)
        self.base_button.clicked.connect(self.use_base)
        self.refresh()

    def active_scene(self) -> ScenePreset | None:
        return self.repository.active()

    def refresh(self, select_id: str | None = None) -> None:
        selected_id = select_id or self._selected_id()
        active = self.repository.active()
        active_id = active.id if active else None
        self._items.clear()
        self.list_widget.clear()

        for scene in self.repository.list():
            self._items[scene.id] = scene
            marker = "▶" if scene.id == active_id else "·"
            tag_preview = ", ".join(scene.style_tags[:4])
            suffix = f" · {tag_preview}" if tag_preview else ""
            item = QListWidgetItem(f"{marker}  {scene.name}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, scene.id)
            self.list_widget.addItem(item)
            if scene.id == selected_id:
                self.list_widget.setCurrentItem(item)

        if active is None:
            self.active_label.setText("Aktive Szene: Basis — kein zusätzlicher Szenenkontext")
        else:
            self.active_label.setText(f"Aktive Szene: {active.name}")

        if self.list_widget.count() and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)
        elif not self.list_widget.count():
            self.new_scene()

    def _selected_id(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self.delete_button.setEnabled(False)
            self.activate_button.setEnabled(False)
            return
        scene_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
        scene = self._items.get(scene_id) or self.repository.get(scene_id)
        if scene is None:
            return
        self.name.setText(scene.name)
        self.context.setPlainText(scene.context)
        self.tags.setText(", ".join(scene.style_tags))
        self.delete_button.setEnabled(True)
        self.activate_button.setEnabled(True)

    @staticmethod
    def _parse_tags(value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def new_scene(self) -> None:
        self.list_widget.setCurrentRow(-1)
        self.name.clear()
        self.context.clear()
        self.tags.clear()
        self.delete_button.setEnabled(False)
        self.activate_button.setEnabled(False)
        self.name.setFocus()

    def save_scene(self) -> None:
        name = self.name.text().strip()
        context = self.context.toPlainText().strip()
        if not name or not context:
            QMessageBox.warning(self, "Szene", "Bitte Name und Szenenkontext eintragen.")
            return
        try:
            saved = self.repository.upsert(
                scene_id=self._selected_id(),
                name=name,
                context=context,
                style_tags=self._parse_tags(self.tags.text()),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Szene", str(exc))
            return
        self.refresh(select_id=saved.id)
        if self.repository.load().active_id == saved.id:
            self.active_scene_changed.emit(saved.model_copy(deep=True))

    def delete_scene(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None:
            return
        scene = self.repository.get(scene_id)
        if scene is None:
            return
        answer = QMessageBox.question(
            self,
            "Szene löschen",
            f"Szene „{scene.name}“ wirklich löschen?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        was_active = self.repository.load().active_id == scene_id
        self.repository.delete(scene_id)
        self.refresh()
        if was_active:
            self.active_scene_changed.emit(None)

    def activate_selected(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None:
            return
        scene = self.repository.set_active(scene_id)
        self.refresh(select_id=scene_id)
        self.active_scene_changed.emit(scene.model_copy(deep=True) if scene else None)

    def use_base(self) -> None:
        self.repository.set_active(None)
        self.refresh()
        self.active_scene_changed.emit(None)
