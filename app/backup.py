from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import uuid
from zipfile import ZIP_DEFLATED, ZipFile

from app import __version__

BACKUP_FORMAT = "local-ai-companion-backup"
BACKUP_VERSION = 1
DEFAULT_DB_PATH = Path("data/companion.sqlite3")
DEFAULT_MEDIA_DIR = Path("data/generated_media")
DEFAULT_BACKUP_DIR = Path("data/backups")
PENDING_RESTORE_DIR = Path("data/.restore_pending")
MANIFEST_NAME = "manifest.json"
DATABASE_MEMBER = "database/companion.sqlite3"


class BackupError(RuntimeError):
    """Raised when a local backup cannot be created, validated, or staged."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sqlite_backup(source: Path, destination: Path) -> None:
    if not source.exists() or not source.is_file():
        raise BackupError(f"Database does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(destination)) as dst:
            src.backup(dst)
    except sqlite3.Error as exc:
        raise BackupError(f"Could not snapshot SQLite database: {exc}") from exc


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _configured_media_roots(connection: sqlite3.Connection) -> list[Path]:
    roots = [DEFAULT_MEDIA_DIR.resolve()]
    if not _table_exists(connection, "app_state"):
        return roots
    row = connection.execute(
        "SELECT value_json FROM app_state WHERE key='runtime_settings' LIMIT 1"
    ).fetchone()
    if not row:
        return roots
    try:
        payload = json.loads(str(row[0]))
    except ValueError:
        return roots
    if not isinstance(payload, dict):
        return roots
    value = str(payload.get("media_output_dir") or "").strip()
    if value:
        try:
            candidate = Path(value).expanduser().resolve()
        except OSError:
            candidate = None
        if candidate is not None and candidate not in roots:
            roots.append(candidate)
    return roots


def _path_in_roots(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    return any(resolved.is_relative_to(root) for root in roots)


def _safe_member_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise BackupError(f"Unsafe path in backup archive: {name!r}")
    return path.as_posix()


def _read_manifest(archive: ZipFile) -> dict[str, object]:
    names = set(archive.namelist())
    if MANIFEST_NAME not in names:
        raise BackupError("Backup archive has no manifest.json")
    for name in names:
        _safe_member_name(name)
    try:
        raw = archive.read(MANIFEST_NAME)
        payload = json.loads(raw.decode("utf-8"))
    except (KeyError, UnicodeDecodeError, ValueError) as exc:
        raise BackupError(f"Could not read backup manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise BackupError("Backup manifest must be a JSON object")
    if payload.get("format") != BACKUP_FORMAT:
        raise BackupError("This is not a Local AI Companion backup")
    if payload.get("version") != BACKUP_VERSION:
        raise BackupError(f"Unsupported backup version: {payload.get('version')!r}")
    if DATABASE_MEMBER not in names:
        raise BackupError("Backup archive has no SQLite database snapshot")
    return payload


def create_backup(
    destination: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    include_media: bool = True,
) -> Path:
    """Create a consistent portable ZIP without mutating the live database."""

    source_db = Path(db_path)
    target = Path(destination).expanduser()
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)

    backup_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()

    with tempfile.TemporaryDirectory(prefix="companion-backup-") as temp_dir:
        snapshot = Path(temp_dir) / "companion.sqlite3"
        _sqlite_backup(source_db, snapshot)

        media_entries: list[dict[str, object]] = []
        files_to_add: list[tuple[Path, str]] = []
        if include_media:
            try:
                with sqlite3.connect(str(snapshot)) as connection:
                    roots = _configured_media_roots(connection)
                    if _table_exists(connection, "media_events"):
                        rows = connection.execute(
                            "SELECT id, path FROM media_events ORDER BY id"
                        ).fetchall()
                        for event_id, path_value in rows:
                            path = Path(str(path_value or "")).expanduser()
                            if (
                                not path.exists()
                                or not path.is_file()
                                or path.is_symlink()
                                or not _path_in_roots(path, roots)
                            ):
                                continue
                            suffix = path.suffix.lower()
                            archive_name = f"media/{int(event_id)}{suffix}"
                            files_to_add.append((path, archive_name))
                            media_entries.append(
                                {
                                    "event_id": int(event_id),
                                    "archive": archive_name,
                                    "original_path": str(path),
                                    "basename": path.name,
                                }
                            )
            except sqlite3.Error as exc:
                raise BackupError(f"Could not inspect media history: {exc}") from exc

        manifest = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "backup_id": backup_id,
            "created_at": created_at,
            "app_version": __version__,
            "database": DATABASE_MEMBER,
            "media": media_entries,
        }

        try:
            with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
                archive.write(snapshot, DATABASE_MEMBER)
                for path, archive_name in files_to_add:
                    archive.write(path, archive_name)
        except OSError as exc:
            raise BackupError(f"Could not write backup archive: {exc}") from exc

    return target


def validate_backup(path: str | Path) -> dict[str, object]:
    archive_path = Path(path).expanduser()
    if not archive_path.exists() or not archive_path.is_file():
        raise BackupError(f"Backup archive does not exist: {archive_path}")
    try:
        with ZipFile(archive_path, "r") as archive:
            return _read_manifest(archive)
    except OSError as exc:
        raise BackupError(f"Could not open backup archive: {exc}") from exc


def _patch_staged_database(
    database: Path,
    media_paths: dict[int, tuple[str, str]],
) -> None:
    """Rewrite restored media pointers to safe portable local destinations."""

    try:
        with sqlite3.connect(str(database)) as connection:
            if _table_exists(connection, "media_events"):
                for event_id, (_original, final_path) in media_paths.items():
                    connection.execute(
                        "UPDATE media_events SET path=? WHERE id=?",
                        (final_path, event_id),
                    )

            if _table_exists(connection, "app_state"):
                row = connection.execute(
                    "SELECT value_json FROM app_state WHERE key='runtime_settings' LIMIT 1"
                ).fetchone()
                if row and media_paths:
                    try:
                        settings = json.loads(str(row[0]))
                    except ValueError:
                        settings = None
                    if isinstance(settings, dict):
                        settings["media_output_dir"] = str(DEFAULT_MEDIA_DIR)
                        connection.execute(
                            "UPDATE app_state SET value_json=? WHERE key='runtime_settings'",
                            (json.dumps(settings, ensure_ascii=False),),
                        )

                character_rows = connection.execute(
                    "SELECT key, value_json FROM app_state WHERE key LIKE 'character:%'"
                ).fetchall()
                by_original = {
                    original: final_path for original, final_path in media_paths.values()
                }
                for key, value_json in character_rows:
                    try:
                        profile = json.loads(str(value_json))
                    except ValueError:
                        continue
                    if not isinstance(profile, dict):
                        continue
                    changed = False
                    reference_id = profile.get("reference_media_id")
                    if isinstance(reference_id, int) and reference_id in media_paths:
                        profile["reference_media_path"] = media_paths[reference_id][1]
                        changed = True
                    last_path = profile.get("last_media_path")
                    if isinstance(last_path, str) and last_path in by_original:
                        profile["last_media_path"] = by_original[last_path]
                        changed = True
                    if changed:
                        connection.execute(
                            "UPDATE app_state SET value_json=? WHERE key=?",
                            (json.dumps(profile, ensure_ascii=False), key),
                        )
            connection.commit()
    except sqlite3.Error as exc:
        raise BackupError(f"Could not prepare restored database: {exc}") from exc


def stage_restore(
    archive_path: str | Path,
    *,
    pending_dir: str | Path = PENDING_RESTORE_DIR,
) -> dict[str, object]:
    """Validate and stage a restore. The live database is not touched."""

    source = Path(archive_path).expanduser()
    pending = Path(pending_dir)
    if pending.exists():
        shutil.rmtree(pending)
    pending.mkdir(parents=True, exist_ok=True)

    try:
        with ZipFile(source, "r") as archive:
            manifest = _read_manifest(archive)
            backup_id = str(manifest.get("backup_id") or uuid.uuid4().hex[:12])
            database_target = pending / "companion.sqlite3"
            with archive.open(DATABASE_MEMBER) as src, database_target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

            media_dir = pending / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            media_paths: dict[int, tuple[str, str]] = {}
            pending_media: list[dict[str, str]] = []
            entries = manifest.get("media")
            if isinstance(entries, list):
                archive_names = set(archive.namelist())
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        event_id = int(entry["event_id"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    member = _safe_member_name(str(entry.get("archive") or ""))
                    if member not in archive_names:
                        continue
                    suffix = Path(member).suffix.lower()
                    final_name = f"restored_{backup_id}_{event_id}{suffix}"
                    pending_file = media_dir / final_name
                    with archive.open(member) as src, pending_file.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    final_path = DEFAULT_MEDIA_DIR / final_name
                    original_path = str(entry.get("original_path") or "")
                    media_paths[event_id] = (original_path, str(final_path))
                    pending_media.append(
                        {"pending": str(pending_file), "final": str(final_path)}
                    )

            _patch_staged_database(database_target, media_paths)
            marker = {
                "format": BACKUP_FORMAT,
                "version": BACKUP_VERSION,
                "backup_id": backup_id,
                "staged_at": datetime.now(timezone.utc).isoformat(),
                "database": str(database_target),
                "media": pending_media,
            }
            (pending / "restore.json").write_text(
                json.dumps(marker, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return marker
    except BackupError:
        shutil.rmtree(pending, ignore_errors=True)
        raise
    except (OSError, KeyError, ValueError) as exc:
        shutil.rmtree(pending, ignore_errors=True)
        raise BackupError(f"Could not stage restore: {exc}") from exc


def apply_pending_restore(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    pending_dir: str | Path = PENDING_RESTORE_DIR,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
) -> Path | None:
    """Apply a staged restore before SQLAlchemy opens the live database.

    The previous SQLite state is first copied with SQLite's backup API. Existing
    generated media are never deleted or overwritten.
    """

    pending = Path(pending_dir)
    marker_path = pending / "restore.json"
    if not marker_path.exists():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError(f"Could not read staged restore marker: {exc}") from exc
    if not isinstance(marker, dict) or marker.get("format") != BACKUP_FORMAT:
        raise BackupError("Invalid staged restore marker")

    pending_db = Path(str(marker.get("database") or ""))
    if not pending_db.exists() or not pending_db.is_file():
        raise BackupError("Staged restore database is missing")

    live_db = Path(db_path)
    live_db.parent.mkdir(parents=True, exist_ok=True)
    previous_backup: Path | None = None
    if live_db.exists():
        previous_backup = Path(backup_dir) / f"pre_restore_{_timestamp()}.sqlite3"
        _sqlite_backup(live_db, previous_backup)

    media_entries = marker.get("media")
    if isinstance(media_entries, list):
        for entry in media_entries:
            if not isinstance(entry, dict):
                continue
            source = Path(str(entry.get("pending") or ""))
            target = Path(str(entry.get("final") or ""))
            if not source.exists() or not source.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                continue
            shutil.move(str(source), str(target))

    try:
        os.replace(pending_db, live_db)
        for suffix in ("-wal", "-shm"):
            stale = Path(f"{live_db}{suffix}")
            if stale.exists():
                stale.unlink()
    except OSError as exc:
        raise BackupError(f"Could not replace live database: {exc}") from exc

    shutil.rmtree(pending, ignore_errors=True)
    return previous_backup
