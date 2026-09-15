from __future__ import annotations

import json

import httpx
import pytest

from app.ai.model import ChatMessage, LocalModelError, LocalModelTimeoutError
from app.ai.model_fallback import FallbackOllamaClient


def _model_from_request(request: httpx.Request) -> str:
    return str(json.loads(request.content.decode())["model"])


def _chat_ok(request: httpx.Request, text: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={"message": {"role": "assistant", "content": text}, "done": True},
    )


def test_backend_crash_promotes_first_working_fallback() -> None:
    calls: list[str] = []
    switched: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = _model_from_request(request)
        calls.append(model)
        if model == "primary:7b":
            return httpx.Response(
                500,
                request=request,
                json={"error": "llama-server process has terminated"},
            )
        return _chat_ok(request, "Fallback antwortet")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = FallbackOllamaClient(
            model="primary:7b",
            client=http_client,
            reconnect_attempts=0,
            fallback_models=["backup:4b"],
            fallback_callback=lambda old, new: switched.append((old, new)),
        )
        reply = client.chat(
            [ChatMessage(role="user", content="Hallo")],
            system_prompt="test",
        )

    assert reply == "Fallback antwortet"
    assert calls == ["primary:7b", "backup:4b"]
    assert client.model == "backup:4b"
    assert switched == [("primary:7b", "backup:4b")]


def test_fallback_chain_skips_broken_candidate_and_uses_next() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = _model_from_request(request)
        calls.append(model)
        if model == "primary:7b":
            return httpx.Response(500, request=request, json={"error": "llama-server process has terminated"})
        if model == "missing:4b":
            return httpx.Response(404, request=request, json={"error": "model not found"})
        return _chat_ok(request, "Zweiter Fallback")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = FallbackOllamaClient(
            model="primary:7b",
            client=http_client,
            reconnect_attempts=0,
            fallback_models=["missing:4b", "backup:8b"],
        )
        reply = client.chat(
            [ChatMessage(role="user", content="Hallo")],
            system_prompt="test",
        )

    assert reply == "Zweiter Fallback"
    assert calls == ["primary:7b", "missing:4b", "backup:8b"]
    assert client.model == "backup:8b"


def test_timeout_never_switches_model() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(_model_from_request(request))
        raise httpx.ReadTimeout("too slow", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = FallbackOllamaClient(
            model="primary:7b",
            client=http_client,
            reconnect_attempts=0,
            fallback_models=["backup:4b"],
        )
        with pytest.raises(LocalModelTimeoutError):
            client.chat(
                [ChatMessage(role="user", content="Hallo")],
                system_prompt="test",
            )

    assert calls == ["primary:7b"]
    assert client.model == "primary:7b"


def test_stream_never_switches_after_partial_output() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = _model_from_request(request)
        calls.append(model)
        body = (
            json.dumps({"message": {"content": "Teil"}, "done": False})
            + "\n"
            + json.dumps({"error": "llama-server process has terminated"})
            + "\n"
        ).encode()
        return httpx.Response(200, request=request, content=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = FallbackOllamaClient(
            model="primary:7b",
            client=http_client,
            reconnect_attempts=0,
            fallback_models=["backup:4b"],
        )
        stream = client.chat_stream(
            [ChatMessage(role="user", content="Hallo")],
            system_prompt="test",
        )
        assert next(stream) == "Teil"
        with pytest.raises(LocalModelError):
            list(stream)

    assert calls == ["primary:7b"]
    assert client.model == "primary:7b"


def test_duplicate_primary_and_fallback_names_are_removed() -> None:
    client = FallbackOllamaClient(
        model="qwen3:8b",
        fallback_models=["QWEN3:8B", "backup:4b", "backup:4b", ""],
        reconnect_attempts=0,
    )
    try:
        assert client.fallback_models == ("backup:4b",)
    finally:
        client.close()
