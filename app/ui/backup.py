from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.backup import BackupError, PENDING_RESTORE_DIR, create_backup
from app.backup_crypto import (
    create_encrypted_backup,
    is_encrypted_backup,
    stage_portable_restore,
)


class BackupWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        mode: str,
        path: str,
        *,
        include_media: bool = True,
        encrypted: bool = False,
        passphrase: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.path = path
        self.include_media = include_media
        self.encrypted = encrypted
        self.passphrase = passphrase

    def run(self) -> None:
        try:
            if self.mode == "export":
                if self.encrypted:
                    result = create_encrypted_backup(
                        self.path,
                        self.passphrase,
                        include_media=self.include_media,
                    )
                else:
                    result = create_backup(self.path, include_media=self.include_media)
            elif self.mode == "restore":
                result = stage_portable_restore(
                    self.path,
                    passphrase=self.passphrase or None,
                )
            else:
                raise BackupError(f"Unknown backup operation: {self.mode}")
        except Exception as exc:  # UI boundary: never crash the settings window
            self.failed.emit(str(exc))
            return
        finally:
            self.passphrase = ""
        self.completed.emit(result)


class BackupWidget(QWidget):
    """User-facing local export and non-destructive staged restore controls."""

    restore_staged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: BackupWorker | None = None

        intro = QLabel(
            "Backups bleiben lokal. Standardmäßig wird ein passwortgeschützter, authentifiziert "
            "verschlüsselter .laicb-Container erstellt; optional werden erzeugte Medien mitgenommen."
        )
        intro.setWordWrap(True)

        restore_note = QLabel(
            "Importe werden zunächst nur vorgemerkt. Erst beim nächsten App-Start wird der "
            "alte Datenbankstand automatisch als pre_restore-Backup gesichert und danach der "
            "importierte Stand aktiviert. Vorhandene Mediendateien werden nicht gelöscht."
        )
        restore_note.setWordWrap(True)

        self.include_media = QCheckBox("Lokale Medien aus der Historie ins Backup aufnehmen")
        self.include_media.setChecked(True)
        self.encrypt_backup = QCheckBox("Backup verschlüsseln (empfohlen)")
        self.encrypt_backup.setChecked(True)

        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("mindestens 8 Zeichen; wird nicht gespeichert")
        self.confirm_passphrase = QLineEdit()
        self.confirm_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_passphrase.setPlaceholderText("Backup-Passphrase wiederholen")

        encryption_form = QFormLayout()
        encryption_form.addRow("Backup-Passphrase", self.passphrase)
        encryption_form.addRow("Bestätigung", self.confirm_passphrase)

        crypto_note = QLabel(
            "Die Backup-Passphrase wird nicht gespeichert und ist unabhängig von der App-Sperre. "
            "Ohne sie kann ein verschlüsseltes Backup nicht wiederhergestellt werden."
        )
        crypto_note.setWordWrap(True)

        self.export_button = QPushButton("Backup exportieren …")
        self.import_button = QPushButton("Backup importieren …")
        self.discard_button = QPushButton("Vorgemerkten Import verwerfen")
        self.status = QLabel()
        self.status.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.discard_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.include_media)
        layout.addWidget(self.encrypt_backup)
        layout.addLayout(encryption_form)
        layout.addWidget(crypto_note)
        layout.addLayout(buttons)
        layout.addWidget(restore_note)
        layout.addWidget(self.status)
        layout.addStretch(1)

        self.encrypt_backup.toggled.connect(self._encryption_toggled)
        self.export_button.clicked.connect(self.export_backup)
        self.import_button.clicked.connect(self.import_backup)
        self.discard_button.clicked.connect(self.discard_pending_restore)
        self._encryption_toggled(True)
        self._refresh_pending_status()

    def _encryption_toggled(self, enabled: bool) -> None:
        self.passphrase.setEnabled(enabled)
        self.confirm_passphrase.setEnabled(enabled)
        if not enabled:
            self.passphrase.clear()
            self.confirm_passphrase.clear()

    def _refresh_pending_status(self) -> None:
        pending = PENDING_RESTORE_DIR / "restore.json"
        if pending.exists():
            self.status.setText(
                "Eine Wiederherstellung ist vorgemerkt und wird beim nächsten App-Start angewendet."
            )
            self.discard_button.setEnabled(True)
        else:
            self.status.setText("Keine Wiederherstellung vorgemerkt.")
            self.discard_button.setEnabled(False)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.export_button.setEnabled(not busy)
        self.import_button.setEnabled(not busy)
        self.include_media.setEnabled(not busy)
        self.encrypt_backup.setEnabled(not busy)
        self.passphrase.setEnabled(not busy and self.encrypt_backup.isChecked())
        self.confirm_passphrase.setEnabled(not busy and self.encrypt_backup.isChecked())
        self.discard_button.setEnabled(
            not busy and (PENDING_RESTORE_DIR / "restore.json").exists()
        )
        if text:
            self.status.setText(text)

    def export_backup(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        encrypted = self.encrypt_backup.isChecked()
        secret = ""
        if encrypted:
            secret = self.passphrase.text()
            if len(secret) < 8:
                QMessageBox.warning(
                    self,
                    "Backup-Verschlüsselung",
                    "Bitte eine Backup-Passphrase mit mindestens 8 Zeichen eingeben.",
                )
                return
            if secret != self.confirm_passphrase.text():
                QMessageBox.warning(
                    self,
                    "Backup-Verschlüsselung",
                    "Die beiden Backup-Passphrasen stimmen nicht überein.",
                )
                return

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = ".laicb" if encrypted else ".zip"
        default_name = f"local-ai-companion-{stamp}{suffix}"
        file_filter = (
            "Verschlüsseltes Companion-Backup (*.laicb)"
            if encrypted
            else "ZIP-Backup (*.zip)"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Lokales Backup speichern",
            default_name,
            file_filter,
        )
        if not path:
            return
        self.passphrase.clear()
        self.confirm_passphrase.clear()
        self._start_worker(
            "export",
            path,
            include_media=self.include_media.isChecked(),
            encrypted=encrypted,
            passphrase=secret,
            status=(
                "Erstelle und verschlüssele lokales Backup …"
                if encrypted
                else "Erstelle konsistentes lokales Backup …"
            ),
        )

    def import_backup(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Lokales Backup auswählen",
            "",
            "Companion-Backups (*.laicb *.zip);;Verschlüsselt (*.laicb);;ZIP-Backup (*.zip);;Alle Dateien (*)",
        )
        if not path:
            return

        secret = ""
        encrypted = is_encrypted_backup(path)
        if encrypted:
            secret, accepted = QInputDialog.getText(
                self,
                "Verschlüsseltes Backup",
                "Backup-Passphrase:",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return
            if not secret:
                QMessageBox.warning(
                    self,
                    "Verschlüsseltes Backup",
                    "Für dieses Backup ist eine Passphrase erforderlich.",
                )
                return

        answer = QMessageBox.question(
            self,
            "Backup vormerken",
            "Das Backup wird jetzt geprüft und für den nächsten App-Start vorgemerkt. "
            "Der aktuelle Datenbankstand wird beim Neustart automatisch separat gesichert. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_worker(
            "restore",
            path,
            encrypted=encrypted,
            passphrase=secret,
            status=(
                "Entschlüssele und prüfe Backup …"
                if encrypted
                else "Prüfe Backup und bereite nicht-destruktive Wiederherstellung vor …"
            ),
        )

    def discard_pending_restore(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if not PENDING_RESTORE_DIR.exists():
            self._refresh_pending_status()
            return
        answer = QMessageBox.question(
            self,
            "Vorgemerkten Import verwerfen",
            "Die vorgemerkte Wiederherstellung löschen? Der aktuell laufende App-Zustand bleibt unverändert.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(PENDING_RESTORE_DIR, ignore_errors=True)
        self._refresh_pending_status()

    def _start_worker(
        self,
        mode: str,
        path: str,
        *,
        include_media: bool = True,
        encrypted: bool = False,
        passphrase: str = "",
        status: str,
    ) -> None:
        self._set_busy(True, status)
        worker = BackupWorker(
            mode,
            path,
            include_media=include_media,
            encrypted=encrypted,
            passphrase=passphrase,
            parent=self,
        )
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        self._worker = worker
        worker.start()

    def _completed(self, result: object) -> None:
        worker = self._worker
        if worker is None:
            return
        if worker.mode == "export":
            label = "Verschlüsseltes Backup" if worker.encrypted else "Backup"
            self.status.setText(f"{label} gespeichert: {Path(str(result))}")
        else:
            self.status.setText(
                "Backup geprüft und vorgemerkt. Bitte die App neu starten, um den Stand zu aktivieren."
            )
            self.restore_staged.emit()
            QMessageBox.information(
                self,
                "Wiederherstellung vorgemerkt",
                "Beim nächsten App-Start wird zuerst der aktuelle Datenbankstand als pre_restore-Backup gesichert. "
                "Danach wird der importierte Stand aktiviert.",
            )

    def _failed(self, error: str) -> None:
        self.status.setText(f"Backup-Vorgang fehlgeschlagen: {error}")
        QMessageBox.warning(self, "Backup", error)

    def _finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_busy(False)
        if (
            not (PENDING_RESTORE_DIR / "restore.json").exists()
            and "Backup" not in self.status.text()
        ):
            self._refresh_pending_status()
