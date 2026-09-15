import json

import httpx
import pytest

from app.ai.model import ChatMessage, LocalModelTimeoutError, OllamaClient


def test_ollama_chat_builds_expected_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"message": {"content": "hello"}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OllamaClient(model="test-model", base_url="http://local", client=http_client)

    reply = client.chat(
        [ChatMessage(role="user", content="Hi")],
        system_prompt="System",
        temperature=0.4,
    )

    assert reply == "hello"
    assert captured["model"] == "test-model"
    assert captured["stream"] is False
    assert captured["keep_alive"] == "20m"
    assert captured["options"] == {"temperature": 0.4}
    assert captured["messages"] == [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Hi"},
    ]

    http_client.close()


def test_ollama_chat_stream_yields_chunks_and_applies_tuning_options() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        body = (
            b'{"message":{"content":"Hel"},"done":false}\n'
            b'{"message":{"content":"lo"},"done":false}\n'
            b'{"message":{"content":"!"},"done":true}\n'
        )
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OllamaClient(model="stream-model", base_url="http://local", client=http_client)

    chunks = list(
        client.chat_stream(
            [ChatMessage(role="user", content="Hi")],
            system_prompt="System",
            temperature=0.7,
            num_ctx=16384,
            num_predict=700,
        )
    )

    assert chunks == ["Hel", "lo", "!"]
    assert "".join(chunks) == "Hello!"
    assert captured["model"] == "stream-model"
    assert captured["stream"] is True
    assert captured["keep_alive"] == "20m"
    assert captured["options"] == {
        "temperature": 0.7,
        "num_ctx": 16384,
        "num_predict": 700,
    }

    http_client.close()


def test_ollama_chat_omits_zero_or_missing_optional_tuning_values() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OllamaClient(model="test-model", base_url="http://local", client=http_client)

    client.chat(
        [ChatMessage(role="user", content="Hi")],
        system_prompt="System",
        num_ctx=0,
        num_predict=None,
    )

    assert captured["options"] == {"temperature": 0.85}
    http_client.close()


def test_ollama_chat_stream_stops_cooperatively() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        body = (
            b'{"message":{"content":"one"},"done":false}\n'
            b'{"message":{"content":" two"},"done":false}\n'
            b'{"message":{"content":" three"},"done":true}\n'
        )
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OllamaClient(model="stream-model", base_url="http://local", client=http_client)
    received: list[str] = []

    def should_stop() -> bool:
        return len(received) >= 1

    for chunk in client.chat_stream(
        [ChatMessage(role="user", content="Hi")],
        system_prompt="System",
        should_stop=should_stop,
    ):
        received.append(chunk)

    assert received == ["one"]

    http_client.close()


def test_ollama_chat_stream_classifies_read_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OllamaClient(
        model="slow-model",
        base_url="http://local",
        client=http_client,
        timeout=321.0,
    )

    with pytest.raises(LocalModelTimeoutError) as exc_info:
        list(
            client.chat_stream(
                [ChatMessage(role="user", content="Hi")],
                system_prompt="System",
            )
        )

    message = str(exc_info.value)
    assert message.startswith("[TIMEOUT]")
    assert "321" in message
    assert "ollama ps" in message
    http_client.close()


def test_keep_alive_can_be_overridden() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OllamaClient(
        model="test-model",
        base_url="http://local",
        client=http_client,
        keep_alive=0,
    )
    client.chat(
        [ChatMessage(role="user", content="Hi")],
        system_prompt="System",
    )

    assert captured["keep_alive"] == 0
    http_client.close()
