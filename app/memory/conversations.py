from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.model import ChatMessage
from app.memory.database import Base
from app.memory.store import ChatMessageRow, StateStore


class ConversationThreadRow(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationThread(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=120)
    archived: bool = False
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationRepository:
    """Conversation isolation layered on top of the existing local SQLite store.

    Legacy single-chat rows are copied into the initial conversation once. They are
    never deleted during migration, which keeps older backups/tests readable.
    """

    ACTIVE_KEY = "active_conversation_id"
    DEFAULT_ID = "main"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        self._session_factory = store._session_factory  # noqa: SLF001 - same persistence boundary
        with self._session_factory() as session:
            Base.metadata.create_all(bind=session.get_bind())
        self._bootstrap()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _bootstrap(self) -> None:
        with self._session_factory.begin() as session:
            existing = session.scalar(select(func.count(ConversationThreadRow.id)))
            if int(existing or 0) == 0:
                now = self._now()
                session.add(
                    ConversationThreadRow(
                        id=self.DEFAULT_ID,
                        title="Hauptchat",
                        archived=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                legacy = session.scalars(select(ChatMessageRow).order_by(ChatMessageRow.id)).all()
                for row in legacy:
                    session.add(
                        ConversationMessageRow(
                            conversation_id=self.DEFAULT_ID,
                            role=row.role,
                            content=row.content,
                            created_at=row.created_at,
                        )
                    )
        active = self.store._load_app_state(self.ACTIVE_KEY)  # noqa: SLF001
        if not active or self.get(active, include_archived=False) is None:
            first = self.list_threads(include_archived=False)
            if not first:
                created = self.create("Hauptchat", activate=True)
                active = created.id
            else:
                active = first[0].id
                self.store._save_app_state(self.ACTIVE_KEY, active)  # noqa: SLF001

    def active_id(self) -> str:
        value = self.store._load_app_state(self.ACTIVE_KEY)  # noqa: SLF001
        if value and self.get(value, include_archived=False) is not None:
            return value
        threads = self.list_threads(include_archived=False)
        if not threads:
            return self.create("Hauptchat", activate=True).id
        self.store._save_app_state(self.ACTIVE_KEY, threads[0].id)  # noqa: SLF001
        return threads[0].id

    def set_active(self, conversation_id: str) -> ConversationThread:
        thread = self.get(conversation_id, include_archived=False)
        if thread is None:
            raise KeyError(f"Conversation {conversation_id!r} not found or archived")
        self.store._save_app_state(self.ACTIVE_KEY, thread.id)  # noqa: SLF001
        return thread

    def list_threads(self, *, include_archived: bool = False) -> list[ConversationThread]:
        with self._session_factory() as session:
            query = select(ConversationThreadRow)
            if not include_archived:
                query = query.where(ConversationThreadRow.archived.is_(False))
            rows = session.scalars(query.order_by(ConversationThreadRow.updated_at.desc())).all()
            result: list[ConversationThread] = []
            for row in rows:
                count = session.scalar(
                    select(func.count(ConversationMessageRow.id)).where(
                        ConversationMessageRow.conversation_id == row.id
                    )
                )
                result.append(
                    ConversationThread(
                        id=row.id,
                        title=row.title,
                        archived=row.archived,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        message_count=int(count or 0),
                    )
                )
        return result

    def get(self, conversation_id: str, *, include_archived: bool = True) -> ConversationThread | None:
        clean = conversation_id.strip()
        if not clean:
            return None
        with self._session_factory() as session:
            row = session.get(ConversationThreadRow, clean)
            if row is None or (row.archived and not include_archived):
                return None
            count = session.scalar(
                select(func.count(ConversationMessageRow.id)).where(
                    ConversationMessageRow.conversation_id == row.id
                )
            )
            return ConversationThread(
                id=row.id,
                title=row.title,
                archived=row.archived,
                created_at=row.created_at,
                updated_at=row.updated_at,
                message_count=int(count or 0),
            )

    def create(self, title: str, *, activate: bool = True) -> ConversationThread:
        clean = " ".join(title.split())[:120]
        if not clean:
            raise ValueError("Conversation title must not be empty")
        now = self._now()
        conversation_id = uuid4().hex[:24]
        with self._session_factory.begin() as session:
            session.add(
                ConversationThreadRow(
                    id=conversation_id,
                    title=clean,
                    archived=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        if activate:
            self.store._save_app_state(self.ACTIVE_KEY, conversation_id)  # noqa: SLF001
        return self.get(conversation_id)  # type: ignore[return-value]

    def rename(self, conversation_id: str, title: str) -> ConversationThread:
        clean = " ".join(title.split())[:120]
        if not clean:
            raise ValueError("Conversation title must not be empty")
        with self._session_factory.begin() as session:
            row = session.get(ConversationThreadRow, conversation_id)
            if row is None:
                raise KeyError(f"Conversation {conversation_id!r} not found")
            row.title = clean
            row.updated_at = self._now()
        return self.get(conversation_id)  # type: ignore[return-value]

    def archive(self, conversation_id: str) -> None:
        active_threads = self.list_threads(include_archived=False)
        if len(active_threads) <= 1 and any(item.id == conversation_id for item in active_threads):
            raise ValueError("At least one active conversation must remain")
        with self._session_factory.begin() as session:
            row = session.get(ConversationThreadRow, conversation_id)
            if row is None:
                raise KeyError(f"Conversation {conversation_id!r} not found")
            row.archived = True
            row.updated_at = self._now()
        if self.active_id() == conversation_id:
            replacement = self.list_threads(include_archived=False)[0]
            self.set_active(replacement.id)

    def unarchive(self, conversation_id: str) -> ConversationThread:
        with self._session_factory.begin() as session:
            row = session.get(ConversationThreadRow, conversation_id)
            if row is None:
                raise KeyError(f"Conversation {conversation_id!r} not found")
            row.archived = False
            row.updated_at = self._now()
        return self.get(conversation_id)  # type: ignore[return-value]

    def fork(self, source_id: str, title: str | None = None, *, activate: bool = True) -> ConversationThread:
        source = self.get(source_id, include_archived=True)
        if source is None:
            raise KeyError(f"Conversation {source_id!r} not found")
        target = self.create(title or f"{source.title} – Variante", activate=False)
        with self._session_factory.begin() as session:
            rows = session.scalars(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == source_id)
                .order_by(ConversationMessageRow.id)
            ).all()
            now = self._now()
            for row in rows:
                session.add(
                    ConversationMessageRow(
                        conversation_id=target.id,
                        role=row.role,
                        content=row.content,
                        created_at=row.created_at,
                    )
                )
            target_row = session.get(ConversationThreadRow, target.id)
            if target_row is not None:
                target_row.updated_at = now
        if activate:
            self.set_active(target.id)
        return self.get(target.id)  # type: ignore[return-value]

    def append_message(self, role: str, content: str, *, conversation_id: str | None = None) -> None:
        clean = content.strip()
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported persisted role: {role}")
        if not clean:
            return
        target = conversation_id or self.active_id()
        if self.get(target, include_archived=False) is None:
            raise KeyError(f"Conversation {target!r} not found or archived")
        now = self._now()
        with self._session_factory.begin() as session:
            session.add(
                ConversationMessageRow(
                    conversation_id=target,
                    role=role,
                    content=clean,
                    created_at=now,
                )
            )
            thread = session.get(ConversationThreadRow, target)
            if thread is not None:
                thread.updated_at = now
            # Keep the old single-chat table readable for the original conversation only.
            if target == self.DEFAULT_ID:
                session.add(ChatMessageRow(role=role, content=clean, created_at=now))

    def list_messages(
        self,
        limit: int = 100,
        *,
        conversation_id: str | None = None,
    ) -> list[ChatMessage]:
        target = conversation_id or self.active_id()
        with self._session_factory() as session:
            rows = session.scalars(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == target)
                .order_by(ConversationMessageRow.id.desc())
                .limit(limit)
            ).all()
        rows.reverse()
        return [ChatMessage(role=row.role, content=row.content) for row in rows]  # type: ignore[arg-type]

    def latest_user_message(self, *, conversation_id: str | None = None) -> str | None:
        target = conversation_id or self.active_id()
        with self._session_factory() as session:
            row = session.scalar(
                select(ConversationMessageRow)
                .where(
                    ConversationMessageRow.conversation_id == target,
                    ConversationMessageRow.role == "user",
                )
                .order_by(ConversationMessageRow.id.desc())
                .limit(1)
            )
        return row.content if row is not None else None

    def latest_exchange(self, *, conversation_id: str | None = None) -> tuple[str, str] | None:
        target = conversation_id or self.active_id()
        with self._session_factory() as session:
            rows = session.scalars(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == target)
                .order_by(ConversationMessageRow.id.desc())
                .limit(2)
            ).all()
        if len(rows) != 2 or rows[0].role != "assistant" or rows[1].role != "user":
            return None
        return rows[1].content, rows[0].content

    def delete_last_assistant_message(self, *, conversation_id: str | None = None) -> str | None:
        target = conversation_id or self.active_id()
        with self._session_factory.begin() as session:
            row = session.scalar(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == target)
                .order_by(ConversationMessageRow.id.desc())
                .limit(1)
            )
            if row is None or row.role != "assistant":
                return None
            content = row.content
            session.delete(row)
            return content

    def replace_last_assistant_message(
        self,
        content: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        clean = content.strip()
        if not clean:
            raise ValueError("Assistant message must not be empty")
        target = conversation_id or self.active_id()
        with self._session_factory.begin() as session:
            row = session.scalar(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == target)
                .order_by(ConversationMessageRow.id.desc())
                .limit(1)
            )
            if row is None or row.role != "assistant":
                raise KeyError("No latest assistant message to replace")
            row.content = clean
            thread = session.get(ConversationThreadRow, target)
            if thread is not None:
                thread.updated_at = self._now()

    def assistant_message_count(self, *, conversation_id: str | None = None) -> int:
        target = conversation_id or self.active_id()
        with self._session_factory() as session:
            count = session.scalar(
                select(func.count(ConversationMessageRow.id)).where(
                    ConversationMessageRow.conversation_id == target,
                    ConversationMessageRow.role == "assistant",
                )
            )
        return int(count or 0)

    def clear_messages(self, *, conversation_id: str | None = None) -> None:
        target = conversation_id or self.active_id()
        with self._session_factory.begin() as session:
            session.execute(
                delete(ConversationMessageRow).where(
                    ConversationMessageRow.conversation_id == target
                )
            )
            thread = session.get(ConversationThreadRow, target)
            if thread is not None:
                thread.updated_at = self._now()
            if target == self.DEFAULT_ID:
                session.execute(delete(ChatMessageRow))
