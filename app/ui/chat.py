from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
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

from app.ai.learning import BehaviorLearner, Feedback, LearningResult
from app.ai.memory_learning import AdaptiveMemoryLearner
from app.ai.model import ChatMessage, LocalModelError, OllamaClient
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.media.service import MediaService
from app.memory.store import StateStore
from app.settings import AppSettings
from app.ui.media_preview import MediaPreview


class ModelWorker(QThread):
    token_received = Signal(str)
    completed = Signal(str)
    stopped = Signal(str)
    interrupted = Signal(str, str)
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
        self._stop_event = Event()

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        parts: list[str] = []
        try:
            for chunk in self._client.chat_stream(
                self._messages,
                system_prompt=self._system_prompt,
                should_stop=self._stop_event.is_set,
            ):
                if self._stop_event.is_set():
                    break
                parts.append(chunk)
                self.token_received.emit(chunk)
        except LocalModelError as exc:
            partial = "".join(parts)
            if self._stop_event.is_set():
                self.stopped.emit(partial)
            elif partial.strip():
                self.interrupted.emit(partial, str(exc))
            else:
                self.failed.emit(str(exc))
            return
        except Exception as exc:  # defensive UI boundary
            partial = "".join(parts)
            error = f"Unexpected local model error: {exc}"
            if self._stop_event.is_set():
                self.stopped.emit(partial)
            elif partial.strip():
                self.interrupted.emit(partial, error)
            else:
                self.failed.emit(error)
            return

        reply = "".join(parts)
        if self._stop_event.is_set():
            self.stopped.emit(reply)
        elif reply.strip():
            self.completed.emit(reply.strip())
        else:
            self.failed.emit("Local model returned an empty streaming response")


