from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.memory.store import StateStore

_WORD_RE = re.compile(r"[\wÀ-ÿ'-]+", re.UNICODE)


class AntiRepetitionConfig(BaseModel):
    """Conversation-scoped guidance that discourages repetitive phrasing and staging."""

    enabled: bool = True
    window: int = Field(default=8, ge=4, le=20)
    opening_threshold: int = Field(default=2, ge=2, le=5)
    creative_threshold: int = Field(default=3, ge=2, le=8)


class ReplyTrace(BaseModel):
    opening: str = ""
    creative_signature: str = ""


class AntiRepetitionState(BaseModel):
    config_by_conversation: dict[str, AntiRepetitionConfig] = Field(default_factory=dict)
    traces_by_conversation: dict[str, list[ReplyTrace]] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


class AntiRepetitionRepository:
    STATE_KEY = "anti_repetition"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> AntiRepetitionState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return AntiRepetitionState()
        try:
            return AntiRepetitionState.model_validate_json(payload)
        except ValueError:
            return AntiRepetitionState()

    def save(self, state: AntiRepetitionState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def config(self, conversation_id: str) -> AntiRepetitionConfig:
        state = self.load()
        config = state.config_by_conversation.get(conversation_id)
        return (config or AntiRepetitionConfig()).model_copy(deep=True)

    def set_config(self, conversation_id: str, config: AntiRepetitionConfig) -> None:
        state = self.load()
        state.config_by_conversation[conversation_id] = config.model_copy(deep=True)
        state.revision += 1
        self.save(state)

    @staticmethod
    def opening_key(text: str) -> str:
        words = [match.group(0).casefold() for match in _WORD_RE.finditer(text)]
        return " ".join(words[:5])

    def record_reply(
        self,
        conversation_id: str,
        text: str,
        creative_signature: str,
    ) -> None:
        clean_text = text.strip()
        if not clean_text:
            return
        state = self.load()
        traces = list(state.traces_by_conversation.get(conversation_id, []))
        traces.append(
            ReplyTrace(
                opening=self.opening_key(clean_text),
                creative_signature=creative_signature.strip(),
            )
        )
        state.traces_by_conversation[conversation_id] = traces[-20:]
        state.revision += 1
        self.save(state)

    def reset(self, conversation_id: str) -> None:
        state = self.load()
        if conversation_id in state.traces_by_conversation:
            state.traces_by_conversation.pop(conversation_id, None)
            state.revision += 1
            self.save(state)

    def recent(self, conversation_id: str) -> list[ReplyTrace]:
        config = self.config(conversation_id)
        traces = self.load().traces_by_conversation.get(conversation_id, [])
        return [trace.model_copy(deep=True) for trace in traces[-config.window :]]

    def guidance(self, conversation_id: str, current_signature: str) -> str:
        config = self.config(conversation_id)
        if not config.enabled:
            return ""
        traces = self.recent(conversation_id)
        if not traces:
            return ""

        hints: list[str] = []
        opening_counts: dict[str, int] = {}
        for trace in traces:
            if trace.opening:
                opening_counts[trace.opening] = opening_counts.get(trace.opening, 0) + 1
        repeated_openings = [
            opening
            for opening, count in opening_counts.items()
            if count >= config.opening_threshold
        ]
        if repeated_openings:
            examples = "; ".join(repeated_openings[:3])
            hints.append(
                "Vary the opening rhythm and sentence construction; avoid reusing these recent opening patterns: "
                + examples
            )

        signature = current_signature.strip()
        if signature:
            consecutive = 0
            for trace in reversed(traces):
                if trace.creative_signature != signature:
                    break
                consecutive += 1
            if consecutive >= config.creative_threshold - 1:
                hints.append(
                    "The current creative combination has been used repeatedly. Keep all explicit user locks and selected layers, "
                    "but vary micro-details, gestures, wording, pacing, and non-locked visual choices so the next response does not feel recycled."
                )

        if not hints:
            return ""
        return " ".join(hints)
