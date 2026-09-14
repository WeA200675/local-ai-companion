import httpx
import pytest

from app.ai.model import LocalModelError, OllamaClient


def test_list_models_returns_sorted_unique_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen2.5:7b"},
                    {"model": "llama3.2:latest"},
                    {"name": "Qwen2.5:7b"},
                    {"name": ""},
                    {"other": "ignored"},
                ]
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OllamaClient(model="unused", base_url="http://local", client=http_client)

    assert client.list_models() == ["llama3.2:latest", "qwen2.5:7b", "Qwen2.5:7b"]
    http_client.close()


def test_list_models_rejects_invalid_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OllamaClient(model="unused", base_url="http://local", client=http_client)

    with pytest.raises(LocalModelError):
        client.list_models()

    http_client.close()
