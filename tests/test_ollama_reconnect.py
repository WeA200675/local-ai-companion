from __future__ import annotations

import json

import httpx
import pytest

from app.ai.model import ChatMessage, LocalModelError, LocalModelTimeoutError, OllamaClient


def _chat_ok(text: str = "Hallo") -> httpx.Response:
    return httpx.Response(
        200,
        json={"message": {"role": "assistant", "content": text}, "done": True},
    )


def test_chat_reconnects_three_times_then_recovers() -> None:
    calls = 0
    retries: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 3:
            return httpx.Response(
                500,
                request=request,
                json={"error": "llama-server process has terminated"},
            )
        return _chat_ok("Wieder da")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = OllamaClient(
            client=http_client,
            reconnect_attempts=3,
            retry_callback=lambda attempt, maximum, _error: retries.append((attempt, maximum)),
        )
        reply = client.chat(
            [ChatMessage(role="user", content="Hallo")],
            system_prompt="test",
        )

    assert reply == "Wieder da"
    assert calls == 4  # initial request + three reconnect attempts
    assert retries == [(1, 3), (2, 3), (3, 3)]


def test_chat_reports_exhausted_reconnects_after_three_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            500,
            request=request,
            json={"error": "llama-server process has terminated"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient(client=http_client, reconnect_attempts=3)
        with pytest.raises(LocalModelError) as exc_info:
            client.chat(
                [ChatMessage(role="user", content="Hallo")],
                system_prompt="test",
            )

    assert calls == 4
    assert "3 Neuverbindungsversuch" in str(exc_info.value)


def test_timeout_is_not_automatically_replayed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("too slow", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient(client=http_client, reconnect_attempts=3)
        with pytest.raises(LocalModelTimeoutError):
            client.chat(
                [ChatMessage(role="user", content="Hallo")],
                system_prompt="test",
            )

    assert calls == 1


def test_missing_model_is_not_automatically_replayed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            404,
            request=request,
            json={"error": "model not found"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient(client=http_client, reconnect_attempts=3)
        with pytest.raises(LocalModelError):
            client.chat(
                [ChatMessage(role="user", content="Hallo")],
                system_prompt="test",
            )

    assert calls == 1


def test_stream_reconnects_only_before_first_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                500,
                request=request,
                json={"error": "llama-server process has terminated"},
            )
        body = (
            json.dumps({"message": {"content": "Hallo"}, "done": False})
            + "\n"
            + json.dumps({"done": True})
            + "\n"
        ).encode()
        return httpx.Response(200, request=request, content=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient(client=http_client, reconnect_attempts=3)
        chunks = list(
            client.chat_stream(
                [ChatMessage(role="user", content="Hallo")],
                system_prompt="test",
            )
        )

    assert chunks == ["Hallo"]
    assert calls == 2


def test_stream_does_not_replay_after_partial_output() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = (
            json.dumps({"message": {"content": "Teil"}, "done": False})
            + "\n"
            + json.dumps({"error": "llama-server process has terminated"})
            + "\n"
        ).encode()
        return httpx.Response(200, request=request, content=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient(client=http_client, reconnect_attempts=3)
        stream = client.chat_stream(
            [ChatMessage(role="user", content="Hallo")],
            system_prompt="test",
        )
        assert next(stream) == "Teil"
        with pytest.raises(LocalModelError):
            list(stream)

    assert calls == 1
