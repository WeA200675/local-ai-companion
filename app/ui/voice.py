from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.voice import LocalVoiceClient, VoiceConfig, VoiceConfigRepository


class VoiceWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, config: VoiceConfig, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config.model_copy(deep=True)
        self.text = text

    def run(self) -> None:
        client = LocalVoiceClient(self.config)
        try:
            path = client.synthesize(self.text)
        except Exception as exc:  # optional voice must never crash the desktop
            self.failed.emit(str(exc))
        else:
            self.completed.emit(str(path))
        finally:
            client.close()


class VoiceStudio(QWidget):
    """Optional local-only TTS surface for giving the companion a voice."""

    def __init__(self, store, chat_store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = VoiceConfigRepository(store)
        self.chat_store = chat_store
        self._worker: VoiceWorker | None = None
        config = self.repository.load()

        self.enabled = QCheckBox("Lokale Stimme aktivieren")
        self.enabled.setChecked(config.enabled)
        self.base_url = QLineEdit(config.base_url)
        self.model = QLineEdit(config.model)
        self.voice = QLineEdit(config.voice)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.5, 2.0)
        self.speed.setSingleStep(0.05)
        self.speed.setValue(config.speed)
        self.output_dir = QLineEdit(config.output_dir)

        form = QFormLayout()
        form.addRow("Stimme", self.enabled)
        form.addRow("Lokaler TTS-Endpunkt", self.base_url)
        form.addRow("TTS-Modell", self.model)
        form.addRow("Voice-ID", self.voice)
        form.addRow("Tempo", self.speed)
        form.addRow("Audio-Ausgabe", self.output_dir)

        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Text eingeben oder die letzte Companion-Antwort übernehmen …")
        self.text.setMaximumBlockCount(100)
        self.status = QLabel(
            "Nur localhost/Loopback ist erlaubt. Die App lädt keinen Sprachdienst und kein Stimmenmodell automatisch herunter."
        )
        self.status.setWordWrap(True)

        self.use_last = QPushButton("Letzte Antwort übernehmen")
        self.speak = QPushButton("Sprechen")
        self.save = QPushButton("Voice-Einstellungen speichern")
        actions = QHBoxLayout()
        actions.addWidget(self.use_last)
        actions.addWidget(self.speak)
        actions.addStretch(1)
        actions.addWidget(self.save)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Sprechtext"))
        layout.addWidget(self.text, 1)
        layout.addWidget(self.status)
        layout.addLayout(actions)

        self.use_last.clicked.connect(self._use_last_reply)
        self.speak.clicked.connect(self._speak)
        self.save.clicked.connect(self._save)

    def _config(self) -> VoiceConfig:
        return VoiceConfig(
            enabled=self.enabled.isChecked(),
            base_url=self.base_url.text(),
            model=self.model.text(),
            voice=self.voice.text(),
            speed=self.speed.value(),
            output_dir=self.output_dir.text(),
        )

    def _save(self) -> None:
        try:
            config = self._config()
        except ValueError as exc:
            QMessageBox.warning(self, "Voice Studio", str(exc))
            return
        self.repository.save(config)
        self.status.setText("Voice-Einstellungen lokal gespeichert.")

    def _use_last_reply(self) -> None:
        exchange = self.chat_store.latest_exchange()
        if exchange is None:
            self.status.setText("Noch keine vollständige Companion-Antwort vorhanden.")
            return
        self.text.setPlainText(exchange[1])

    def _speak(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            config = self._config()
        except ValueError as exc:
            QMessageBox.warning(self, "Voice Studio", str(exc))
            return
        self.repository.save(config)
        text = self.text.toPlainText().strip()
        if not text:
            self._use_last_reply()
            text = self.text.toPlainText().strip()
        if not text:
            return

        self.speak.setEnabled(False)
        self.status.setText("Lokale Sprachsynthese läuft …")
        worker = VoiceWorker(config, text, self)
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        self._worker = worker
        worker.start()

    def _completed(self, path: str) -> None:
        target = Path(path)
        self.status.setText(f"Audio lokal erzeugt: {target}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))

    def _failed(self, error: str) -> None:
        self.status.setText(f"Voice-Fehler: {error}")

    def _finished(self) -> None:
        self.speak.setEnabled(True)
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
