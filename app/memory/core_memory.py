from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class CoreMemory(BaseModel):
    """One deliberate, user-authored memory that the AI must not edit itself."""

    id: str
    title: str = Field(max_length=80)
    content: str = Field(max_length=1200)
    priority: int = Field(default=50, ge=0, le=100)
    active: bool = True
    created_at: datetime
    updated_at: datetime

    @field_validator("title", "content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("Core memory text must not be blank")
        return clean

    @classmethod
    def create(
        cls,
        *,
        title: str,
        content: str,
        priority: int = 50,
        active: bool = True,
    ) -> "CoreMemory":
        now = datetime.now(timezone.utc)
        return cls(
            id=uuid4().hex,
            title=title,
            content=content,
            priority=priority,
            active=active,
            created_at=now,
            updated_at=now,
        )

    def prompt_text(self) -> str:
        return f"{self.title}: {self.content}"


class CoreMemoryBook(BaseModel):
    revision: int = Field(default=1, ge=1)
    items: list[CoreMemory] = Field(default_factory=list)


class CoreMemoryRepository:
    """Persist core memories inside the existing local app-state/backup boundary."""

    STATE_KEY = "core_memories"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> CoreMemoryBook:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001 - same persistence layer
        if payload is None:
            return CoreMemoryBook()
        try:
            return CoreMemoryBook.model_validate_json(payload)
        except ValueError:
            return CoreMemoryBook()

    def save(self, book: CoreMemoryBook) -> None:
        self.store._save_app_state(  # noqa: SLF001 - same persistence layer
            self.STATE_KEY,
            book.model_dump_json(),
        )

    def list(self) -> list[CoreMemory]:
        book = self.load()
        return sorted(
            (item.model_copy(deep=True) for item in book.items),
            key=lambda item: (item.active, item.priority, item.updated_at),
            reverse=True,
        )

    def get(self, memory_id: str) -> CoreMemory | None:
        clean_id = memory_id.strip()
        for item in self.load().items:
            if item.id == clean_id:
                return item.model_copy(deep=True)
        return None

    def upsert(
        self,
        *,
        memory_id: str | None,
        title: str,
        content: str,
        priority: int = 50,
        active: bool = True,
    ) -> CoreMemory:
        book = self.load()
        clean_id = (memory_id or "").strip()
        now = datetime.now(timezone.utc)

        for index, item in enumerate(book.items):
            if clean_id and item.id == clean_id:
                updated = item.model_copy(
                    update={
                        "title": title,
                        "content": content,
                        "priority": priority,
                        "active": active,
                        "updated_at": now,
                    }
                )
                updated = CoreMemory.model_validate(updated.model_dump())
                book.items[index] = updated
                book.revision += 1
                self.save(book)
                return updated.model_copy(deep=True)

        created = CoreMemory.create(
            title=title,
            content=content,
            priority=priority,
            active=active,
        )
        book.items.append(created)
        book.revision += 1
        self.save(book)
        return created.model_copy(deep=True)

    def delete(self, memory_id: str) -> bool:
        book = self.load()
        clean_id = memory_id.strip()
        before = len(book.items)
        book.items = [item for item in book.items if item.id != clean_id]
        if len(book.items) == before:
            return False
        book.revision += 1
        self.save(book)
        return True

    def set_active(self, memory_id: str, active: bool) -> None:
        item = self.get(memory_id)
        if item is None:
            raise KeyError(f"Core memory {memory_id!r} not found")
        self.upsert(
            memory_id=item.id,
            title=item.title,
            content=item.content,
            priority=item.priority,
            active=active,
        )

    def active_prompt_entries(self, limit: int = 12) -> list[str]:
        return [item.prompt_text() for item in self.list() if item.active][: max(0, limit)]
