from __future__ import annotations

import uuid

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ai.session_mode_store import SessionModeStore
from app.ai.session_modes import SessionMode, SessionModeState, TRAIT_NAMES
from app.memory.store import StateStore

_TRAIT_LABELS = {
    "dominance": "Dominanz",
    "strictness": "Strenge",
    "teasing": "Neckisch",
    "initiative": "Initiative",
    "persistence": "Beharrlichkeit",
    "creativity": "Kreativität",
    "autonomy": "Autonomie",
}


class SessionModesWidget(QWidget):
    """Editor for temporary, non-destructive persona overlays."""

    active_mode_changed = Signal(object)

    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = SessionModeStore(store)
        self.state: SessionModeState = self.repository.load()

        self.mode_combo = QComboBox()
        self.name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("z. B. cinematic, controlled, playful")
        self.offsets: dict[str, QDoubleSpinBox] = {}

        form = QFormLayout()
        form.addRow("Modus", self.mode_combo)
        form.addRow("Name", self.name_edit)
        form.addRow("Beschreibung", self.description_edit)
        form.addRow("Temporäre Stil-Tags", self.tags_edit)

        for trait_name in TRAIT_NAMES:
            spin = QDoubleSpinBox()
            spin.setRange(-0.50, 0.50)
            spin.setDecimals(2)
            spin.setSingleStep(0.05)
            spin.setPrefix("+")
            spin.setSpecialValueText("0.00")
            spin.setToolTip(
                "Temporärer Offset. Gesperrte Persona-Traits werden nicht überschrieben; die gelernte Basis bleibt unverändert."
            )
            self.offsets[trait_name] = spin
            form.addRow(_TRAIT_LABELS[trait_name], spin)

        self.active_label = QLabel()
        self.active_label.setWordWrap(True)
        self.note = QLabel(
            "Session-Modi verändern nur den Kontext der laufenden Unterhaltung und Medienplanung. Lernwerte, Grenzen und Snapshots der Basis-Persona werden dadurch nicht umgeschrieben."
        )
        self.note.setWordWrap(True)

        self.new_button = QPushButton("Neuer Modus")
        self.save_button = QPushButton("Modus speichern")
        self.delete_button = QPushButton("Löschen")
        self.activate_button = QPushButton("Aktivieren")
        self.base_button = QPushButton("Basis verwenden")

        buttons = QHBoxLayout()
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(self.base_button)
        buttons.addWidget(self.activate_button)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.active_label)
        layout.addWidget(self.note)
        layout.addStretch(1)
        layout.addLayout(buttons)

        self.mode_combo.currentIndexChanged.connect(self._load_selected)
        self.new_button.clicked.connect(self._new_mode)
        self.save_button.clicked.connect(self._save_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.activate_button.clicked.connect(self._activate_selected)
        self.base_button.clicked.connect(self._activate_base)

        self._refresh_combo()
        self._emit_active()

    def active_mode(self) -> SessionMode | None:
        return self.state.active_mode()

    def _refresh_combo(self, selected_id: str | None = None) -> None:
        target = selected_id or self.state.active_id
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for mode in self.state.modes:
            self.mode_combo.addItem(mode.name, mode.id)
        self.mode_combo.blockSignals(False)
        index = self.mode_combo.findData(target) if target else 0
        if index < 0 and self.mode_combo.count():
            index = 0
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self._load_selected()
        self._update_active_label()

    def _selected_mode(self) -> SessionMode | None:
        mode_id = self.mode_combo.currentData()
        if not mode_id:
            return None
        return next((mode for mode in self.state.modes if mode.id == mode_id), None)

    def _load_selected(self) -> None:
        mode = self._selected_mode()
        enabled = mode is not None
        self.delete_button.setEnabled(enabled)
        self.activate_button.setEnabled(enabled)
        if mode is None:
            return
        self.name_edit.setText(mode.name)
        self.description_edit.setText(mode.description)
        self.tags_edit.setText(", ".join(mode.style_tags))
        for name, spin in self.offsets.items():
            spin.setValue(mode.trait_offsets.get(name, 0.0))

    def _mode_from_form(self, mode_id: str) -> SessionMode:
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError("Der Session-Modus braucht einen Namen.")
        tags = [part.strip() for part in self.tags_edit.text().split(",") if part.strip()]
        offsets = {
            trait_name: spin.value()
            for trait_name, spin in self.offsets.items()
            if abs(spin.value()) >= 0.005
        }
        return SessionMode(
            id=mode_id,
            name=name,
            description=self.description_edit.text().strip(),
            trait_offsets=offsets,
            style_tags=tags,
        )

    def _new_mode(self) -> None:
        mode = SessionMode(
            id=f"custom-{uuid.uuid4().hex[:8]}",
            name="Neuer Modus",
            description="Benutzerdefinierter temporärer Session-Modus",
        )
        self.state.modes.append(mode)
        self.repository.save(self.state)
        self._refresh_combo(mode.id)
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _save_selected(self) -> None:
        selected = self._selected_mode()
        if selected is None:
            return
        try:
            updated = self._mode_from_form(selected.id)
        except ValueError as exc:
            QMessageBox.warning(self, "Session-Modus", str(exc))
            return
        self.state.modes = [updated if mode.id == selected.id else mode for mode in self.state.modes]
        self.repository.save(self.state)
        self._refresh_combo(updated.id)
        if self.state.active_id == updated.id:
            self.active_mode_changed.emit(updated)

    def _delete_selected(self) -> None:
        selected = self._selected_mode()
        if selected is None:
            return
        answer = QMessageBox.question(
            self,
            "Session-Modus löschen",
            f"Den Modus „{selected.name}“ wirklich löschen? Die Basis-Persona wird nicht verändert.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.state.modes = [mode for mode in self.state.modes if mode.id != selected.id]
        if self.state.active_id == selected.id:
            self.state.active_id = None
        self.repository.save(self.state)
        self._refresh_combo()
        self._emit_active()

    def _activate_selected(self) -> None:
        selected = self._selected_mode()
        if selected is None:
            return
        self.state.active_id = selected.id
        self.repository.save(self.state)
        self._update_active_label()
        self.active_mode_changed.emit(selected)

    def _activate_base(self) -> None:
        self.state.active_id = None
        self.repository.save(self.state)
        self._update_active_label()
        self.active_mode_changed.emit(None)

    def _update_active_label(self) -> None:
        active = self.state.active_mode()
        if active is None:
            self.active_label.setText("Aktiv: Basis-Persona ohne temporären Overlay")
        else:
            self.active_label.setText(
                f"Aktiv: {active.name} — {active.description or 'temporärer Persona-Overlay'}"
            )

    def _emit_active(self) -> None:
        self.active_mode_changed.emit(self.state.active_mode())
