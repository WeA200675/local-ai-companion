from __future__ import annotations

import httpx

from app.ai.backend_health import classify_ollama_failure


def _status_error(status: int, body: dict[str, str]) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
    response = httpx.Response(status, request=request, json=body)
    return httpx.HTTPStatusError("failed", request=request, response=response)


def test_windows_access_violation_is_classified_as_native_backend_crash() -> None:
    failure = classify_ollama_failure(
        _status_error(
            500,
            {
                "error": (
                    "llama-server process has terminated: exit status 0xc0000005: "
                    "The memory could not be read"
                )
            },
        ),
        model_name="qwen2.5:7b",
    )

    assert failure.code == "native_backend_crash"
    assert "Ersatzmodell suchen" in failure.next_step
    assert "RAM/VRAM" in failure.next_step


def test_generic_server_error_keeps_backend_failure_classification() -> None:
    failure = classify_ollama_failure(
        _status_error(500, {"error": "unexpected backend error"}),
        model_name="qwen3:4b",
    )

    assert failure.code == "backend_failure"
