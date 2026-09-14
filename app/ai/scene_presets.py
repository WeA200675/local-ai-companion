from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.memory.store import StateStore


class ScenePreset(BaseModel):
    """Temporary user-authored scene context; separate from persona and memory."""

    id: str
    name: str = Field(max_length=80)
    context: str = Field(max_length=1800)
    style_tags: list[str] = Field(default_factory=list, max_length=24)
    created_at: datetime
    updated_at: datetime

    @field_validator("name", "context")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("Scene name and context must not be blank")
        return clean

    @field_validator("style_tags")
    @classmethod
    def _clean_tags(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = " ".join(value.split())[:80]
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result[:24]

    @classmethod
    def create(cls, *, name: str, context: str, style_tags: list[str]) -> "ScenePreset":
        now = datetime.now(timezone.utc)
        return cls(
            id=uuid4().hex,
            name=name,
            context=context,
            style_tags=style_tags,
            created_at=now,
            updated_at=now,
        )


class ScenePresetBook(BaseModel):
    revision: int = Field(default=1, ge=1)
    active_id: str | None = None
    items: list[ScenePreset] = Field(default_factory=list)


class ScenePresetRepository:
    STATE_KEY = "scene_presets"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> ScenePresetBook:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return ScenePresetBook()
        try:
            book = ScenePresetBook.model_validate_json(payload)
        except ValueError:
            return ScenePresetBook()
        if book.active_id and all(item.id != book.active_id for item in book.items):
            book.active_id = None
        return book

    def save(self, book: ScenePresetBook) -> None:
        self.store._save_app_state(self.STATE_KEY, book.model_dump_json())  # noqa: SLF001

    def list(self) -> list[ScenePreset]:
        return sorted(
            (item.model_copy(deep=True) for item in self.load().items),
            key=lambda item: (item.updated_at, item.name.casefold()),
            reverse=True,
        )

    def get(self, scene_id: str) -> ScenePreset | None:
        clean_id = scene_id.strip()
        for item in self.load().items:
            if item.id == clean_id:
                return item.model_copy(deep=True)
        return None

    def active(self) -> ScenePreset | None:
        book = self.load()
        if not book.active_id:
            return None
        for item in book.items:
            if item.id == book.active_id:
                return item.model_copy(deep=True)
        return None

    def upsert(
        self,
        *,
        scene_id: str | None,
        name: str,
        context: str,
        style_tags: list[str],
    ) -> ScenePreset:
        book = self.load()
        clean_id = (scene_id or "").strip()
        now = datetime.now(timezone.utc)

        for index, item in enumerate(book.items):
            if clean_id and item.id == clean_id:
                updated = ScenePreset.model_validate(
                    item.model_copy(
                        update={
                            "name": name,
                            "context": context,
                            "style_tags": style_tags,
                            "updated_at": now,
                        }
                    ).model_dump()
                )
                book.items[index] = updated
                book.revision += 1
                self.save(book)
                return updated.model_copy(deep=True)

        created = ScenePreset.create(name=name, context=context, style_tags=style_tags)
        book.items.append(created)
        book.revision += 1
        self.save(book)
        return created.model_copy(deep=True)

    def delete(self, scene_id: str) -> bool:
        book = self.load()
        clean_id = scene_id.strip()
        before = len(book.items)
        book.items = [item for item in book.items if item.id != clean_id]
        if len(book.items) == before:
            return False
        if book.active_id == clean_id:
            book.active_id = None
        book.revision += 1
        self.save(book)
        return True

    def set_active(self, scene_id: str | None) -> ScenePreset | None:
        book = self.load()
        clean_id = (scene_id or "").strip()
        if not clean_id:
            book.active_id = None
            book.revision += 1
            self.save(book)
            return None
        selected = next((item for item in book.items if item.id == clean_id), None)
        if selected is None:
            raise KeyError(f"Scene preset {scene_id!r} not found")
        book.active_id = selected.id
        book.revision += 1
        self.save(book)
        return selected.model_copy(deep=True)
