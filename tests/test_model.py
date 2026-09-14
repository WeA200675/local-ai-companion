import json

import httpx

from app.ai.model import ChatMessage, OllamaClient


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
    assert captured["options"]["temperature"] == 0.4
    assert captured["messages"] == [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Hi"},
    ]

    http_client.close()


def test_ollama_chat_stream_yields_chunks_and_uses_streaming_payload() -> None:
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
        )
    )

    assert chunks == ["Hel", "lo", "!"]
    assert "".join(chunks) == "Hello!"
    assert captured["model"] == "stream-model"
    assert captured["stream"] is True
    assert captured["options"]["temperature"] == 0.7

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
