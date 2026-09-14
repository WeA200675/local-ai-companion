from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field


class VisualPreferenceProfile(BaseModel):
    """Small, auditable local preference memory for generated visuals."""

    liked: dict[str, int] = Field(default_factory=dict)
    disliked: dict[str, int] = Field(default_factory=dict)

    @staticmethod
    def cues_from_intent(intent: dict[str, object]) -> list[str]:
        cues: list[str] = []
        for key in ("mood", "theme", "visual_style"):
            value = intent.get(key)
            if isinstance(value, str) and value.strip():
                cues.append(value.strip().lower())
        wardrobe = intent.get("wardrobe")
        if isinstance(wardrobe, list):
            for item in wardrobe:
                if isinstance(item, str) and item.strip():
                    cues.append(item.strip().lower())
        return list(dict.fromkeys(cues))[:20]

    def adjust(self, intent: dict[str, object], feedback: str, amount: int = 1) -> None:
        if feedback not in {"positive", "negative"}:
            raise ValueError(f"Unsupported media feedback: {feedback}")
        bucket = self.liked if feedback == "positive" else self.disliked
        for cue in self.cues_from_intent(intent):
            next_value = bucket.get(cue, 0) + amount
            if next_value <= 0:
                bucket.pop(cue, None)
            else:
                bucket[cue] = next_value

    @staticmethod
    def _top(bucket: dict[str, int], limit: int) -> list[str]:
        return [
            cue
            for cue, _score in sorted(
                bucket.items(), key=lambda item: (-item[1], item[0])
            )[:limit]
        ]

    def top_liked(self, limit: int = 8) -> list[str]:
        return self._top(self.liked, limit)

    def top_disliked(self, limit: int = 8) -> list[str]:
        return self._top(self.disliked, limit)

    def describe(self, limit: int = 8) -> tuple[str, str]:
        liked = ", ".join(self.top_liked(limit)) or "none yet"
        disliked = ", ".join(self.top_disliked(limit)) or "none yet"
        return liked, disliked
