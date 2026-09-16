from __future__ import annotations

import httpx
import pytest

from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.voice import LocalVoiceClient, VoiceConfig, VoiceConfigRepository, VoiceError


def test_voice_config_rejects_remote_endpoint() -> None:
    with pytest.raises(ValueError, match="local"):
        VoiceConfig(base_url="https://example.com")


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8880", "http://localhost:8880", "http://[::1]:8880"],
)
def test_voice_config_accepts_loopback(url: str) -> None:
    assert VoiceConfig(base_url=url).base_url == url


def test_voice_config_round_trip(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "voice.sqlite3"))
    repository = VoiceConfigRepository(store)
    repository.save(
        VoiceConfig(
            enabled=True,
            base_url="http://localhost:9999",
            model="local-tts",
            voice="companion",
            speed=1.15,
            output_dir=str(tmp_path / "voice"),
        )
    )
    loaded = repository.load()
    assert loaded.enabled is True
    assert loaded.model == "local-tts"
    assert loaded.voice == "companion"
    assert loaded.speed == 1.15


def test_local_voice_sends_openai_compatible_payload_and_saves_wav(tmp_path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, content=b"RIFF-local-audio")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    config = VoiceConfig(
        enabled=True,
        model="tts-model",
        voice="voice-a",
        speed=0.9,
        output_dir=str(tmp_path / "audio"),
    )
    client = LocalVoiceClient(config, client=http)
    path = client.synthesize("  Hallo   dort.  ")

    assert seen["path"] == "/v1/audio/speech"
    assert seen["json"] == {
        "model": "tts-model",
        "input": "Hallo dort.",
        "voice": "voice-a",
        "response_format": "wav",
        "speed": 0.9,
    }
    assert path.suffix == ".wav"
    assert path.read_bytes() == b"RIFF-local-audio"


def test_local_voice_requires_enabled_config(tmp_path) -> None:
    client = LocalVoiceClient(VoiceConfig(output_dir=str(tmp_path)))
    with pytest.raises(VoiceError, match="deaktiviert"):
        client.synthesize("Hallo")
    client.close()
