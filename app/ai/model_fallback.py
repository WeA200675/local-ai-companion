from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any

from app.ai.model import ChatMessage, LocalModelError, OllamaClient

FallbackCallback = Callable[[str, str], None]


class FallbackOllamaClient(OllamaClient):
    """Ollama client with an explicit, ordered local model fallback chain.

    The ordinary Ollama reconnect policy still runs first. A fallback model is
    attempted only after a model-specific backend failure (for example a local
    llama-server crash) remains after those reconnect attempts. Endpoint-wide
    connection failures, long inference timeouts, missing primary models and
    ordinary 4xx responses do not trigger a model switch.

    Fallback is safe for streaming: another model is only tried before the first
    response token has been emitted. Once partial text exists, the interruption
    is surfaced rather than replayed with a different model.
    """

    def __init__(
        self,
        *args: Any,
        fallback_models: Sequence[str] | None = None,
        fallback_callback: FallbackCallback | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.primary_model = self.model
        seen = {self.primary_model.casefold()}
        cleaned: list[str] = []
        for raw in fallback_models or ():
            name = str(raw or "").strip()
            folded = name.casefold()
            if not name or folded in seen:
                continue
            seen.add(folded)
            cleaned.append(name)
        self.fallback_models = tuple(cleaned)
        self.fallback_callback = fallback_callback

    @staticmethod
    def _can_start_fallback(error: LocalModelError) -> bool:
        # A different model can help when the model runner/backend itself crashes.
        # It cannot repair an unreachable Ollama endpoint, a missing primary model
        # or a request that simply exceeded the inference timeout.
        return error.code == "backend_failure"

    @staticmethod
    def _candidate_failure_stops_chain(error: LocalModelError) -> bool:
        # Once the shared Ollama endpoint itself is offline/transport-broken, trying
        # additional models cannot help. A timeout also stops the chain to avoid
        # multiplying a long local inference wait by every fallback candidate.
        return error.code in {"unreachable", "transport_error", "timeout"}

    def _remaining_fallbacks(self) -> tuple[str, ...]:
        chain = (self.primary_model, *self.fallback_models)
        current = self.model.casefold()
        try:
            index = next(i for i, name in enumerate(chain) if name.casefold() == current)
        except StopIteration:
            index = 0
        return tuple(chain[index + 1 :])

    def _notify_fallback(self, previous: str, selected: str) -> None:
        if self.fallback_callback is not None:
            self.fallback_callback(previous, selected)

    @staticmethod
    def _fallback_exhausted(
        initial_error: LocalModelError,
        attempted: list[tuple[str, str]],
    ) -> LocalModelError:
        detail = "; ".join(f"{name}: {message}" for name, message in attempted)
        suffix = f" Fallback-Versuche: {detail}." if detail else ""
        return LocalModelError(
            f"{initial_error} Die konfigurierte lokale Modell-Rueckfallkette war ebenfalls erfolglos.{suffix}",
            code=initial_error.code,
            retryable=False,
        )

    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        retry_callback=None,
    ) -> str:
        message_list = list(messages)
        trigger_error: LocalModelError | None = None
        try:
            return super().chat(
                message_list,
                system_prompt=system_prompt,
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
                retry_callback=retry_callback,
            )
        except LocalModelError as exc:
            if not self._can_start_fallback(exc):
                raise
            trigger_error = exc

        attempted: list[tuple[str, str]] = []
        failed_model = self.model
        for candidate in self._remaining_fallbacks():
            previous = self.model
            self.model = candidate
            try:
                reply = super().chat(
                    message_list,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    num_ctx=num_ctx,
                    num_predict=num_predict,
                    retry_callback=retry_callback,
                )
            except LocalModelError as exc:
                attempted.append((candidate, str(exc)))
                if self._candidate_failure_stops_chain(exc):
                    break
                continue
            self._notify_fallback(previous, candidate)
            return reply

        self.model = failed_model
        assert trigger_error is not None
        raise self._fallback_exhausted(trigger_error, attempted) from trigger_error

    def chat_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.85,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        should_stop=None,
        retry_callback=None,
    ) -> Iterator[str]:
        message_list = list(messages)
        emitted = False
        trigger_error: LocalModelError | None = None
        try:
            for chunk in super().chat_stream(
                message_list,
                system_prompt=system_prompt,
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
                should_stop=should_stop,
                retry_callback=retry_callback,
            ):
                emitted = True
                yield chunk
            return
        except LocalModelError as exc:
            if emitted or not self._can_start_fallback(exc):
                raise
            trigger_error = exc

        attempted: list[tuple[str, str]] = []
        failed_model = self.model
        for candidate in self._remaining_fallbacks():
            previous = self.model
            self.model = candidate
            candidate_emitted = False
            try:
                for chunk in super().chat_stream(
                    message_list,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    num_ctx=num_ctx,
                    num_predict=num_predict,
                    should_stop=should_stop,
                    retry_callback=retry_callback,
                ):
                    candidate_emitted = True
                    emitted = True
                    yield chunk
            except LocalModelError as exc:
                if candidate_emitted:
                    raise
                attempted.append((candidate, str(exc)))
                if self._candidate_failure_stops_chain(exc):
                    break
                continue
            self._notify_fallback(previous, candidate)
            return

        self.model = failed_model
        assert trigger_error is not None
        raise self._fallback_exhausted(trigger_error, attempted) from trigger_error

    def chat_json(
        self,
        messages: Iterable[ChatMessage],
        *,
        system_prompt: str,
        temperature: float = 0.25,
        retry_callback=None,
    ) -> dict[str, Any]:
        message_list = list(messages)
        trigger_error: LocalModelError | None = None
        try:
            return super().chat_json(
                message_list,
                system_prompt=system_prompt,
                temperature=temperature,
                retry_callback=retry_callback,
            )
        except LocalModelError as exc:
            if not self._can_start_fallback(exc):
                raise
            trigger_error = exc

        attempted: list[tuple[str, str]] = []
        failed_model = self.model
        for candidate in self._remaining_fallbacks():
            previous = self.model
            self.model = candidate
            try:
                result = super().chat_json(
                    message_list,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    retry_callback=retry_callback,
                )
            except LocalModelError as exc:
                attempted.append((candidate, str(exc)))
                if self._candidate_failure_stops_chain(exc):
                    break
                continue
            self._notify_fallback(previous, candidate)
            return result

        self.model = failed_model
        assert trigger_error is not None
        raise self._fallback_exhausted(trigger_error, attempted) from trigger_error
