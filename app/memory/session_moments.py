from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.memory.conversations import ConversationRepository
from app.memory.store import StateStore


class SessionMoment(BaseModel):
    """User-saved exchange that can be reused as temporary re-entry context."""

    id: str = Field(min_length=1, max_length=80)
    conversation_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=600)
    user_excerpt: str = Field(default="", max_length=1200)
    assistant_excerpt: str = Field(default="", max_length=1200)
    created_at: datetime

    @field_validator("id", "conversation_id", "title", "note", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        return " ".join(str(value or "").split())

    def prompt_text(self) -> str:
        parts = [f"Saved moment: {self.title}"]
        if self.note:
            parts.append(f"user note: {self.note}")
        if self.user_excerpt:
            parts.append(f"earlier user excerpt: {self.user_excerpt}")
        if self.assistant_excerpt:
            parts.append(f"earlier companion excerpt: {self.assistant_excerpt}")
        return "; ".join(parts)


class SessionMomentState(BaseModel):
    moments: list[SessionMoment] = Field(default_factory=list)
    active_by_conversation: dict[str, str] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


class SessionMomentRepository:
    STATE_KEY = "session_moments"

    def __init__(self, store: StateStore, conversations: ConversationRepository) -> None:
        self.store = store
        self.conversations = conversations

    def load(self) -> SessionMomentState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return SessionMomentState()
        try:
            state = SessionMomentState.model_validate_json(payload)
        except ValueError:
            return SessionMomentState()
        valid_ids = {moment.id for moment in state.moments}
        state.active_by_conversation = {
            key: value for key, value in state.active_by_conversation.items() if value in valid_ids
        }
        return state

    def save(self, state: SessionMomentState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def list_moments(self, conversation_id: str | None = None) -> list[SessionMoment]:
        moments = self.load().moments
        if conversation_id is not None:
            moments = [item for item in moments if item.conversation_id == conversation_id]
        return [item.model_copy(deep=True) for item in reversed(moments)]

    def get(self, moment_id: str) -> SessionMoment | None:
        clean = moment_id.strip()
        return next(
            (item.model_copy(deep=True) for item in self.load().moments if item.id == clean),
            None,
        )

    def active(self, conversation_id: str) -> SessionMoment | None:
        state = self.load()
        moment_id = state.active_by_conversation.get(conversation_id)
        if not moment_id:
            return None
        return next(
            (
                item.model_copy(deep=True)
                for item in state.moments
                if item.id == moment_id and item.conversation_id == conversation_id
            ),
            None,
        )

    def capture_latest(
        self,
        conversation_id: str,
        *,
        title: str,
        note: str = "",
    ) -> SessionMoment:
        clean_title = " ".join(title.split())[:120]
        if not clean_title:
            raise ValueError("Moment title must not be empty")
        exchange = self.conversations.latest_exchange(conversation_id=conversation_id)
        if exchange is None:
            raise ValueError("A complete user/assistant exchange is required to save a moment")
        user_text, assistant_text = exchange
        moment = SessionMoment(
            id=f"moment-{uuid4().hex[:12]}",
            conversation_id=conversation_id,
            title=clean_title,
            note=" ".join(note.split())[:600],
            user_excerpt=" ".join(user_text.split())[:1200],
            assistant_excerpt=" ".join(assistant_text.split())[:1200],
            created_at=datetime.now(timezone.utc),
        )
        state = self.load()
        state.moments.append(moment)
        state.revision += 1
        self.save(state)
        return moment.model_copy(deep=True)

    def set_active(self, conversation_id: str, moment_id: str | None) -> SessionMoment | None:
        state = self.load()
        if not moment_id:
            if conversation_id in state.active_by_conversation:
                state.active_by_conversation.pop(conversation_id, None)
                state.revision += 1
                self.save(state)
            return None
        moment = next(
            (
                item
                for item in state.moments
                if item.id == moment_id and item.conversation_id == conversation_id
            ),
            None,
        )
        if moment is None:
            raise KeyError(f"Session moment {moment_id!r} not found in this conversation")
        state.active_by_conversation[conversation_id] = moment.id
        state.revision += 1
        self.save(state)
        return moment.model_copy(deep=True)

    def clear(self, conversation_id: str) -> None:
        self.set_active(conversation_id, None)

    def delete(self, moment_id: str) -> bool:
        state = self.load()
        target = next((item for item in state.moments if item.id == moment_id), None)
        if target is None:
            return False
        state.moments = [item for item in state.moments if item.id != moment_id]
        state.active_by_conversation = {
            key: value for key, value in state.active_by_conversation.items() if value != moment_id
        }
        state.revision += 1
        self.save(state)
        return True
