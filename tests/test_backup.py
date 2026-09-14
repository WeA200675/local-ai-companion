from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

import pytest

from app.backup import (
    BackupError,
    create_backup,
    apply_pending_restore,
    stage_restore,
    validate_backup,
)
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _chat_contents(db_path: Path) -> list[str]:
    with sqlite3.connect(str(db_path)) as connection:
        rows = connection.execute("SELECT content FROM chat_messages ORDER BY id").fetchall()
    return [str(row[0]) for row in rows]


def test_backup_restore_preserves_previous_database_and_rewrites_media(tmp_path) -> None:
    db_path = tmp_path / "live.sqlite3"
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    image = media_dir / "anchor.png"
    image.write_bytes(b"reference-image")

    factory = make_session_factory(db_path)
    store = StateStore(factory)
    store.save_settings(AppSettings(media_output_dir=str(media_dir)))
    store.append_message("user", "before backup")
    media_id = store.record_media_event(
        path=str(image),
        kind="png",
        prompt_id="prompt-1",
        seed=123,
        continuity_key="persona-main",
        intent={"mood": "confident"},
    )
    profile = store.load_character_profile("persona-main")
    profile.set_reference(media_id, str(image))
    profile.register_generation(str(image))
    store.save_character_profile(profile)

    archive_path = create_backup(tmp_path / "portable-backup", db_path=db_path)
    manifest = validate_backup(archive_path)
    assert manifest["format"] == "local-ai-companion-backup"
    assert len(manifest["media"]) == 1

    with ZipFile(archive_path) as archive:
        assert "database/companion.sqlite3" in archive.namelist()
        assert f"media/{media_id}.png" in archive.namelist()

    store.append_message("user", "after backup")
    factory.kw["bind"].dispose()

    pending_dir = tmp_path / "pending"
    restored_media_dir = tmp_path / "restored-media"
    marker = stage_restore(
        archive_path,
        pending_dir=pending_dir,
        media_target_dir=restored_media_dir,
    )
    staged_db = Path(str(marker["database"]))
    assert _chat_contents(staged_db) == ["before backup"]

    with sqlite3.connect(str(staged_db)) as connection:
        media_path = connection.execute(
            "SELECT path FROM media_events WHERE id=?", (media_id,)
        ).fetchone()[0]
        settings_payload = json.loads(
            connection.execute(
                "SELECT value_json FROM app_state WHERE key='runtime_settings'"
            ).fetchone()[0]
        )
        profile_payload = json.loads(
            connection.execute(
                "SELECT value_json FROM app_state WHERE key='character:persona-main'"
            ).fetchone()[0]
        )

    assert Path(media_path).parent == restored_media_dir
    assert settings_payload["media_output_dir"] == str(restored_media_dir)
    assert profile_payload["reference_media_path"] == media_path
    assert profile_payload["last_media_path"] == media_path

    previous = apply_pending_restore(
        db_path=db_path,
        pending_dir=pending_dir,
        backup_dir=tmp_path / "pre-restore-backups",
    )
    assert previous is not None and previous.exists()
    assert _chat_contents(previous) == ["before backup", "after backup"]
    assert _chat_contents(db_path) == ["before backup"]
    assert Path(media_path).read_bytes() == b"reference-image"
    assert not pending_dir.exists()


def test_backup_can_exclude_media(tmp_path) -> None:
    db_path = tmp_path / "live.sqlite3"
    factory = make_session_factory(db_path)
    store = StateStore(factory)
    store.append_message("user", "hello")

    archive_path = create_backup(
        tmp_path / "state-only.zip",
        db_path=db_path,
        include_media=False,
    )
    manifest = validate_backup(archive_path)
    assert manifest["media"] == []


def test_invalid_backup_is_rejected(tmp_path) -> None:
    invalid = tmp_path / "invalid.zip"
    invalid.write_text("not a zip", encoding="utf-8")

    with pytest.raises(BackupError):
        validate_backup(invalid)
    with pytest.raises(BackupError):
        stage_restore(invalid, pending_dir=tmp_path / "pending")
