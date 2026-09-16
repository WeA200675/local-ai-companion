from __future__ import annotations

from pathlib import Path

import pytest

from app.media.comfyui_resilient import ResilientComfyUIClient, ResilientComfyUIError
from app.media.comfyui_runtime import (
    VisibleMediaBackendError,
    VisibleResilientComfyUIClient,
    classify_resilient_comfyui_error,
    present_resilient_comfyui_error,
)


@pytest.mark.parametrize(
    ("stage", "message", "category"),
    [
        ("prepare", "profile missing", "configuration"),
        ("reference_upload", "file unreadable", "reference"),
        ("queue", "connection refused", "unreachable"),
        ("history", "HTTP 503", "unreachable"),
        ("execution", "Node 3: CUDA out of memory", "resources"),
        ("execution", "Node 8: missing custom node", "workflow"),
        ("output download", "HTTP 404", "output"),
        ("timeout", "render timed out", "timeout"),
    ],
)
def test_classifies_media_failures(stage: str, message: str, category: str) -> None:
    error = ResilientComfyUIError(message, stage=stage, prompt_id="prompt-1")

    presentation = classify_resilient_comfyui_error(error)
    visible = present_resilient_comfyui_error(error)

    assert presentation.category == category
    assert f"[COMFYUI/{category} · Prompt-ID prompt-1]" in visible
    assert message in visible
    assert presentation.action in visible


def test_visible_runtime_crosses_optional_media_skip_boundary(monkeypatch) -> None:
    error = ResilientComfyUIError(
        "ComfyUI execution failed: Node 3: CUDA out of memory",
        stage="execution",
        prompt_id="oom-1",
    )

    def fail_generate(self, *args, **kwargs):
        raise error

    monkeypatch.setattr(ResilientComfyUIClient, "generate", fail_generate)
    client = VisibleResilientComfyUIClient()

    with pytest.raises(VisibleMediaBackendError) as exc_info:
        client.generate("positive", "negative")

    assert exc_info.value.stage == "execution"
    assert exc_info.value.prompt_id == "oom-1"
    assert "VRAM/RAM" in str(exc_info.value)
    assert exc_info.value.__cause__ is error
    client.close()


def test_desktop_runtime_uses_visible_resilient_client() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")

    assert "media_backend = VisibleResilientComfyUIClient(" in source


@pytest.mark.parametrize(
    ("stage", "retry_safe"),
    [
        ("prepare", True),
        ("reference_upload", True),
        ("history", True),
        ("execution", True),
        ("output download", True),
        ("timeout", True),
        ("queue", False),
    ],
)
def test_visible_failure_marks_only_ambiguous_queue_as_unsafe(
    stage: str, retry_safe: bool
) -> None:
    error = VisibleMediaBackendError("failed", stage=stage)

    assert error.retry_safe is retry_safe


def test_chat_retry_is_limited_to_explicit_media_requests() -> None:
    source = Path("app/ui/chat.py").read_text(encoding="utf-8")

    assert "exc.retry_safe and self._forced_intent is not None" in source
    assert "self._last_manual_media_request" in source
    assert "Render wiederholen" in source
