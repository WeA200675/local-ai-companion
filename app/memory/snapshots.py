from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.ai.persona import PersonaState
from app.memory.database import Base


class Snapshot(Base):
    __tablename__ = "persona_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    parent_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restore_target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    persona_json: Mapped[str] = mapped_column(Text, nullable=False)


class SnapshotStore:
    def __init__(self, session: Session):
        self.session = session
        Base.metadata.create_all(bind=session.get_bind())

    def save(
        self,
        state: PersonaState,
        *,
        kind: str = "manual",
        parent_snapshot_id: int | None = None,
        restore_target_id: int | None = None,
    ) -> Snapshot:
        snapshot = Snapshot(
            created_at=datetime.now(timezone.utc),
            kind=kind,
            parent_snapshot_id=parent_snapshot_id,
            restore_target_id=restore_target_id,
            persona_json=state.model_dump_json(),
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def get(self, snapshot_id: int) -> Snapshot:
        snapshot = self.session.get(Snapshot, snapshot_id)
        if snapshot is None:
            raise KeyError(f"Snapshot {snapshot_id} not found")
        return snapshot

    def list_recent(self, limit: int = 100) -> list[Snapshot]:
        return list(
            self.session.scalars(
                select(Snapshot).order_by(Snapshot.id.desc()).limit(limit)
            ).all()
        )

    def load_state(self, snapshot_id: int) -> PersonaState:
        snapshot = self.get(snapshot_id)
        return PersonaState.model_validate(json.loads(snapshot.persona_json))

    def latest(self) -> Snapshot | None:
        return self.session.scalar(select(Snapshot).order_by(Snapshot.id.desc()).limit(1))

    def restore(self, current_state: PersonaState, target_snapshot_id: int) -> PersonaState:
        target = self.get(target_snapshot_id)
        current = self.latest()

        self.save(
            current_state,
            kind="pre_restore",
            parent_snapshot_id=current.id if current else None,
            restore_target_id=target_snapshot_id,
        )

        restored_state = PersonaState.model_validate(json.loads(target.persona_json))
        restored_state.revision += 1

        self.save(
            restored_state,
            kind="restored",
            parent_snapshot_id=target_snapshot_id,
            restore_target_id=target_snapshot_id,
        )
        return restored_state
