from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import httpx

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class LocalModelError(RuntimeError):
    """Raised when the local model backend cannot complete a request."""


class OllamaClient:
    """Small synchronous adapter for an Ollama-compatible local HTTP API.

    The UI calls this client from a worker thread, so keeping the adapter
    synchronous makes it easy to test and replace later.
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def is_available(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
    ) -> str:
        wire_messages = [{"role": "system", "content": system_prompt}]
        wire_messages.extend(
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role != "system"
        )
        payload = {
            "model": self.model,
            "messages": wire_messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        try:
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocalModelError(f"Local model request failed: {exc}") from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("Local model returned an empty or invalid response")
        return content.strip()
