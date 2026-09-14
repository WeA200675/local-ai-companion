from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ai.model import ChatMessage, LocalModelError, OllamaClient
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.memory.store import StateStore


class ModelWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        client: OllamaClient,
        messages: list[ChatMessage],
        system_prompt: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._messages = messages
        self._system_prompt = system_prompt

    def run(self) -> None:
        try:
            reply = self._client.chat(self._messages, system_prompt=self._system_prompt)
        except LocalModelError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # defensive UI boundary
            self.failed.emit(f"Unexpected local model error: {exc}")
            return
        self.completed.emit(reply)


class ChatWidget(QWidget):
    def __init__(
        self,
        store: StateStore,
        model: OllamaClient,
        persona: PersonaState,
        preference_tags: list[str] | None = None,
        on_persona_changed: Callable[[PersonaState], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.model = model
        self.persona = persona
        self.preference_tags = preference_tags or []
        self.on_persona_changed = on_persona_changed
        self._worker: ModelWorker | None = None

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Schreib deiner lokalen KI …")
        self.input.setMaximumHeight(120)

        self.send_button = QPushButton("Senden")
        self.clear_button = QPushButton("Chat leeren")
        self.status = QLabel(f"Modell: {self.model.model}")

        button_row = QHBoxLayout()
        button_row.addWidget(self.status, 1)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.send_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.input)
        layout.addLayout(button_row)

        self.send_button.clicked.connect(self.send_current)
        self.clear_button.clicked.connect(self.clear_chat)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.send_current)

        self._load_history()

    def _load_history(self) -> None:
        self.transcript.clear()
        for message in self.store.list_messages():
            self._append_message(message)

    def _append_message(self, message: ChatMessage) -> None:
        label = "Du" if message.role == "user" else self.persona.name
        safe_text = message.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.transcript.append(f"<b>{label}:</b><br>{safe_text}<br>")
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def send_current(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        text = self.input.toPlainText().strip()
        if not text:
            return

        self.input.clear()
        self.store.append_message("user", text)
        self._append_message(ChatMessage(role="user", content=text))

        messages = self.store.list_messages(limit=60)
        system_prompt = build_system_prompt(self.persona, self.preference_tags)
        self._set_busy(True)

        worker = ModelWorker(self.model, messages, system_prompt, self)
        worker.completed.connect(self._model_completed)
        worker.failed.connect(self._model_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        worker.start()

    def _model_completed(self, reply: str) -> None:
        self.store.append_message("assistant", reply)
        self._append_message(ChatMessage(role="assistant", content=reply))

    def _model_failed(self, error: str) -> None:
        QMessageBox.warning(
            self,
            "Lokales Modell nicht erreichbar",
            f"{error}\n\nPrüfe, ob Ollama läuft und das konfigurierte Modell installiert ist.",
        )

    def _worker_finished(self) -> None:
        self._set_busy(False)
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.status.setText("KI denkt lokal …" if busy else f"Modell: {self.model.model}")

    def clear_chat(self) -> None:
        answer = QMessageBox.question(
            self,
            "Chat leeren",
            "Nur den Chatverlauf löschen? Persona und Snapshots bleiben erhalten.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.store.clear_messages()
            self.transcript.clear()
