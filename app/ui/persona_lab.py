from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import sessionmaker

from app.ai.persona import PersonaState, Trait
from app.memory.snapshots import SnapshotStore
from app.memory.store import StateStore


TRAITS = (
    "dominance",
    "strictness",
    "teasing",
    "initiative",
    "persistence",
    "creativity",
    "autonomy",
)


class TraitEditor(QWidget):
    changed = Signal()

    def __init__(self, trait: Trait, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.trait = trait

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(38)
        self.minimum = self._percent_spin()
        self.maximum = self._percent_spin()
        self.learning_rate = self._percent_spin()
        self.locked = QCheckBox("gesperrt")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.slider, 1)
        row.addWidget(self.value_label)
        row.addWidget(QLabel("Min"))
        row.addWidget(self.minimum)
        row.addWidget(QLabel("Max"))
        row.addWidget(self.maximum)
        row.addWidget(QLabel("Lernen"))
        row.addWidget(self.learning_rate)
        row.addWidget(self.locked)

        self.slider.valueChanged.connect(self._slider_changed)
        self.minimum.valueChanged.connect(self._minimum_changed)
        self.maximum.valueChanged.connect(self._maximum_changed)
        self.learning_rate.valueChanged.connect(self._learning_rate_changed)
        self.locked.toggled.connect(self._lock_changed)
        self.refresh(trait)

    @staticmethod
    def _percent_spin() -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setSuffix("%")
        spin.setMaximumWidth(76)
        return spin

    def _slider_changed(self, value: int) -> None:
        self.value_label.setText(f"{value}%")
        self.trait.current = value / 100
        self.changed.emit()

    def _minimum_changed(self, value: int) -> None:
        if value > self.maximum.value():
            self.maximum.setValue(value)
        self._apply_bounds(value, self.maximum.value())

    def _maximum_changed(self, value: int) -> None:
        if value < self.minimum.value():
            self.minimum.setValue(value)
        self._apply_bounds(self.minimum.value(), value)

    def _apply_bounds(self, minimum: int, maximum: int) -> None:
        self.trait.user_min = minimum / 100
        self.trait.user_max = maximum / 100
        current = min(maximum, max(minimum, round(self.trait.current * 100)))
        self.slider.blockSignals(True)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(current)
        self.slider.blockSignals(False)
        self.trait.current = current / 100
        self.value_label.setText(f"{current}%")
        self.changed.emit()

    def _learning_rate_changed(self, value: int) -> None:
        self.trait.learning_rate = value / 100
        self.changed.emit()

    def _lock_changed(self, locked: bool) -> None:
        self.trait.locked = locked
        self.changed.emit()

    def refresh(self, trait: Trait) -> None:
        self.trait = trait
        widgets = (self.slider, self.minimum, self.maximum, self.learning_rate, self.locked)
        for widget in widgets:
            widget.blockSignals(True)

        minimum = round(trait.user_min * 100)
        maximum = round(trait.user_max * 100)
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        current = min(maximum, max(minimum, round(trait.current * 100)))
        self.minimum.setValue(minimum)
        self.maximum.setValue(maximum)
        self.learning_rate.setValue(round(trait.learning_rate * 100))
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(current)
        self.value_label.setText(f"{current}%")
        self.locked.setChecked(trait.locked)

        for widget in widgets:
            widget.blockSignals(False)


