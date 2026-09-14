from __future__ import annotations

from contextlib import contextmanager
import base64
import json
import os
from pathlib import Path
import struct
import tempfile
from typing import Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.backup import BackupError, create_backup, stage_restore, validate_backup

MAGIC = b"LAICB1\x00"
HEADER_LIMIT = 16 * 1024
DEFAULT_SCRYPT_N = 2**15
DEFAULT_SCRYPT_R = 8
DEFAULT_SCRYPT_P = 1
KEY_LENGTH = 32


def _require_passphrase(passphrase: str) -> bytes:
    if len(passphrase) < 8:
        raise BackupError("Backup-Passphrase muss mindestens 8 Zeichen lang sein")
    return passphrase.encode("utf-8")


def _derive_key(passphrase: bytes, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    try:
        return Scrypt(salt=salt, length=KEY_LENGTH, n=n, r=r, p=p).derive(passphrase)
    except (TypeError, ValueError) as exc:
        raise BackupError(f"Ungültige Verschlüsselungsparameter: {exc}") from exc


def is_encrypted_backup(path: str | Path) -> bool:
    source = Path(path).expanduser()
    try:
        with source.open("rb") as handle:
            return handle.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def encrypt_backup_file(
    source_zip: str | Path,
    destination: str | Path,
    passphrase: str,
) -> Path:
    source = Path(source_zip).expanduser()
    if not source.exists() or not source.is_file():
        raise BackupError(f"Backup archive does not exist: {source}")
    secret = _require_passphrase(passphrase)
    target = Path(destination).expanduser()
    if target.suffix.lower() != ".laicb":
        target = target.with_suffix(".laicb")
    target.parent.mkdir(parents=True, exist_ok=True)

    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = {
        "format": "local-ai-companion-encrypted-backup",
        "version": 1,
        "cipher": "AES-256-GCM",
        "kdf": "scrypt",
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "n": DEFAULT_SCRYPT_N,
        "r": DEFAULT_SCRYPT_R,
        "p": DEFAULT_SCRYPT_P,
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    associated_data = MAGIC + header_bytes
    key = _derive_key(
        secret,
        salt,
        n=DEFAULT_SCRYPT_N,
        r=DEFAULT_SCRYPT_R,
        p=DEFAULT_SCRYPT_P,
    )
    try:
        plaintext = source.read_bytes()
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data)
    except OSError as exc:
        raise BackupError(f"Could not read backup archive: {exc}") from exc

    temp_target = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        with temp_target.open("wb") as handle:
            handle.write(MAGIC)
            handle.write(struct.pack(">I", len(header_bytes)))
            handle.write(header_bytes)
            handle.write(ciphertext)
        os.replace(temp_target, target)
    except OSError as exc:
        try:
            temp_target.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupError(f"Could not write encrypted backup: {exc}") from exc
    return target


def create_encrypted_backup(
    destination: str | Path,
    passphrase: str,
    *,
    db_path: str | Path = Path("data/companion.sqlite3"),
    include_media: bool = True,
) -> Path:
    """Create a portable backup and encrypt it as one authenticated local container."""

    with tempfile.TemporaryDirectory(prefix="companion-encrypted-backup-") as temp_dir:
        plain = create_backup(
            Path(temp_dir) / "payload.zip",
            db_path=db_path,
            include_media=include_media,
        )
        return encrypt_backup_file(plain, destination, passphrase)


def _read_encrypted_payload(path: Path, passphrase: str) -> bytes:
    secret = _require_passphrase(passphrase)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BackupError(f"Could not open encrypted backup: {exc}") from exc
    if not raw.startswith(MAGIC):
        raise BackupError("Selected file is not an encrypted Local AI Companion backup")
    offset = len(MAGIC)
    if len(raw) < offset + 4:
        raise BackupError("Encrypted backup header is truncated")
    header_length = struct.unpack(">I", raw[offset : offset + 4])[0]
    offset += 4
    if header_length <= 0 or header_length > HEADER_LIMIT or len(raw) < offset + header_length:
        raise BackupError("Encrypted backup header is invalid")
    header_bytes = raw[offset : offset + header_length]
    ciphertext = raw[offset + header_length :]
    if not ciphertext:
        raise BackupError("Encrypted backup contains no payload")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
        if not isinstance(header, dict):
            raise BackupError("Encrypted backup header is invalid")
        if header.get("format") != "local-ai-companion-encrypted-backup":
            raise BackupError("Unsupported encrypted backup format")
        if int(header.get("version", 0)) != 1:
            raise BackupError("Unsupported encrypted backup version")
        if header.get("cipher") != "AES-256-GCM" or header.get("kdf") != "scrypt":
            raise BackupError("Unsupported encrypted backup cryptography")
        salt = base64.b64decode(str(header["salt"]), validate=True)
        nonce = base64.b64decode(str(header["nonce"]), validate=True)
        n = int(header["n"])
        r = int(header["r"])
        p = int(header["p"])
    except BackupError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BackupError(f"Encrypted backup header is invalid: {exc}") from exc
    if len(salt) < 16 or len(nonce) != 12:
        raise BackupError("Encrypted backup cryptographic parameters are invalid")
    if n < 2**14 or n > 2**20 or r < 1 or r > 32 or p < 1 or p > 16:
        raise BackupError("Encrypted backup KDF parameters are outside safe limits")

    key = _derive_key(secret, salt, n=n, r=r, p=p)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, MAGIC + header_bytes)
    except InvalidTag as exc:
        raise BackupError("Falsche Backup-Passphrase oder beschädigtes verschlüsseltes Backup") from exc


@contextmanager
def decrypted_backup(path: str | Path, passphrase: str) -> Iterator[Path]:
    source = Path(path).expanduser()
    payload = _read_encrypted_payload(source, passphrase)
    with tempfile.TemporaryDirectory(prefix="companion-decrypted-backup-") as temp_dir:
        target = Path(temp_dir) / "payload.zip"
        try:
            target.write_bytes(payload)
        except OSError as exc:
            raise BackupError(f"Could not prepare decrypted backup: {exc}") from exc
        yield target


def validate_portable_backup(
    path: str | Path,
    passphrase: str | None = None,
) -> dict[str, object]:
    source = Path(path).expanduser()
    if not is_encrypted_backup(source):
        return validate_backup(source)
    if not passphrase:
        raise BackupError("Dieses Backup ist verschlüsselt; eine Passphrase ist erforderlich")
    with decrypted_backup(source, passphrase) as plain:
        return validate_backup(plain)


def stage_portable_restore(
    path: str | Path,
    *,
    passphrase: str | None = None,
    pending_dir: str | Path = Path("data/.restore_pending"),
    media_target_dir: str | Path = Path("data/generated_media"),
) -> dict[str, object]:
    source = Path(path).expanduser()
    if not is_encrypted_backup(source):
        return stage_restore(
            source,
            pending_dir=pending_dir,
            media_target_dir=media_target_dir,
        )
    if not passphrase:
        raise BackupError("Dieses Backup ist verschlüsselt; eine Passphrase ist erforderlich")
    with decrypted_backup(source, passphrase) as plain:
        return stage_restore(
            plain,
            pending_dir=pending_dir,
            media_target_dir=media_target_dir,
        )
