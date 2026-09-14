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
