from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.ai.model import ChatMessage
from app.ai.persona import PersonaState
from app.media.continuity import CharacterProfile
from app.media.preferences import VisualPreferenceProfile
from app.memory.database import Base
from app.settings import AppSettings


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


class LearningEventRow(Base):
    __tablename__ = "learning_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback: Mapped[str] = mapped_column(String(16), nullable=False)
    deltas_json: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MediaEventRow(Base):
    __tablename__ = "media_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    seed: Mapped[str] = mapped_column(String(32), nullable=False)
    continuity_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intent_json: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MemoryObservationRow(Base):
    __tablename__ = "memory_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_summary: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StateStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        with self._session_factory() as session:
            Base.metadata.create_all(bind=session.get_bind())

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

    def latest_user_message(self) -> str | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(ChatMessageRow)
                .where(ChatMessageRow.role == "user")
                .order_by(ChatMessageRow.id.desc())
                .limit(1)
            )
        return row.content if row is not None else None

    def latest_exchange(self) -> tuple[str, str] | None:
        """Return the latest adjacent user/assistant pair, if one exists."""

        with self._session_factory() as session:
            rows = session.scalars(
                select(ChatMessageRow).order_by(ChatMessageRow.id.desc()).limit(2)
            ).all()
        if len(rows) != 2 or rows[0].role != "assistant" or rows[1].role != "user":
            return None
        return rows[1].content, rows[0].content

    def delete_last_assistant_message(self) -> str | None:
        """Delete only the latest message when it is an assistant reply."""

        with self._session_factory.begin() as session:
            row = session.scalar(
                select(ChatMessageRow).order_by(ChatMessageRow.id.desc()).limit(1)
            )
            if row is None or row.role != "assistant":
                return None
            content = row.content
            session.delete(row)
            return content

    def replace_last_assistant_message(self, content: str) -> None:
        """Replace the latest assistant reply, used to join continued streams."""

        clean = content.strip()
        if not clean:
            raise ValueError("Assistant message must not be empty")
        with self._session_factory.begin() as session:
            row = session.scalar(
                select(ChatMessageRow).order_by(ChatMessageRow.id.desc()).limit(1)
            )
            if row is None or row.role != "assistant":
                raise KeyError("No latest assistant message to replace")
            row.content = clean

    def assistant_message_count(self) -> int:
        with self._session_factory() as session:
            count = session.scalar(
                select(func.count(ChatMessageRow.id)).where(ChatMessageRow.role == "assistant")
            )
        return int(count or 0)

    def clear_messages(self) -> None:
        with self._session_factory.begin() as session:
            session.execute(delete(ChatMessageRow))

    def save_persona(self, persona: PersonaState) -> None:
        self._save_app_state("persona", persona.model_dump_json())

    def load_persona(self) -> PersonaState:
        payload = self._load_app_state("persona")
        if payload is None:
            return PersonaState()
        return PersonaState.model_validate_json(payload)

    def snapshot_persona(self, persona: PersonaState, *, kind: str) -> int:
        """Write an immutable persona snapshot and return its id."""

        from app.memory.snapshots import SnapshotStore

        with self._session_factory() as session:
            snapshot = SnapshotStore(session).save(persona, kind=kind)
            return snapshot.id

    def save_preference_tags(self, tags: Iterable[str]) -> None:
        normalized = sorted({tag.strip() for tag in tags if tag.strip()})
        self._save_app_state(
            "preference_tags", json.dumps(normalized, ensure_ascii=False)
        )

    def load_preference_tags(self) -> list[str]:
        payload = self._load_app_state("preference_tags")
        if payload is None:
            return []
        try:
            value = json.loads(payload)
        except ValueError:
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def save_settings(self, settings: AppSettings) -> None:
        self._save_app_state("runtime_settings", settings.model_dump_json())

    def load_settings(self, defaults: AppSettings | None = None) -> AppSettings:
        fallback = defaults or AppSettings()
        payload = self._load_app_state("runtime_settings")
        if payload is None:
            return fallback.model_copy(deep=True)
        try:
            return AppSettings.model_validate_json(payload)
        except ValueError:
            return fallback.model_copy(deep=True)

    @staticmethod
    def _character_state_key(key: str) -> str:
        clean = key.strip() or "persona-main"
        return f"character:{clean}"[:80]

    def load_character_profile(self, key: str) -> CharacterProfile:
        state_key = self._character_state_key(key)
        payload = self._load_app_state(state_key)
        if payload is not None:
            try:
                return CharacterProfile.model_validate_json(payload)
            except ValueError:
                pass
        profile = CharacterProfile.create(key)
        self.save_character_profile(profile)
        return profile

    def save_character_profile(self, profile: CharacterProfile) -> None:
        self._save_app_state(
            self._character_state_key(profile.key), profile.model_dump_json()
        )

    def load_visual_preferences(self) -> VisualPreferenceProfile:
        payload = self._load_app_state("visual_preferences")
        if payload is None:
            return VisualPreferenceProfile()
        try:
            return VisualPreferenceProfile.model_validate_json(payload)
        except ValueError:
            return VisualPreferenceProfile()

    def save_visual_preferences(self, profile: VisualPreferenceProfile) -> None:
        self._save_app_state("visual_preferences", profile.model_dump_json())

    @staticmethod
    def _normalize_memory_summary(summary: str) -> str:
        return " ".join(summary.casefold().split())[:320]

    def upsert_memory_observation(
        self,
        *,
        category: str,
        summary: str,
        confidence: float,
    ) -> tuple[int, bool]:
        clean = " ".join(summary.split())[:240]
        if not clean:
            raise ValueError("Memory summary must not be empty")
        normalized = self._normalize_memory_summary(clean)
        now = datetime.now(timezone.utc)
        confidence = min(1.0, max(0.0, float(confidence)))

        with self._session_factory.begin() as session:
            row = session.scalar(
                select(MemoryObservationRow).where(
                    MemoryObservationRow.normalized_summary == normalized
                )
            )
            if row is None:
                row = MemoryObservationRow(
                    category=category.strip() or "preference",
                    summary=clean,
                    normalized_summary=normalized,
                    confidence=confidence,
                    active=True,
                    source_count=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                return row.id, True

            changed = False
            if confidence > row.confidence:
                row.confidence = confidence
                changed = True
            if row.category != category and category.strip():
                row.category = category.strip()
                changed = True
            row.source_count += 1
            row.updated_at = now
            return row.id, changed

    def list_memory_observations(self, limit: int = 200) -> list[dict[str, object]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(MemoryObservationRow)
                .order_by(
                    MemoryObservationRow.active.desc(),
                    MemoryObservationRow.confidence.desc(),
                    MemoryObservationRow.updated_at.desc(),
                )
                .limit(limit)
            ).all()
        return [
            {
                "id": row.id,
                "category": row.category,
                "summary": row.summary,
                "confidence": row.confidence,
                "active": row.active,
                "source_count": row.source_count,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]

    def list_active_memory_summaries(self, limit: int = 12) -> list[str]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(MemoryObservationRow)
                .where(MemoryObservationRow.active.is_(True))
                .order_by(
                    MemoryObservationRow.confidence.desc(),
                    MemoryObservationRow.updated_at.desc(),
                )
                .limit(limit)
            ).all()
        return [row.summary for row in rows]

    def set_memory_observation_active(self, observation_id: int, active: bool) -> None:
        with self._session_factory.begin() as session:
            row = session.get(MemoryObservationRow, observation_id)
            if row is None:
                raise KeyError(f"Memory observation {observation_id} not found")
            row.active = bool(active)
            row.updated_at = datetime.now(timezone.utc)

    def record_learning_event(
        self,
        *,
        feedback: str,
        deltas: dict[str, float],
        rationale: str,
    ) -> None:
        if feedback not in {"positive", "negative"}:
            raise ValueError(f"Unsupported feedback: {feedback}")
        with self._session_factory.begin() as session:
            session.add(
                LearningEventRow(
                    feedback=feedback,
                    deltas_json=json.dumps(deltas, ensure_ascii=False, sort_keys=True),
                    rationale=rationale.strip(),
                )
            )

    def list_learning_events(self, limit: int = 50) -> list[dict[str, object]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(LearningEventRow).order_by(LearningEventRow.id.desc()).limit(limit)
            ).all()
        return [
            {
                "id": row.id,
                "feedback": row.feedback,
                "deltas": json.loads(row.deltas_json),
                "rationale": row.rationale,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def record_media_event(
        self,
        *,
        path: str,
        kind: str,
        prompt_id: str,
        seed: int,
        continuity_key: str | None,
        intent: dict[str, object],
    ) -> int:
        with self._session_factory.begin() as session:
            row = MediaEventRow(
                path=path,
                kind=kind,
                prompt_id=prompt_id,
                seed=str(seed),
                continuity_key=continuity_key,
                intent_json=json.dumps(intent, ensure_ascii=False, sort_keys=True),
            )
            session.add(row)
            session.flush()
            return row.id

    def list_media_events(self, limit: int = 200) -> list[dict[str, object]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(MediaEventRow).order_by(MediaEventRow.id.desc()).limit(limit)
            ).all()
        return [
            {
                "id": row.id,
                "path": row.path,
                "kind": row.kind,
                "prompt_id": row.prompt_id,
                "seed": int(row.seed),
                "continuity_key": row.continuity_key,
                "intent": json.loads(row.intent_json),
                "feedback": row.feedback,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def set_media_feedback(self, media_id: int, feedback: str | None) -> None:
        if feedback not in {None, "positive", "negative"}:
            raise ValueError(f"Unsupported media feedback: {feedback}")

        with self._session_factory.begin() as session:
            row = session.get(MediaEventRow, media_id)
            if row is None:
                raise KeyError(f"Media event {media_id} not found")
            old_feedback = row.feedback
            if old_feedback == feedback:
                return
            row.feedback = feedback

            try:
                intent = json.loads(row.intent_json)
            except ValueError:
                intent = {}
            if not isinstance(intent, dict):
                intent = {}

            visual_row = session.get(AppStateRow, "visual_preferences")
            if visual_row is None:
                visual = VisualPreferenceProfile()
            else:
                try:
                    visual = VisualPreferenceProfile.model_validate_json(visual_row.value_json)
                except ValueError:
                    visual = VisualPreferenceProfile()

            if old_feedback in {"positive", "negative"}:
                visual.adjust(intent, old_feedback, amount=-1)
            if feedback in {"positive", "negative"}:
                visual.adjust(intent, feedback, amount=1)

            visual_json = visual.model_dump_json()
            if visual_row is None:
                session.add(AppStateRow(key="visual_preferences", value_json=visual_json))
            else:
                visual_row.value_json = visual_json

            if not row.continuity_key:
                return

            state_key = self._character_state_key(row.continuity_key)
            state_row = session.get(AppStateRow, state_key)
            if state_row is None:
                profile = CharacterProfile.create(row.continuity_key)
            else:
                try:
                    profile = CharacterProfile.model_validate_json(state_row.value_json)
                except ValueError:
                    profile = CharacterProfile.create(row.continuity_key)

            if old_feedback == "positive":
                profile.positive_feedback = max(0, profile.positive_feedback - 1)
            elif old_feedback == "negative":
                profile.negative_feedback = max(0, profile.negative_feedback - 1)

            if feedback == "positive":
                profile.positive_feedback += 1
            elif feedback == "negative":
                profile.negative_feedback += 1

            serialized = profile.model_dump_json()
            if state_row is None:
                session.add(AppStateRow(key=state_key, value_json=serialized))
            else:
                state_row.value_json = serialized

    def _save_app_state(self, key: str, value_json: str) -> None:
        with self._session_factory.begin() as session:
            row = session.get(AppStateRow, key)
            if row is None:
                session.add(AppStateRow(key=key, value_json=value_json))
            else:
                row.value_json = value_json

    def _load_app_state(self, key: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(AppStateRow, key)
            return row.value_json if row is not None else None
