from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from app.ai.variety import VarietyCard, VarietyRepository


class VarietyWidget(QWidget):
    """Conversation-scoped temporary creative prompts for more varied exchanges."""

    active_card_changed = Signal(object)

    def __init__(
        self,
        repository: VarietyRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id
        self._cards: dict[str, VarietyCard] = {}

        intro = QLabel(
            "Das Impuls-Deck bringt Abwechslung, ohne die gelernte Persona oder Memory zu verändern. "
            "Ein Impuls gilt nur für die aktuell ausgewählte Unterhaltung und kann jederzeit entfernt werden."
        )
        intro.setWordWrap(True)
        self.active_label = QLabel()
        self.active_label.setWordWrap(True)

        self.category = QComboBox()
        self.category.addItem("Alle Kategorien", "")
        self.draw_button = QPushButton("🎲 Neu mischen")
        self.clear_button = QPushButton("Basis verwenden")

        draw_row = QHBoxLayout()
        draw_row.addWidget(QLabel("Misch-Kategorie"))
        draw_row.addWidget(self.category, 1)
        draw_row.addWidget(self.clear_button)
        draw_row.addWidget(self.draw_button)

        self.list_widget = QListWidget()
        self.name = QLineEdit()
        self.name.setMaxLength(80)
        self.card_category = QLineEdit()
        self.card_category.setMaxLength(40)
        self.instruction = QPlainTextEdit()
        self.instruction.setMaximumHeight(100)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("cinematic, playful, concise")
        self.enabled = QCheckBox("Aktiv")
        self.enabled.setChecked(True)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Kategorie", self.card_category)
        form.addRow("Temporärer Impuls", self.instruction)
        form.addRow("Stil-Tags", self.tags)
        form.addRow("", self.enabled)

        self.new_button = QPushButton("Eigener Impuls")
        self.save_button = QPushButton("Speichern")
        self.activate_button = QPushButton("Auswahl aktivieren")
        self.delete_button = QPushButton("Löschen")

        edit_row = QHBoxLayout()
        edit_row.addWidget(self.new_button)
        edit_row.addWidget(self.delete_button)
        edit_row.addStretch(1)
        edit_row.addWidget(self.activate_button)
        edit_row.addWidget(self.save_button)

        note = QLabel(
            "Eingebaute Impulse sind bewusst allgemein gehalten. Eigene Karten können frei ergänzt werden; "
            "sie bleiben lokale Konfiguration und werden nicht ins Langzeit-Memory übernommen."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.active_label)
        layout.addLayout(draw_row)
        layout.addWidget(self.list_widget, 1)
        layout.addLayout(form)
        layout.addLayout(edit_row)
        layout.addWidget(note)

        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear_active)
        self.new_button.clicked.connect(self.new_custom)
        self.save_button.clicked.connect(self.save_custom)
        self.activate_button.clicked.connect(self.activate_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.refresh()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()
        self.active_card_changed.emit(self.repository.active(conversation_id))

    def active_card(self) -> VarietyCard | None:
        return self.repository.active(self.conversation_id)

    def refresh(self, select_id: str | None = None) -> None:
        selected = select_id or self._selected_id()
        active = self.repository.active(self.conversation_id)
        active_id = active.id if active else None
        cards = self.repository.list_cards()
        self._cards = {card.id: card for card in cards}

        categories = sorted({card.category for card in cards if card.enabled}, key=str.casefold)
        current_category = self.category.currentData()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("Alle Kategorien", "")
        for category in categories:
            self.category.addItem(category, category)
        index = self.category.findData(current_category)
        if index >= 0:
            self.category.setCurrentIndex(index)
        self.category.blockSignals(False)

        self.list_widget.clear()
        for card in cards:
            marker = "▶" if card.id == active_id else "·"
            source = "Standard" if card.builtin else "Eigener"
            disabled = " · aus" if not card.enabled else ""
            item = QListWidgetItem(f"{marker}  {card.name} · {card.category} · {source}{disabled}")
            item.setData(Qt.ItemDataRole.UserRole, card.id)
            self.list_widget.addItem(item)
            if card.id == selected:
                self.list_widget.setCurrentItem(item)

        if active is None:
            self.active_label.setText("Aktiver Impuls: keiner — Basis-Kontext")
        else:
            self.active_label.setText(
                f"Aktiver Impuls: {active.name} — {active.instruction}"
            )
        if self.list_widget.count() and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)
        self._selection_changed(self.list_widget.currentItem(), None)

    def _selected_id(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _selected(self) -> VarietyCard | None:
        card_id = self._selected_id()
        return self._cards.get(card_id or "")

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        card = self._selected() if current is not None else None
        if card is None:
            self.delete_button.setEnabled(False)
            self.activate_button.setEnabled(False)
            return
        self.name.setText(card.name)
        self.card_category.setText(card.category)
        self.instruction.setPlainText(card.instruction)
        self.tags.setText(", ".join(card.style_tags))
        self.enabled.setChecked(card.enabled)
        editable = not card.builtin
        self.name.setEnabled(editable)
        self.card_category.setEnabled(editable)
        self.instruction.setEnabled(editable)
        self.tags.setEnabled(editable)
        self.enabled.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)
        self.activate_button.setEnabled(card.enabled)

    @staticmethod
    def _parse_tags(value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def draw(self) -> None:
        category = str(self.category.currentData() or "")
        try:
            card = self.repository.draw(
                self.conversation_id,
                category=category or None,
            )
        except ValueError as exc:
            QMessageBox.information(self, "Impuls-Deck", str(exc))
            return
        self.refresh(select_id=card.id)
        self.active_card_changed.emit(card)

    def clear_active(self) -> None:
        self.repository.set_active(self.conversation_id, None)
        self.refresh()
        self.active_card_changed.emit(None)

    def new_custom(self) -> None:
        self.list_widget.setCurrentRow(-1)
        self.name.setEnabled(True)
        self.card_category.setEnabled(True)
        self.instruction.setEnabled(True)
        self.tags.setEnabled(True)
        self.enabled.setEnabled(True)
        self.save_button.setEnabled(True)
        self.delete_button.setEnabled(False)
        self.activate_button.setEnabled(False)
        self.name.clear()
        self.card_category.setText("Eigene")
        self.instruction.clear()
        self.tags.clear()
        self.enabled.setChecked(True)
        self.name.setFocus()

    def save_custom(self) -> None:
        selected = self._selected()
        card_id = selected.id if selected is not None and not selected.builtin else None
        name = self.name.text().strip()
        instruction = self.instruction.toPlainText().strip()
        if not name or not instruction:
            QMessageBox.warning(self, "Impuls-Deck", "Bitte Name und Impuls eintragen.")
            return
        try:
            card = self.repository.upsert_custom(
                card_id=card_id,
                name=name,
                category=self.card_category.text().strip() or "Eigene",
                instruction=instruction,
                style_tags=self._parse_tags(self.tags.text()),
                enabled=self.enabled.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Impuls-Deck", str(exc))
            return
        self.refresh(select_id=card.id)

    def activate_selected(self) -> None:
        card = self._selected()
        if card is None or not card.enabled:
            return
        active = self.repository.set_active(self.conversation_id, card.id)
        self.refresh(select_id=card.id)
        self.active_card_changed.emit(active)

    def delete_selected(self) -> None:
        card = self._selected()
        if card is None or card.builtin:
            return
        answer = QMessageBox.question(
            self,
            "Impuls löschen",
            f"Eigenen Impuls „{card.name}“ wirklich löschen?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        was_active = self.repository.active(self.conversation_id)
        self.repository.delete_custom(card.id)
        self.refresh()
        if was_active is not None and was_active.id == card.id:
            self.active_card_changed.emit(None)