class PersonaLab(QWidget):
    persona_changed = Signal(object)
    preference_tags_changed = Signal(list)

    def __init__(
        self,
        store: StateStore,
        session_factory: sessionmaker,
        persona: PersonaState,
        preference_tags: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.session_factory = session_factory
        self.persona = persona
        self.editors: dict[str, TraitEditor] = {}

        self.name_edit = QLineEdit(persona.name)
        self.tags_edit = QLineEdit(", ".join(preference_tags))
        self.tags_edit.setPlaceholderText("z. B. dominant, teasing, latex")

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Präferenz-Tags", self.tags_edit)

        for name in TRAITS:
            editor = TraitEditor(getattr(persona, name))
            editor.changed.connect(self._save_live_state)
            self.editors[name] = editor
            form.addRow(name.capitalize(), editor)

        self.snapshot_list = QListWidget()
        self.learning_list = QListWidget()
        self.learning_list.setMaximumHeight(150)
        self.save_snapshot_button = QPushButton("Snapshot speichern")
        self.restore_button = QPushButton("Ausgewählten Snapshot laden")
        self.refresh_button = QPushButton("Historie aktualisieren")

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_snapshot_button)
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(
            QLabel(
                "Min/Max begrenzen sowohl manuelle Werte als auch Lernen; die Lernrate bestimmt, wie stark Feedback wirkt."
            )
        )
        layout.addWidget(QLabel("Persona-Historie"))
        layout.addWidget(self.snapshot_list, 1)
        layout.addWidget(QLabel("Lern-Audit (neueste zuerst)"))
        layout.addWidget(self.learning_list)
        layout.addLayout(buttons)

        self.name_edit.editingFinished.connect(self._save_live_state)
        self.tags_edit.editingFinished.connect(self._save_tags)
        self.save_snapshot_button.clicked.connect(self.save_snapshot)
        self.restore_button.clicked.connect(self.restore_selected)
        self.refresh_button.clicked.connect(self.refresh_history)

        self.refresh_history()

    def set_persona(self, persona: PersonaState) -> None:
        """Refresh editors when the chat learning layer changes the persona."""

        self.persona = persona
        self.name_edit.setText(persona.name)
        for name, editor in self.editors.items():
            editor.refresh(getattr(persona, name))
        self.refresh_learning_events()
        self.refresh_snapshots()

    def _save_live_state(self) -> None:
        self.persona.name = self.name_edit.text().strip() or "Companion"
        self.persona.revision += 1
        self.store.save_persona(self.persona)
        self.persona_changed.emit(self.persona)

    def _save_tags(self) -> None:
        tags = [part.strip() for part in self.tags_edit.text().split(",") if part.strip()]
        self.store.save_preference_tags(tags)
        self.preference_tags_changed.emit(tags)

    def save_snapshot(self) -> None:
        self._save_live_state()
        with self.session_factory() as session:
            snapshot = SnapshotStore(session).save(self.persona, kind="manual")
        self.refresh_snapshots()
        QMessageBox.information(self, "Snapshot", f"Snapshot #{snapshot.id} gespeichert.")

    def refresh_history(self) -> None:
        self.refresh_snapshots()
        self.refresh_learning_events()

    def refresh_snapshots(self) -> None:
        self.snapshot_list.clear()
        with self.session_factory() as session:
            snapshots = SnapshotStore(session).list_recent()
        for snapshot in snapshots:
            stamp = snapshot.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            item = QListWidgetItem(f"#{snapshot.id}  {snapshot.kind}  {stamp}")
            item.setData(Qt.ItemDataRole.UserRole, snapshot.id)
            self.snapshot_list.addItem(item)

    def refresh_learning_events(self) -> None:
        self.learning_list.clear()
        for event in self.store.list_learning_events(limit=30):
            created_at = event["created_at"]
            stamp = created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            deltas = event["deltas"]
            changed = ", ".join(
                f"{name} {float(value):+.2f}"
                for name, value in deltas.items()
                if abs(float(value)) >= 0.01
            )
            if not changed:
                changed = "keine Änderung"
            rationale = str(event["rationale"]).strip()
            suffix = f" — {rationale}" if rationale else ""
            self.learning_list.addItem(
                f"{stamp}  {event['feedback']}: {changed}{suffix}"
            )

    def restore_selected(self) -> None:
        item = self.snapshot_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Snapshot", "Bitte zuerst einen Snapshot auswählen.")
            return
        snapshot_id = int(item.data(Qt.ItemDataRole.UserRole))
        answer = QMessageBox.question(
            self,
            "Persona zurücksetzen",
            "Vor dem Zurücksetzen wird der aktuelle Stand automatisch als pre_restore-Snapshot gesichert. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        with self.session_factory() as session:
            restored = SnapshotStore(session).restore(self.persona, snapshot_id)

        self.persona = restored
        self.store.save_persona(restored)
        self.name_edit.setText(restored.name)
        for name, editor in self.editors.items():
            editor.refresh(getattr(restored, name))
        self.persona_changed.emit(restored)
        self.refresh_history()