class MediaWorker(QThread):
    generated = Signal(str, str)
    skipped = Signal()
    failed = Signal(str)

    def __init__(
        self,
        service: MediaService,
        *,
        user_text: str,
        assistant_text: str,
        persona: PersonaState,
        preference_tags: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._user_text = user_text
        self._assistant_text = assistant_text
        self._persona = persona.model_copy(deep=True)
        self._preference_tags = list(preference_tags)

    def run(self) -> None:
        try:
            result = self._service.generate_for_exchange(
                user_text=self._user_text,
                assistant_text=self._assistant_text,
                persona=self._persona,
                preference_tags=self._preference_tags,
            )
        except Exception as exc:  # media must never take the chat down
            self.failed.emit(str(exc))
            return
        if result is None:
            self.skipped.emit()
            return
        description = " · ".join(
            part
            for part in (
                result.intent.mood.strip(),
                result.intent.theme.strip(),
                result.intent.visual_style.strip(),
            )
            if part
        )
        self.generated.emit(str(result.path), description)


class LearningWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        learner: BehaviorLearner,
        *,
        user_text: str,
        assistant_text: str,
        feedback: Feedback,
        persona: PersonaState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._learner = learner
        self._user_text = user_text
        self._assistant_text = assistant_text
        self._feedback = feedback
        self._persona = persona.model_copy(deep=True)

    def run(self) -> None:
        try:
            result = self._learner.apply(
                user_text=self._user_text,
                assistant_text=self._assistant_text,
                feedback=self._feedback,
                persona=self._persona,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)


class MemoryWorker(QThread):
    completed = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        learner: AdaptiveMemoryLearner,
        store: StateStore,
        *,
        user_text: str,
        assistant_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._learner = learner
        self._store = store
        self._user_text = user_text
        self._assistant_text = assistant_text

    def run(self) -> None:
        try:
            proposal = self._learner.propose(
                user_text=self._user_text,
                assistant_text=self._assistant_text,
            )
            accepted = self._learner.accepted(proposal)
            for observation in accepted:
                self._store.upsert_memory_observation(
                    category=observation.category,
                    summary=observation.summary,
                    confidence=observation.confidence,
                )
        except Exception as exc:  # adaptive memory must never break chat
            self.failed.emit(str(exc))
            return
        self.completed.emit(len(accepted))


class ChatWidget(QWidget):
    media_history_changed = Signal()
    memory_changed = Signal()

    def __init__(
        self,
        store: StateStore,
        model: OllamaClient,
        persona: PersonaState,
        preference_tags: list[str] | None = None,
        media_service: MediaService | None = None,
        settings: AppSettings | None = None,
        on_persona_changed: Callable[[PersonaState], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.model = model
        self.persona = persona
        self.preference_tags = preference_tags or []
        self.media_service = media_service
        self.settings = settings or AppSettings()
        self.on_persona_changed = on_persona_changed
        self.learner = BehaviorLearner(model)
        self.memory_learner = AdaptiveMemoryLearner(model)
        self._worker: ModelWorker | None = None
        self._media_worker: MediaWorker | None = None
        self._learning_worker: LearningWorker | None = None
        self._memory_worker: MemoryWorker | None = None
        self._pending_user_text = ""
        self._latest_user_text = ""
        self._latest_assistant_text = ""
        self._streaming_started = False
        self._generation_was_stopped = False
        self._generation_was_interrupted = False

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Schreib deiner lokalen KI …")
        self.input.setMaximumHeight(120)

        self.media_preview = MediaPreview()
        self.media_preview.setVisible(bool(self.media_service and self.media_service.enabled))

        self.more_button = QPushButton("👍 Mehr davon")
        self.less_button = QPushButton("👎 Weniger davon")
        self.more_button.setEnabled(False)
        self.less_button.setEnabled(False)
        self.learning_label = QLabel("Feedback verändert nur nicht gesperrte Persona-Traits.")

        feedback_row = QHBoxLayout()
        feedback_row.addWidget(self.learning_label, 1)
        feedback_row.addWidget(self.less_button)
        feedback_row.addWidget(self.more_button)

        self.send_button = QPushButton("Senden")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip("Laufende Textantwort abbrechen")
        self.clear_button = QPushButton("Chat leeren")
        self.status = QLabel(f"Modell: {self.model.model}")

        button_row = QHBoxLayout()
        button_row.addWidget(self.status, 1)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.send_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.media_preview)
        layout.addLayout(feedback_row)
        layout.addWidget(self.input)
        layout.addLayout(button_row)

        self.send_button.clicked.connect(self.send_current)
        self.stop_button.clicked.connect(self.stop_current_response)
        self.clear_button.clicked.connect(self.clear_chat)
        self.more_button.clicked.connect(lambda: self._start_learning("positive"))
        self.less_button.clicked.connect(lambda: self._start_learning("negative"))
        self.send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.send_shortcut.activated.connect(self.send_current)
        self.stop_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.stop_shortcut.activated.connect(self.stop_current_response)

        self._load_history()

    def can_reconfigure(self) -> bool:
        workers = (
            self._worker,
            self._media_worker,
            self._learning_worker,
            self._memory_worker,
        )
        return not any(worker is not None and worker.isRunning() for worker in workers)

    def set_services(
        self,
        model: OllamaClient,
        media_service: MediaService | None,
        settings: AppSettings,
    ) -> None:
        if not self.can_reconfigure():
            raise RuntimeError("Backends cannot be changed while a local worker is running")
        self.model = model
        self.learner = BehaviorLearner(model)
        self.memory_learner = AdaptiveMemoryLearner(model)
        self.media_service = media_service
        self.settings = settings.model_copy(deep=True)
        self.media_preview.setVisible(bool(media_service and media_service.enabled))
        self.status.setText(f"Modell: {self.model.model}")

    def _load_history(self) -> None:
        self.transcript.clear()
        for message in self.store.list_messages():
            self._append_message(message)

    def _append_message(self, message: ChatMessage) -> None:
        label = "Du" if message.role == "user" else self.persona.name
        safe_label = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_text = (
            message.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        safe_text = safe_text.replace("\n", "<br>")
        self.transcript.append(f"<b>{safe_label}:</b><br>{safe_text}<br>")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        self.transcript.verticalScrollBar().setValue(
            self.transcript.verticalScrollBar().maximum()
        )

    def _stream_token(self, token: str) -> None:
        if not token:
            return
        if not self._streaming_started:
            label = self.persona.name
            safe_label = (
                label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            self.transcript.append(f"<b>{safe_label}:</b><br>")
            self._streaming_started = True
            self.status.setText("KI antwortet lokal …")

        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.transcript.setTextCursor(cursor)
        self._scroll_to_bottom()

    def _finish_streaming_message(self) -> None:
        if not self._streaming_started:
            return
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        self.transcript.setTextCursor(cursor)
        self._streaming_started = False
        self._scroll_to_bottom()

    def send_current(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        text = self.input.toPlainText().strip()
        if not text:
            return

        self._pending_user_text = text
        self._streaming_started = False
        self._generation_was_stopped = False
        self._generation_was_interrupted = False
        self.more_button.setEnabled(False)
        self.less_button.setEnabled(False)
        self.input.clear()
        self.store.append_message("user", text)
        self._append_message(ChatMessage(role="user", content=text))

        messages = self.store.list_messages(limit=60)
        memory_notes = (
            self.store.list_active_memory_summaries(limit=12)
            if self.settings.adaptive_memory_enabled
            else []
        )
        system_prompt = build_system_prompt(
            self.persona,
            self.preference_tags,
            memory_notes,
        )
        self._set_busy(True)

        worker = ModelWorker(self.model, messages, system_prompt, self)
        worker.token_received.connect(self._stream_token)
        worker.completed.connect(self._model_completed)
        worker.stopped.connect(self._model_stopped)
        worker.interrupted.connect(self._model_interrupted)
        worker.failed.connect(self._model_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        worker.start()

    def stop_current_response(self) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning() or worker.stop_requested:
            return
        worker.request_stop()
        self.stop_button.setEnabled(False)
        self.status.setText("Stoppe laufende Antwort …")

    def _model_completed(self, reply: str) -> None:
        self._finish_streaming_message()
        self.store.append_message("assistant", reply)
        self._latest_user_text = self._pending_user_text
        self._latest_assistant_text = reply
        self.more_button.setEnabled(True)
        self.less_button.setEnabled(True)
        self._start_media_generation(self._pending_user_text, reply)
        self._maybe_start_memory_learning(self._pending_user_text, reply)

    def _model_stopped(self, partial: str) -> None:
        clean = partial.strip()
        self._finish_streaming_message()
        if clean:
            self.store.append_message("assistant", clean)
        self._latest_user_text = ""
        self._latest_assistant_text = ""
        self.more_button.setEnabled(False)
        self.less_button.setEnabled(False)
        self._generation_was_stopped = True
        self.status.setText("Antwort gestoppt")

    def _model_interrupted(self, partial: str, error: str) -> None:
        clean = partial.strip()
        self._finish_streaming_message()
        if clean:
            self.store.append_message("assistant", clean)
        self._latest_user_text = ""
        self._latest_assistant_text = ""
        self.more_button.setEnabled(False)
        self.less_button.setEnabled(False)
        self._generation_was_interrupted = True
        self.status.setText(f"Antwort unterbrochen: {error}")

    def _model_failed(self, error: str) -> None:
        self._finish_streaming_message()
        QMessageBox.warning(
            self,
            "Lokales Modell nicht erreichbar",
            f"{error}\n\nPrüfe, ob Ollama läuft und das konfigurierte Modell installiert ist.",
        )

    def _worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._set_busy(False)
        if self._generation_was_stopped:
            self.status.setText("Antwort gestoppt")
        elif self._generation_was_interrupted:
            self.status.setText("Antwort wurde unterbrochen; Teiltext wurde lokal gespeichert")
        if worker is not None:
            worker.deleteLater()

    def _set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.clear_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        if busy:
            self.status.setText("KI denkt lokal …")
        elif not self._background_worker_running():
            self.status.setText(f"Modell: {self.model.model}")

    def _background_worker_running(self) -> bool:
        workers = (self._media_worker, self._learning_worker, self._memory_worker)
        return any(worker is not None and worker.isRunning() for worker in workers)

    def _start_media_generation(self, user_text: str, assistant_text: str) -> None:
        if not self.media_service or not self.media_service.enabled:
            return
        if self._media_worker is not None and self._media_worker.isRunning():
            return

        self.media_preview.setVisible(True)
        self.status.setText("KI plant optional ein lokales Bild …")
        worker = MediaWorker(
            self.media_service,
            user_text=user_text,
            assistant_text=assistant_text,
            persona=self.persona,
            preference_tags=self.preference_tags,
            parent=self,
        )
        worker.generated.connect(self._media_generated)
        worker.skipped.connect(self._media_skipped)
        worker.failed.connect(self._media_failed)
        worker.finished.connect(self._media_finished)
        self._media_worker = worker
        worker.start()

    def _media_generated(self, path: str, description: str) -> None:
        self.media_preview.show_media(path, description=description)
        self.status.setText("Lokales Medium erzeugt")
        self.media_history_changed.emit()

    def _media_skipped(self) -> None:
        if self._memory_worker is None or not self._memory_worker.isRunning():
            self.status.setText("Kein Bild für diese Antwort nötig")

    def _media_failed(self, error: str) -> None:
        self.status.setText(f"Medien-Backend: {error}")

    def _media_finished(self) -> None:
        worker = self._media_worker
        self._media_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._worker is None or not self._worker.isRunning():
            if not self._background_worker_running():
                self.status.setText(f"Modell: {self.model.model}")

    def _maybe_start_memory_learning(self, user_text: str, assistant_text: str) -> None:
        if not self.settings.adaptive_memory_enabled:
            return
        if self._memory_worker is not None and self._memory_worker.isRunning():
            return
        count = self.store.assistant_message_count()
        if count <= 0 or count % self.settings.adaptive_memory_interval != 0:
            return

        self.status.setText("Lokales Memory prüft stabile Präferenzen …")
        worker = MemoryWorker(
            self.memory_learner,
            self.store,
            user_text=user_text,
            assistant_text=assistant_text,
            parent=self,
        )
        worker.completed.connect(self._memory_completed)
        worker.failed.connect(self._memory_failed)
        worker.finished.connect(self._memory_finished)
        self._memory_worker = worker
        worker.start()

    def _memory_completed(self, stored_count: int) -> None:
        if stored_count:
            self.status.setText(f"Memory aktualisiert: {stored_count} Beobachtung(en)")
            self.memory_changed.emit()

    def _memory_failed(self, error: str) -> None:
        self.status.setText(f"Memory-Lernen übersprungen: {error}")

    def _memory_finished(self) -> None:
        worker = self._memory_worker
        self._memory_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._worker is None or not self._worker.isRunning():
            if not self._background_worker_running():
                self.status.setText(f"Modell: {self.model.model}")

    def _start_learning(self, feedback: Feedback) -> None:
        if not self._latest_user_text or not self._latest_assistant_text:
            return
        if self._learning_worker is not None and self._learning_worker.isRunning():
            return

        self.more_button.setEnabled(False)
        self.less_button.setEnabled(False)
        self.status.setText("Persona wertet dein Feedback lokal aus …")
        worker = LearningWorker(
            self.learner,
            user_text=self._latest_user_text,
            assistant_text=self._latest_assistant_text,
            feedback=feedback,
            persona=self.persona,
            parent=self,
        )
        worker.completed.connect(self._learning_completed)
        worker.failed.connect(self._learning_failed)
        worker.finished.connect(self._learning_finished)
        self._learning_worker = worker
        worker.start()

    def _learning_completed(self, result: LearningResult) -> None:
        if self.settings.learning_snapshots:
            self.store.snapshot_persona(self.persona, kind="pre_learning")

        self.persona = result.persona
        self.store.save_persona(self.persona)
        self.store.record_learning_event(
            feedback=result.feedback,
            deltas=result.deltas,
            rationale=result.rationale,
        )

        if self.settings.learning_snapshots:
            self.store.snapshot_persona(self.persona, kind="learning")

        if self.on_persona_changed is not None:
            self.on_persona_changed(self.persona)
        changed = [
            f"{name} {signal:+.2f}"
            for name, signal in result.deltas.items()
            if abs(signal) >= 0.01
        ]
        summary = ", ".join(changed[:4]) if changed else "keine Trait-Änderung"
        self.learning_label.setText(f"Gelernt: {summary}")
        self.status.setText("Persona-Lernschritt gespeichert")

    def _learning_failed(self, error: str) -> None:
        self.learning_label.setText(f"Lernen fehlgeschlagen: {error}")

    def _learning_finished(self) -> None:
        worker = self._learning_worker
        self._learning_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._worker is None or not self._worker.isRunning():
            if not self._background_worker_running():
                self.status.setText(f"Modell: {self.model.model}")

    def clear_chat(self) -> None:
        answer = QMessageBox.question(
            self,
            "Chat leeren",
            "Nur den Chatverlauf löschen? Persona, Langzeit-Memory, Lernhistorie und Snapshots bleiben erhalten.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.store.clear_messages()
            self.transcript.clear()
            self._latest_user_text = ""
            self._latest_assistant_text = ""
            self.more_button.setEnabled(False)
            self.less_button.setEnabled(False)
