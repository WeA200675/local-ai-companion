from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
import json
from typing import Any, Literal

import httpx

from app.ai.backend_health import classify_ollama_failure

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class LocalModelError(RuntimeError):
    """Raised when the local model backend cannot complete a request."""


class LocalModelTimeoutError(LocalModelError):
    """Raised when local inference stays silent longer than the read timeout."""


class OllamaClient:
    """Small synchronous adapter for an Ollama-compatible local HTTP API.

    The desktop UI calls this client from worker threads. Normal structured
    helper calls remain non-streaming, while interactive chat can consume
    ``chat_stream`` incrementally and cooperatively cancel an in-flight reply.

    Local inference can legitimately take much longer than an ordinary HTTP
    request, especially after a cold model load or when running CPU-only. The
    default read timeout therefore allows ten minutes of inactivity while the
    connection timeout stays short. ``keep_alive`` asks Ollama to keep the model
    resident for a finite period so repeated replies avoid unnecessary reloads.
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 600.0,
        client: httpx.Client | None = None,
        *,
        connect_timeout: float = 10.0,
        keep_alive: str | int = "20m",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.connect_timeout = float(connect_timeout)
        self.keep_alive = keep_alive
        self._owns_client = client is None
        if client is None:
            request_timeout = httpx.Timeout(
                connect=self.connect_timeout,
                read=self.timeout,
                write=min(self.timeout, 60.0),
                pool=min(self.connect_timeout, 10.0),
            )
            self._client = httpx.Client(timeout=request_timeout)
        else:
            self._client = client

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

    def list_models(self) -> list[str]:
        """Return installed model names reported by an Ollama-compatible backend."""

        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            failure = classify_ollama_failure(exc, model_name=self.model)
            raise LocalModelError(f"Could not list local models: {failure.message()}") from exc
        except ValueError as exc:
            raise LocalModelError(f"Could not list local models: invalid JSON response: {exc}") from exc

        if not isinstance(data, dict):
            raise LocalModelError("Local model list returned an invalid response")
        models = data.get("models")
        if not isinstance(models, list):
            raise LocalModelError("Local model list is missing the models array")

        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name") or item.get("model")
            if isinstance(raw_name, str) and raw_name.strip():
                names.append(raw_name.strip())
        return sorted(set(names), key=str.casefold)

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

    @staticmethod
    def _chat_options(
        temperature: float,
        *,
        num_ctx: int | None = None,
        num_predict: int | None = None,
    ) -> dict[str, float | int]:
        options: dict[str, float | int] = {"temperature": temperature}
        if num_ctx is not None and num_ctx > 0:
            options["num_ctx"] = num_ctx
        if num_predict is not None and num_predict > 0:
            options["num_predict"] = num_predict
        return options

    def _base_payload(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        stream: bool,
        temperature: float,
        num_ctx: int | None = None,
        num_predict: int | None = None,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": self._wire_messages(messages, system_prompt),
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": self._chat_options(
                temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
            ),
        }

    def _timeout_error(self) -> LocalModelTimeoutError:
        seconds = int(self.timeout) if self.timeout.is_integer() else self.timeout
        return LocalModelTimeoutError(
            "[TIMEOUT] Das lokale Modell hat zu lange keine Daten geliefert "
            f"(Inaktivitätslimit {seconds} s). Ollama kann weiterhin laufen; "
            "das Modell lädt möglicherweise noch oder rechnet auf CPU/GPU sehr langsam. "
            "Prüfe `ollama ps`, reduziere bei Bedarf Kontext/Antwortlimit oder verwende ein kleineres Modell."
        )

    def _model_http_error(self, exc: httpx.HTTPError) -> LocalModelError:
        failure = classify_ollama_failure(
            exc,
            model_name=self.model,
            timeout_seconds=self.timeout,
        )
        return LocalModelError(failure.message())

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise self._timeout_error() from exc
        except httpx.HTTPError as exc:
            raise self._model_http_error(exc) from exc
        except ValueError as exc:
            raise LocalModelError(f"Local model returned invalid response JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LocalModelError("Local model returned an invalid response")
        error = data.get("error")
        if isinstance(error, str) and error.strip():
            raise LocalModelError(f"Ollama meldete einen Inferenzfehler: {error.strip()}")
        return data

    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
        num_ctx: int | None = None,
        num_predict: int | None = None,
    ) -> str:
        payload = self._base_payload(
            messages,
            system_prompt=system_prompt,
            stream=False,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
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
        num_ctx: int | None = None,
        num_predict: int | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[str]:
        """Yield an interactive reply as Ollama NDJSON chunks arrive."""

        payload = self._base_payload(
            messages,
            system_prompt=system_prompt,
            stream=True,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
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
        except httpx.TimeoutException as exc:
            raise self._timeout_error() from exc
        except httpx.HTTPError as exc:
            raise self._model_http_error(exc) from exc

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

        payload = self._base_payload(
            messages,
            system_prompt=system_prompt,
            stream=False,
            temperature=temperature,
        )
        payload["format"] = "json"
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
