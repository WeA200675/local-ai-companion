from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from app.media.service import MediaService
from app.media.test_center import build_media_test_report


class MediaTestCenterWidget(QWidget):
    """Read-only local diagnostics for the complete configured media route."""

    def __init__(self, service: MediaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service

        title = QLabel("Medien-Testzentrum")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        explanation = QLabel(
            "Prüft lokal Workflow-Katalog, Routing, Motion-Evidenz, Referenzen und "
            "steuerbare Renderwerte. Ein echter Render kann im Chat über "
            "„Medium jetzt erzeugen“ gestartet werden."
        )
        explanation.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.refresh_button = QPushButton("Prüfung aktualisieren")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(self.output, 1)
        layout.addWidget(self.refresh_button)
        self.refresh()

    def set_service(self, service: MediaService) -> None:
        self._service = service
        self.refresh()

    def refresh(self) -> None:
        self.output.setPlainText(build_media_test_report(self._service).render_text())
