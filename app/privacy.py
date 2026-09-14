from __future__ import annotations

import base64
from hashlib import pbkdf2_hmac
import hmac
import os

from pydantic import BaseModel, Field

from app.memory.store import StateStore

_STATE_KEY = "privacy_lock_v1"
_DEFAULT_ITERATIONS = 310_000


class PrivacyConfig(BaseModel):
    """Local privacy-lock configuration. The passphrase itself is never stored."""

    enabled: bool = False
    salt_b64: str = ""
    digest_b64: str = ""
    iterations: int = Field(default=_DEFAULT_ITERATIONS, ge=100_000, le=2_000_000)
    auto_lock_minutes: int = Field(default=0, ge=0, le=720)

    @property
    def has_passphrase(self) -> bool:
        return bool(self.salt_b64 and self.digest_b64)

    def set_passphrase(self, passphrase: str) -> None:
        clean = passphrase.strip()
        if len(clean) < 6:
            raise ValueError("Die lokale Sperre braucht mindestens 6 Zeichen.")
        salt = os.urandom(16)
        digest = pbkdf2_hmac(
            "sha256",
            clean.encode("utf-8"),
            salt,
            self.iterations,
            dklen=32,
        )
        self.salt_b64 = base64.b64encode(salt).decode("ascii")
        self.digest_b64 = base64.b64encode(digest).decode("ascii")
        self.enabled = True

    def verify(self, passphrase: str) -> bool:
        if not self.has_passphrase:
            return False
        try:
            salt = base64.b64decode(self.salt_b64, validate=True)
            expected = base64.b64decode(self.digest_b64, validate=True)
        except ValueError:
            return False
        actual = pbkdf2_hmac(
            "sha256",
            passphrase.strip().encode("utf-8"),
            salt,
            self.iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)

    def clear_passphrase(self) -> None:
        self.enabled = False
        self.salt_b64 = ""
        self.digest_b64 = ""
        self.auto_lock_minutes = 0


class PrivacyStore:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> PrivacyConfig:
        payload = self.store._load_app_state(_STATE_KEY)
        if payload is None:
            return PrivacyConfig()
        try:
            config = PrivacyConfig.model_validate_json(payload)
        except ValueError:
            return PrivacyConfig()
        if config.enabled and not config.has_passphrase:
            config.enabled = False
        return config

    def save(self, config: PrivacyConfig) -> None:
        self.store._save_app_state(_STATE_KEY, config.model_dump_json())
