from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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

from app.media.continuity import CharacterProfile
from app.memory.store import StateStore


class CharacterStudio(QWidget):
    """User-controlled visual identity editor for recurring local characters."""

    profile_changed = Signal(str)

    def __init__(
        self,
        store: StateStore,
        *,
        key: str = "persona-main",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.profile: CharacterProfile | None = None

        self.key_edit = QLineEdit(key)
        self.key_edit.setPlaceholderText("persona-main")
        self.load_button = QPushButton("Profil laden")

        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key_edit, 1)
        key_layout.addWidget(self.load_button)

        self.seed_edit = QLineEdit()
        self.seed_edit.setReadOnly(True)
        self.new_seed_button = QPushButton("Neuen Seed erzeugen")
        self.new_seed_button.setToolTip(
            "Ändert die numerische Basis der Figur. Ein festes Referenzbild bleibt erhalten."
        )

        seed_row = QWidget()
        seed_layout = QHBoxLayout(seed_row)
        seed_layout.setContentsMargins(0, 0, 0, 0)
        seed_layout.addWidget(self.seed_edit, 1)
        seed_layout.addWidget(self.new_seed_button)

        self.appearance = QPlainTextEdit()
        self.appearance.setPlaceholderText(
            "Stabile visuelle Merkmale der klar erwachsenen Figur: Gesicht, Haare, Körperbau, wiederkehrende Accessoires, Stil …"
        )
        self.appearance.setMaximumHeight(150)

        self.revision = QLabel("–")
        self.reference = QLabel("Keine feste Referenz")
        self.reference.setWordWrap(True)
        self.stats = QLabel("Noch kein Profil geladen")
        self.stats.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Continuity-Key", key_row)
        form.addRow("Seed", seed_row)
        form.addRow("Visuelle Identität", self.appearance)
        form.addRow("Identitäts-Revision", self.revision)
        form.addRow("Feste Referenz", self.reference)
        form.addRow("Historie", self.stats)

        self.note = QLabel(
            "Die Beschreibung ist ein harter, lokaler Identitätsanker für spätere Bild-Prompts. Die KI darf sie benutzen, aber nicht selbst überschreiben. Stil- und Szenenwünsche bleiben davon getrennt."
        )
        self.note.setWordWrap(True)

        self.save_button = QPushButton("Visuelle Identität speichern")
        self.refresh_button = QPushButton("Aktualisieren")
        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.note)
        layout.addStretch(1)
        layout.addLayout(buttons)

        self.load_button.clicked.connect(self.load_profile)
        self.refresh_button.clicked.connect(self.load_profile)
        self.save_button.clicked.connect(self.save_profile)
        self.new_seed_button.clicked.connect(self.rotate_seed)
        self.load_profile()

    def set_key(self, key: str) -> None:
        clean = key.strip() or "persona-main"
        if self.key_edit.text().strip() == clean and self.profile is not None:
            return
        self.key_edit.setText(clean)
        self.load_profile()

    def load_profile(self) -> None:
        key = self.key_edit.text().strip() or "persona-main"
        self.key_edit.setText(key)
        profile = self.store.load_character_profile(key)
        self.profile = profile
        self.seed_edit.setText(str(profile.seed))
        self.appearance.setPlainText(profile.appearance_prompt)
        self.revision.setText(str(profile.appearance_revision))

        if profile.reference_media_path:
            path = Path(profile.reference_media_path).expanduser()
            state = "vorhanden" if path.exists() else "Datei fehlt"
            self.reference.setText(
                f"#{profile.reference_media_id or '?'} · {path} · {state}"
            )
        else:
            self.reference.setText("Keine feste Referenz; positives Bild-Feedback kann als Fallback dienen.")

        self.stats.setText(
            f"Generierungen: {profile.generation_count} · "
            f"positives Bild-Feedback: {profile.positive_feedback} · "
            f"negatives Bild-Feedback: {profile.negative_feedback}"
        )

    def save_profile(self) -> None:
        if self.profile is None:
            self.load_profile()
        if self.profile is None:
            return
        try:
            changed = self.profile.set_appearance(self.appearance.toPlainText())
        except ValueError as exc:
            QMessageBox.warning(self, "Visuelle Identität", str(exc))
            return
        self.store.save_character_profile(self.profile)
        self.load_profile()
        if changed:
            self.profile_changed.emit(self.profile.key)

    def rotate_seed(self) -> None:
        if self.profile is None:
            self.load_profile()
        if self.profile is None:
            return
        answer = QMessageBox.question(
            self,
            "Neuen Character-Seed erzeugen",
            "Der Seed beeinflusst die visuelle Kontinuität zukünftiger Generierungen. Das feste Referenzbild und die Identitätsbeschreibung bleiben erhalten. Seed wirklich ändern?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.profile.rotate_seed()
        self.store.save_character_profile(self.profile)
        self.load_profile()
        self.profile_changed.emit(self.profile.key)
