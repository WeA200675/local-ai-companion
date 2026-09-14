from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.memory.conversations import ConversationRepository, ConversationThread


class ConversationsWidget(QWidget):
    """Manage isolated chat histories without duplicating persona or long-term memory."""

    active_conversation_changed = Signal(str)

    def __init__(
        self,
        repository: ConversationRepository,
        *,
        can_switch: Callable[[], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.can_switch = can_switch
        self._threads: dict[str, ConversationThread] = {}

        intro = QLabel(
            "Unterhaltungen trennen den Chatverlauf. Persona, Core Memory und adaptive Langzeit-Erinnerungen "
            "bleiben gemeinsam. Mit „Variante“ kannst du denselben Verlauf in eine neue Richtung verzweigen."
        )
        intro.setWordWrap(True)

        self.active_label = QLabel()
        self.active_label.setWordWrap(True)
        self.show_archived = QCheckBox("Archivierte anzeigen")
        self.list_widget = QListWidget()
        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(120)
        self.title_edit.setPlaceholderText("Titel der Unterhaltung")

        self.new_button = QPushButton("Neue Unterhaltung")
        self.rename_button = QPushButton("Umbenennen")
        self.activate_button = QPushButton("Öffnen")
        self.fork_button = QPushButton("Variante erstellen")
        self.archive_button = QPushButton("Archivieren")
        self.restore_button = QPushButton("Wiederherstellen")

        actions = QHBoxLayout()
        actions.addWidget(self.new_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.fork_button)
        actions.addStretch(1)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.archive_button)
        actions.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.active_label)
        layout.addWidget(self.show_archived)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.title_edit)
        layout.addLayout(actions)

        self.show_archived.toggled.connect(lambda _checked: self.refresh())
        self.list_widget.currentItemChanged.connect(self._selection_changed)
        self.new_button.clicked.connect(self.create_conversation)
        self.rename_button.clicked.connect(self.rename_selected)
        self.activate_button.clicked.connect(self.activate_selected)
        self.fork_button.clicked.connect(self.fork_selected)
        self.archive_button.clicked.connect(self.archive_selected)
        self.restore_button.clicked.connect(self.restore_selected)
        self.refresh()

    def _allow_switch(self) -> bool:
        if self.can_switch is None or self.can_switch():
            return True
        QMessageBox.information(
            self,
            "Unterhaltung",
            "Während ein lokaler KI-, Medien- oder Lernjob läuft, kann die Unterhaltung nicht gewechselt werden.",
        )
        return False

    def refresh(self, select_id: str | None = None) -> None:
        active_id = self.repository.active_id()
        selected_id = select_id or self._selected_id() or active_id
        self._threads.clear()
        self.list_widget.clear()
        threads = self.repository.list_threads(include_archived=self.show_archived.isChecked())
        for thread in threads:
            self._threads[thread.id] = thread
            active = "▶" if thread.id == active_id else "·"
            archived = " [Archiv]" if thread.archived else ""
            item = QListWidgetItem(
                f"{active}  {thread.title} · {thread.message_count} Nachrichten{archived}"
            )
            item.setData(Qt.ItemDataRole.UserRole, thread.id)
            self.list_widget.addItem(item)
            if thread.id == selected_id:
                self.list_widget.setCurrentItem(item)

        active = self.repository.get(active_id, include_archived=False)
        self.active_label.setText(
            f"Aktiv: {active.title}" if active is not None else "Keine aktive Unterhaltung"
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

    def _selected(self) -> ConversationThread | None:
        thread_id = self._selected_id()
        if thread_id is None:
            return None
        return self._threads.get(thread_id) or self.repository.get(thread_id)

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        thread = self._selected() if current is not None else None
        enabled = thread is not None
        self.rename_button.setEnabled(enabled)
        self.fork_button.setEnabled(enabled)
        self.activate_button.setEnabled(enabled and not bool(thread and thread.archived))
        self.archive_button.setEnabled(enabled and not bool(thread and thread.archived))
        self.restore_button.setEnabled(enabled and bool(thread and thread.archived))
        if thread is not None:
            self.title_edit.setText(thread.title)

    def create_conversation(self) -> None:
        if not self._allow_switch():
            return
        title = self.title_edit.text().strip() or "Neue Unterhaltung"
        created = self.repository.create(title, activate=True)
        self.refresh(select_id=created.id)
        self.active_conversation_changed.emit(created.id)

    def rename_selected(self) -> None:
        thread = self._selected()
        if thread is None:
            return
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Unterhaltung", "Bitte einen Titel eingeben.")
            return
        updated = self.repository.rename(thread.id, title)
        self.refresh(select_id=updated.id)

    def activate_selected(self) -> None:
        if not self._allow_switch():
            return
        thread = self._selected()
        if thread is None or thread.archived:
            return
        self.repository.set_active(thread.id)
        self.refresh(select_id=thread.id)
        self.active_conversation_changed.emit(thread.id)

    def fork_selected(self) -> None:
        if not self._allow_switch():
            return
        thread = self._selected()
        if thread is None:
            return
        title = self.title_edit.text().strip()
        if not title or title == thread.title:
            title = f"{thread.title} – Variante"
        forked = self.repository.fork(thread.id, title=title, activate=True)
        self.refresh(select_id=forked.id)
        self.active_conversation_changed.emit(forked.id)

    def archive_selected(self) -> None:
        thread = self._selected()
        if thread is None or thread.archived:
            return
        if thread.id == self.repository.active_id() and not self._allow_switch():
            return
        answer = QMessageBox.question(
            self,
            "Unterhaltung archivieren",
            f"„{thread.title}“ archivieren? Der Verlauf bleibt lokal erhalten.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.archive(thread.id)
        except ValueError as exc:
            QMessageBox.information(self, "Unterhaltung", str(exc))
            return
        active_id = self.repository.active_id()
        self.refresh(select_id=active_id)
        self.active_conversation_changed.emit(active_id)

    def restore_selected(self) -> None:
        thread = self._selected()
        if thread is None or not thread.archived:
            return
        restored = self.repository.unarchive(thread.id)
        self.refresh(select_id=restored.id)
