from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.media.service import MediaService
from app.settings import AppSettings


def _service(*, backend_enabled: bool) -> MediaService:
    service = object.__new__(MediaService)
    service.backend = SimpleNamespace(enabled=backend_enabled)
    service.settings = AppSettings(media_enabled=True)
    service.workflow_profiles = []
    service.workflow_capabilities = {}
    return service


def test_legacy_backend_exposes_image_for_manual_generation() -> None:
    assert _service(backend_enabled=True).available_media_kinds == ("image",)


def test_disabled_backend_exposes_no_manual_media_kind() -> None:
    assert _service(backend_enabled=False).available_media_kinds == ()


def test_explicit_intent_bypasses_planner_in_generation_path() -> None:
    source = Path("app/media/service.py").read_text(encoding="utf-8")
    chat_source = Path("app/ui/chat.py").read_text(encoding="utf-8")

    assert "intent = forced_intent or self.plan(" in source
    assert 'QPushButton("🎨 Medium jetzt erzeugen")' in chat_source
    assert "forced_intent=forced_intent" in chat_source
