from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
import json
from typing import Any, Literal

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

    The desktop UI calls this client from worker threads. Normal structured
    helper calls remain non-streaming, while interactive chat can consume
    ``chat_stream`` incrementally and cooperatively cancel an in-flight reply.
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

    def _wire_messages(
        self,
        messages: Iterable[ChatMessage],
        system_prompt: str,
    ) -> list[dict[str, str]]:
        wire_messages = [{"role": "system", "content": system_prompt}]
        wire_messages.extend(
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role != "system"
        )
        return wire_messages

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocalModelError(f"Local model request failed: {exc}") from exc
        if not isinstance(data, dict):
            raise LocalModelError("Local model returned an invalid response")
        return data

    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": self._wire_messages(messages, system_prompt),
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self._post_chat(payload)
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("Local model returned an empty or invalid response")
        return content.strip()

    def chat_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[str]:
        """Yield an interactive reply as Ollama NDJSON chunks arrive.

        Cancellation is cooperative: callers provide ``should_stop`` and this
        method exits as soon as the next stream chunk is observed. No partial
        response is discarded by the adapter; the caller decides whether to
        persist already emitted text.
        """

        payload = {
            "model": self.model,
            "messages": self._wire_messages(messages, system_prompt),
            "stream": True,
            "options": {"temperature": temperature},
        }
        emitted = False
        try:
            with self._client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if should_stop is not None and should_stop():
                        return
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except ValueError as exc:
                        raise LocalModelError(
                            f"Local model returned invalid stream JSON: {exc}"
                        ) from exc
                    if not isinstance(data, dict):
                        raise LocalModelError("Local model returned an invalid stream chunk")
                    error = data.get("error")
                    if isinstance(error, str) and error.strip():
                        raise LocalModelError(f"Local model stream failed: {error.strip()}")
                    message = data.get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    if isinstance(content, str) and content:
                        emitted = True
                        yield content
                    if data.get("done") is True:
                        break
        except LocalModelError:
            raise
        except httpx.HTTPError as exc:
            raise LocalModelError(f"Local model streaming request failed: {exc}") from exc

        if should_stop is not None and should_stop():
            return
        if not emitted:
            raise LocalModelError("Local model returned an empty streaming response")

    def chat_json(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.25,
    ) -> dict[str, Any]:
        """Request a JSON object from an Ollama-compatible backend."""

        payload = {
            "model": self.model,
            "messages": self._wire_messages(messages, system_prompt),
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        data = self._post_chat(payload)
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("Local model returned empty JSON content")
        try:
            parsed = json.loads(content)
        except ValueError as exc:
            raise LocalModelError(f"Local model returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LocalModelError("Local model JSON response was not an object")
        return parsed
