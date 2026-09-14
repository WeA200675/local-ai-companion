from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import DateTime, Integer, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.ai.model import ChatMessage
from app.ai.persona import PersonaState
from app.memory.database import Base


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AppStateRow(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class StateStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def append_message(self, role: str, content: str) -> None:
        clean = content.strip()
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported persisted role: {role}")
        if not clean:
            return
        with self._session_factory.begin() as session:
            session.add(ChatMessageRow(role=role, content=clean))

    def list_messages(self, limit: int = 100) -> list[ChatMessage]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChatMessageRow).order_by(ChatMessageRow.id.desc()).limit(limit)
            ).all()
        rows.reverse()
        return [ChatMessage(role=row.role, content=row.content) for row in rows]  # type: ignore[arg-type]

    def clear_messages(self) -> None:
        with self._session_factory.begin() as session:
            session.execute(delete(ChatMessageRow))

    def save_persona(self, persona: PersonaState) -> None:
        payload = persona.model_dump_json()
        with self._session_factory.begin() as session:
            row = session.get(AppStateRow, "persona")
            if row is None:
                session.add(AppStateRow(key="persona", value_json=payload))
            else:
                row.value_json = payload

    def load_persona(self) -> PersonaState:
        with self._session_factory() as session:
            row = session.get(AppStateRow, "persona")
            if row is None:
                return PersonaState()
            return PersonaState.model_validate_json(row.value_json)

    def save_preference_tags(self, tags: Iterable[str]) -> None:
        normalized = sorted({tag.strip() for tag in tags if tag.strip()})
        payload = json.dumps(normalized, ensure_ascii=False)
        with self._session_factory.begin() as session:
            row = session.get(AppStateRow, "preference_tags")
            if row is None:
                session.add(AppStateRow(key="preference_tags", value_json=payload))
            else:
                row.value_json = payload

    def load_preference_tags(self) -> list[str]:
        with self._session_factory() as session:
            row = session.get(AppStateRow, "preference_tags")
            if row is None:
                return []
            value = json.loads(row.value_json)
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]
