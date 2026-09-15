from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
import json
import time
from typing import Any, Literal, TypeVar

import httpx

from app.ai.backend_health import classify_ollama_failure

Role = Literal["user", "assistant", "system"]
RetryCallback = Callable[[int, int, str], None]
T = TypeVar("T")

_RETRYABLE_FAILURE_CODES = {"unreachable", "backend_failure", "transport_error"}
_RETRYABLE_ERROR_MARKERS = (
    "llama-server process has terminated",
    "inferenz-backend",
    "backend ist mit http 5",
    "endpoint ist nicht erreichbar",
    "verbindung zu ollama",
    "connection refused",
    "connection reset",
    "server disconnected",
)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class LocalModelError(RuntimeError):
    """Raised when the local model backend cannot complete a request."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "unknown",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LocalModelTimeoutError(LocalModelError):
    """Raised when local inference stays silent longer than the read timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="timeout", retryable=False)


class OllamaClient:
    """Small synchronous adapter for an Ollama-compatible local HTTP API.

    Interactive chat is streamed from worker threads; helper calls are normally
    non-streaming. Transient local Ollama transport/backend failures are retried
    automatically. The default policy performs three reconnect attempts after
    the initial failed request. Timeouts, missing models and ordinary 4xx errors
    are not retried automatically.

    A streaming request is retried only before the first response token arrives.
    Once partial text has reached the UI, replaying the request could duplicate or
    splice text, so an interruption is surfaced instead of silently restarting.
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
        reconnect_attempts: int = 3,
        reconnect_backoff_seconds: float | None = None,
        retry_callback: RetryCallback | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.connect_timeout = float(connect_timeout)
        self.keep_alive = keep_alive
        self.reconnect_attempts = max(0, int(reconnect_attempts))
        self.retry_callback = retry_callback
        self._owns_client = client is None
        if reconnect_backoff_seconds is None:
            # Injected clients are primarily used by deterministic tests and local
            # probes; do not make those sleep between mocked retries.
            reconnect_backoff_seconds = 0.75 if self._owns_client else 0.0
        self.reconnect_backoff_seconds = max(0.0, float(reconnect_backoff_seconds))
        self._client = client if client is not None else self._new_http_client()

    def _new_http_client(self) -> httpx.Client:
        request_timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.timeout,
            write=min(self.timeout, 60.0),
            pool=min(self.connect_timeout, 10.0),
        )
        return httpx.Client(timeout=request_timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _reset_owned_connection(self) -> None:
        """Drop pooled sockets before a retry so a restarted Ollama is contacted fresh."""

        if not self._owns_client:
            return
        try:
            self._client.close()
        finally:
            self._client = self._new_http_client()

    def _retry_delay(self, retry_number: int) -> float:
        if self.reconnect_backoff_seconds <= 0:
            return 0.0
        # Short exponential backoff: 0.75s, 1.5s, 3s with the default policy.
        return min(5.0, self.reconnect_backoff_seconds * (2 ** max(0, retry_number - 1)))

    @staticmethod
    def _should_retry_error(error: LocalModelError) -> bool:
        if isinstance(error, LocalModelTimeoutError):
            return False
        if error.retryable:
            return True
        folded = str(error).casefold()
        return any(marker in folded for marker in _RETRYABLE_ERROR_MARKERS)

    def _notify_retry(
        self,
        retry_number: int,
        error: LocalModelError,
        callback: RetryCallback | None = None,
    ) -> None:
        target = callback or self.retry_callback
        if target is not None:
            target(retry_number, self.reconnect_attempts, str(error))

    def _wait_before_retry(
        self,
        retry_number: int,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> bool:
        delay = self._retry_delay(retry_number)
        if delay <= 0:
            return not (should_stop is not None and should_stop())
        deadline = time.monotonic() + delay
        while True:
            if should_stop is not None and should_stop():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.1, remaining))

    def _retry_exhausted_error(self, error: LocalModelError) -> LocalModelError:
        return LocalModelError(
            f"{error} Automatische Ollama-Wiederverbindung blieb nach "
            f"{self.reconnect_attempts} Neuverbindungsversuch(en) erfolglos.",
            code=error.code,
            retryable=error.retryable,
        )

    def _run_with_reconnects(
        self,
        operation: Callable[[], T],
        *,
        retry_callback: RetryCallback | None = None,
    ) -> T:
        retries_used = 0
        while True:
            try:
                return operation()
            except LocalModelError as exc:
                if not self._should_retry_error(exc):
                    raise
                if retries_used >= self.reconnect_attempts:
                    raise self._retry_exhausted_error(exc) from exc
                retries_used += 1
                self._notify_retry(retries_used, exc, retry_callback)
                self._reset_owned_connection()
                self._wait_before_retry(retries_used)

    def is_available(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        """Return installed model names reported by an Ollama-compatible backend."""

        def request() -> list[str]:
            try:
                response = self._client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
            except httpx.TimeoutException as exc:
                raise self._timeout_error() from exc
            except httpx.HTTPError as exc:
                failure = classify_ollama_failure(exc, model_name=self.model)
                raise LocalModelError(
                    f"Could not list local models: {failure.message()}",
                    code=failure.code,
                    retryable=failure.code in _RETRYABLE_FAILURE_CODES,
                ) from exc
            except ValueError as exc:
                raise LocalModelError(
                    f"Could not list local models: invalid JSON response: {exc}"
                ) from exc

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

        return self._run_with_reconnects(request)

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
        return LocalModelError(
            failure.message(),
            code=failure.code,
            retryable=failure.code in _RETRYABLE_FAILURE_CODES,
        )

    @staticmethod
    def _inference_error(message: str) -> LocalModelError:
        clean = " ".join(message.split())
        folded = clean.casefold()
        retryable = any(marker in folded for marker in _RETRYABLE_ERROR_MARKERS)
        return LocalModelError(
            f"Ollama meldete einen Inferenzfehler: {clean}",
            code="backend_failure" if retryable else "inference_error",
            retryable=retryable,
        )

    def _post_chat_once(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            raise self._inference_error(error)
        return data

    def _post_chat(
        self,
        payload: dict[str, Any],
        *,
        retry_callback: RetryCallback | None = None,
    ) -> dict[str, Any]:
        return self._run_with_reconnects(
            lambda: self._post_chat_once(payload),
            retry_callback=retry_callback,
        )

    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        retry_callback: RetryCallback | None = None,
    ) -> str:
        payload = self._base_payload(
            messages,
            system_prompt=system_prompt,
            stream=False,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
        data = self._post_chat(payload, retry_callback=retry_callback)
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("Local model returned an empty or invalid response")
        return content.strip()

    def _chat_stream_once(
        self,
        payload: dict[str, Any],
        *,
        should_stop: Callable[[], bool] | None,
    ) -> Iterator[str]:
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
                        raise self._inference_error(error)
                    message = data.get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    if isinstance(content, str) and content:
                        yield content
                    if data.get("done") is True:
                        break
        except LocalModelError:
            raise
        except httpx.TimeoutException as exc:
            raise self._timeout_error() from exc
        except httpx.HTTPError as exc:
            raise self._model_http_error(exc) from exc

    def chat_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        should_stop: Callable[[], bool] | None = None,
        retry_callback: RetryCallback | None = None,
    ) -> Iterator[str]:
        """Yield an interactive reply as Ollama NDJSON chunks arrive.

        Transient Ollama failures are retried up to ``reconnect_attempts`` times,
        but only while no response token has been emitted yet.
        """

        payload = self._base_payload(
            messages,
            system_prompt=system_prompt,
            stream=True,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
        retries_used = 0
        emitted = False

        while True:
            try:
                for chunk in self._chat_stream_once(payload, should_stop=should_stop):
                    emitted = True
                    yield chunk
                break
            except LocalModelError as exc:
                if emitted or not self._should_retry_error(exc):
                    raise
                if retries_used >= self.reconnect_attempts:
                    raise self._retry_exhausted_error(exc) from exc
                retries_used += 1
                self._notify_retry(retries_used, exc, retry_callback)
                self._reset_owned_connection()
                if not self._wait_before_retry(
                    retries_used,
                    should_stop=should_stop,
                ):
                    return

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
        retry_callback: RetryCallback | None = None,
    ) -> dict[str, Any]:
        """Request a JSON object from an Ollama-compatible backend."""

        payload = self._base_payload(
            messages,
            system_prompt=system_prompt,
            stream=False,
            temperature=temperature,
        )
        payload["format"] = "json"
        data = self._post_chat(payload, retry_callback=retry_callback)
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
