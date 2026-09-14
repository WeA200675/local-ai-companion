from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from app.backup import BackupError, apply_pending_restore
from app.backup_crypto import (
    create_encrypted_backup,
    is_encrypted_backup,
    stage_portable_restore,
    validate_portable_backup,
)
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _chat_contents(db_path: Path) -> list[str]:
    with sqlite3.connect(str(db_path)) as connection:
        rows = connection.execute("SELECT content FROM chat_messages ORDER BY id").fetchall()
    return [str(row[0]) for row in rows]


def test_encrypted_backup_round_trip(tmp_path) -> None:
    db_path = tmp_path / "live.sqlite3"
    factory = make_session_factory(db_path)
    store = StateStore(factory)
    store.append_message("user", "encrypted hello")

    encrypted = create_encrypted_backup(
        tmp_path / "private-copy",
        "correct horse battery staple",
        db_path=db_path,
        include_media=False,
    )

    assert encrypted.suffix == ".laicb"
    assert encrypted.exists()
    assert is_encrypted_backup(encrypted)
    assert not encrypted.read_bytes().startswith(b"PK")

    manifest = validate_portable_backup(encrypted, "correct horse battery staple")
    assert manifest["format"] == "local-ai-companion-backup"

    pending = tmp_path / "pending"
    marker = stage_portable_restore(
        encrypted,
        passphrase="correct horse battery staple",
        pending_dir=pending,
        media_target_dir=tmp_path / "restored-media",
    )
    staged = Path(str(marker["database"]))
    assert _chat_contents(staged) == ["encrypted hello"]

    store.append_message("user", "new live state")
    factory.kw["bind"].dispose()
    previous = apply_pending_restore(
        db_path=db_path,
        pending_dir=pending,
        backup_dir=tmp_path / "pre-restore",
    )
    assert previous is not None
    assert _chat_contents(previous) == ["encrypted hello", "new live state"]
    assert _chat_contents(db_path) == ["encrypted hello"]


def test_wrong_passphrase_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "live.sqlite3"
    factory = make_session_factory(db_path)
    StateStore(factory).append_message("user", "secret")

    encrypted = create_encrypted_backup(
        tmp_path / "private.laicb",
        "right-passphrase",
        db_path=db_path,
        include_media=False,
    )

    with pytest.raises(BackupError, match="Passphrase|beschädigtes"):
        validate_portable_backup(encrypted, "wrong-passphrase")


def test_tampered_encrypted_backup_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "live.sqlite3"
    factory = make_session_factory(db_path)
    StateStore(factory).append_message("user", "secret")

    encrypted = create_encrypted_backup(
        tmp_path / "private.laicb",
        "right-passphrase",
        db_path=db_path,
        include_media=False,
    )
    data = bytearray(encrypted.read_bytes())
    data[-1] ^= 0x01
    encrypted.write_bytes(bytes(data))

    with pytest.raises(BackupError, match="Passphrase|beschädigtes"):
        validate_portable_backup(encrypted, "right-passphrase")


def test_short_backup_passphrase_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "live.sqlite3"
    factory = make_session_factory(db_path)
    StateStore(factory).append_message("user", "secret")

    with pytest.raises(BackupError, match="mindestens 8"):
        create_encrypted_backup(
            tmp_path / "private.laicb",
            "short",
            db_path=db_path,
            include_media=False,
        )
