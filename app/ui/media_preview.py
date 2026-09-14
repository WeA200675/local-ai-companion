from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget


class MediaPreview(QWidget):
    """Inline preview for locally generated images, GIFs, and short videos."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._movie: QMovie | None = None

        self.caption = QLabel("Noch kein generiertes Medium")
        self.caption.setWordWrap(True)

        self.image = QLabel()
        self.image.setMinimumHeight(180)
        self.image.setScaledContents(False)
        self.image.setAlignment(self.image.alignment())

        self.video = QVideoWidget()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.0)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.image)
        self.stack.addWidget(self.video)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.caption)
        layout.addWidget(self.stack)

    def show_media(self, path: str | Path, *, description: str = "") -> None:
        media_path = Path(path)
        self.player.stop()
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

        suffix = media_path.suffix.lower()
        self.caption.setText(description or media_path.name)

        if suffix == ".gif":
            movie = QMovie(str(media_path))
            self._movie = movie
            self.image.setMovie(movie)
            self.stack.setCurrentWidget(self.image)
            movie.start()
            return

        if suffix in {".mp4", ".webm", ".mov", ".mkv"}:
            self.stack.setCurrentWidget(self.video)
            self.player.setSource(QUrl.fromLocalFile(str(media_path.resolve())))
            self.player.setLoops(QMediaPlayer.Loops.Infinite)
            self.player.play()
            return

        pixmap = QPixmap(str(media_path))
        if pixmap.isNull():
            self.caption.setText(f"Medium gespeichert: {media_path}")
            self.image.clear()
            self.stack.setCurrentWidget(self.image)
            return

        self.image.setPixmap(pixmap.scaledToWidth(520))
        self.stack.setCurrentWidget(self.image)
