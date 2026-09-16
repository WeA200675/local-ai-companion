from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class VoiceError(RuntimeError):
    """Raised when the optional local voice backend cannot synthesize speech."""


class VoiceConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8880"
    model: str = "kokoro"
    voice: str = "af_bella"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    output_dir: str = "data/generated_voice"

    @field_validator("base_url", "model", "voice", "output_dir", mode="before")
    @classmethod
    def _strip(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("base_url")
    @classmethod
    def _local_endpoint_only(cls, value: str) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or host not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("voice endpoint must be local (localhost/loopback)")
        return value.rstrip("/")

    @field_validator("model", "voice", "output_dir")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be blank")
        return value

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser()


class VoiceConfigRepository:
    KEY = "voice_config"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> VoiceConfig:
        payload = self.store._load_app_state(self.KEY)  # noqa: SLF001
        if not payload:
            return VoiceConfig()
        try:
            return VoiceConfig.model_validate_json(payload)
        except ValueError:
            return VoiceConfig()

    def save(self, config: VoiceConfig) -> None:
        self.store._save_app_state(self.KEY, config.model_dump_json())  # noqa: SLF001


class LocalVoiceClient:
    """Minimal OpenAI-compatible TTS adapter restricted to loopback endpoints."""

    def __init__(
        self,
        config: VoiceConfig,
        *,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config.model_copy(deep=True)
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def synthesize(self, text: str) -> Path:
        clean = " ".join(text.split())
        if not clean:
            raise VoiceError("Kein Text zum Sprechen vorhanden.")
        if not self.config.enabled:
            raise VoiceError("Lokale Stimme ist deaktiviert.")

        try:
            response = self._client.post(
                f"{self.config.base_url}/v1/audio/speech",
                json={
                    "model": self.config.model,
                    "input": clean,
                    "voice": self.config.voice,
                    "response_format": "wav",
                    "speed": self.config.speed,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise VoiceError(f"Lokaler Sprachdienst nicht erreichbar: {exc}") from exc
        if not response.content:
            raise VoiceError("Lokaler Sprachdienst hat keine Audiodaten geliefert.")

        output = self.config.output_path
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = output / f"voice_{stamp}.wav"
        temporary = target.with_suffix(".tmp")
        try:
            temporary.write_bytes(response.content)
            temporary.replace(target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise VoiceError(f"Audiodatei konnte nicht gespeichert werden: {exc}") from exc
        return target
