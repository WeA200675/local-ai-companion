from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.media.planner import MediaIntent
from app.memory.store import StateStore

FOCUS_TAGS = (
    "portrait",
    "full_body",
    "detail",
    "environment",
    "character",
    "motion",
)


@dataclass(frozen=True, slots=True)
class WorkflowPerformance:
    profile_id: str
    positive: int = 0
    negative: int = 0
    matching_positive: int = 0
    matching_negative: int = 0

    @property
    def score(self) -> int:
        # Matching feedback matters most; generic feedback remains a softer signal.
        return (
            self.matching_positive * 6
            - self.matching_negative * 8
            + self.positive * 2
            - self.negative * 3
        )

    @property
    def samples(self) -> int:
        return self.positive + self.negative


def _folded_text(*parts: object) -> str:
    return " ".join(str(part or "").casefold().replace("-", " ").split() for part in parts)


def intent_focus_tags(intent: MediaIntent) -> tuple[str, ...]:
    """Derive conservative routing tags from already-decided visual direction."""

    tags: list[str] = []
    framing = _folded_text(intent.framing, intent.composition)
    scene = _folded_text(intent.theme, intent.visual_style, intent.mood)

    if any(token in framing for token in ("portrait", "close up", "headshot", "bust", "face")):
        tags.append("portrait")
    if any(token in framing for token in ("full body", "head to toe", "whole body", "full length")):
        tags.append("full_body")
    if any(token in framing + " " + scene for token in ("detail", "macro", "texture", "material close")):
        tags.append("detail")
    if any(
        token in framing + " " + scene
        for token in ("wide", "establishing", "environment", "room", "interior", "exterior", "scene")
    ):
        tags.append("environment")
    if intent.continuity_key:
        tags.append("character")
    if intent.kind != "image" or intent.motion.strip():
        tags.append("motion")

    return tuple(dict.fromkeys(tags))


def focus_tags_from_payload(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    stored = payload.get("workflow_focus_tags")
    if isinstance(stored, list):
        clean = [
            str(item).strip()
            for item in stored
            if str(item).strip() in FOCUS_TAGS
        ]
        if clean:
            return tuple(dict.fromkeys(clean))
    try:
        intent = MediaIntent.model_validate(payload)
    except ValueError:
        return ()
    return intent_focus_tags(intent)


class WorkflowPerformanceRepository:
    """Learn soft workflow-routing preferences from explicit media feedback only."""

    def __init__(self, store: StateStore, *, history_limit: int = 500) -> None:
        self.store = store
        self.history_limit = max(20, int(history_limit))

    def performance(
        self,
        profile_id: str,
        focus_tags: Iterable[str] = (),
    ) -> WorkflowPerformance:
        requested = {tag for tag in focus_tags if tag in FOCUS_TAGS}
        positive = negative = matching_positive = matching_negative = 0
        for event in self.store.list_media_events(limit=self.history_limit):
            intent = event.get("intent")
            if not isinstance(intent, dict):
                continue
            if str(intent.get("workflow_profile") or "") != profile_id:
                continue
            feedback = event.get("feedback")
            if feedback not in {"positive", "negative"}:
                continue
            event_tags = set(focus_tags_from_payload(intent))
            matches = bool(requested and event_tags.intersection(requested))
            if feedback == "positive":
                positive += 1
                matching_positive += int(matches)
            else:
                negative += 1
                matching_negative += int(matches)
        return WorkflowPerformance(
            profile_id=profile_id,
            positive=positive,
            negative=negative,
            matching_positive=matching_positive,
            matching_negative=matching_negative,
        )

    def scores(
        self,
        profile_ids: Iterable[str],
        focus_tags: Iterable[str] = (),
    ) -> dict[str, int]:
        requested = tuple(focus_tags)
        return {
            profile_id: self.performance(profile_id, requested).score
            for profile_id in profile_ids
        }
