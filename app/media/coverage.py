from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from app.ai.creative_accents import default_detail_accents, default_mood_grades
from app.ai.look_presets import default_look_presets
from app.ai.scene_mixer import ATMOSPHERES, COMPOSITIONS, LIGHTING, SETTINGS, SceneMix
from app.ai.visual_motifs import default_visual_motifs
from app.memory.store import StateStore


class VisualCoverageConfig(BaseModel):
    enabled: bool = True
    recent_window: int = Field(default=24, ge=6, le=60)


class VisualCoverageSample(BaseModel):
    conversation_id: str
    created_at: datetime
    kind: str = "image"
    look_id: str | None = None
    setting_id: str | None = None
    lighting_id: str | None = None
    composition_id: str | None = None
    atmosphere_id: str | None = None
    motif_id: str | None = None
    mood_id: str | None = None
    detail_id: str | None = None


class VisualCoverageState(BaseModel):
    config_by_conversation: dict[str, VisualCoverageConfig] = Field(default_factory=dict)
    samples: list[VisualCoverageSample] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)


class CoverageDimension(BaseModel):
    key: str
    label: str
    counts: dict[str, int]
    labels: dict[str, str]
    underused_ids: list[str] = Field(default_factory=list)
    overused_ids: list[str] = Field(default_factory=list)


class VisualCoverageSummary(BaseModel):
    conversation_id: str
    sample_count: int
    window: int
    dimensions: list[CoverageDimension] = Field(default_factory=list)


_OPTION_LABELS: dict[str, dict[str, str]] = {
    "look": {item.id: item.name for item in default_look_presets()},
    "setting": {item.id: item.label for item in SETTINGS},
    "lighting": {item.id: item.label for item in LIGHTING},
    "composition": {item.id: item.label for item in COMPOSITIONS},
    "atmosphere": {item.id: item.label for item in ATMOSPHERES},
    "motif": {item.id: item.name for item in default_visual_motifs()},
    "mood": {item.id: item.name for item in default_mood_grades()},
    "detail": {item.id: item.name for item in default_detail_accents()},
    "kind": {"image": "Bild", "gif": "GIF", "video": "Video"},
}

_DIMENSION_LABELS = {
    "look": "Look",
    "setting": "Setting",
    "lighting": "Licht",
    "composition": "Komposition",
    "atmosphere": "Atmosphäre",
    "motif": "Visual-Motiv",
    "mood": "Mood-Grade",
    "detail": "Detail",
    "kind": "Medium",
}


def infer_media_kind(path: str | Path) -> str:
    suffix = Path(path).suffix.casefold()
    if suffix == ".gif":
        return "gif"
    if suffix in {".mp4", ".webm", ".mov", ".mkv"}:
        return "video"
    return "image"


class VisualCoverageRepository:
    """Conversation-scoped local coverage history for generated visuals.

    The tracker stores only compact creative IDs and media kind. It does not inspect
    image pixels and does not require a vision model, cloud service, or telemetry.
    """

    STATE_KEY = "visual_coverage"
    MAX_SAMPLES = 400

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> VisualCoverageState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return VisualCoverageState()
        try:
            state = VisualCoverageState.model_validate_json(payload)
        except ValueError:
            return VisualCoverageState()
        state.samples = state.samples[-self.MAX_SAMPLES :]
        return state

    def save(self, state: VisualCoverageState) -> None:
        state.samples = state.samples[-self.MAX_SAMPLES :]
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def config(self, conversation_id: str) -> VisualCoverageConfig:
        value = self.load().config_by_conversation.get(conversation_id)
        return (value or VisualCoverageConfig()).model_copy(deep=True)

    def set_config(self, conversation_id: str, config: VisualCoverageConfig) -> None:
        state = self.load()
        state.config_by_conversation[conversation_id] = config.model_copy(deep=True)
        state.revision += 1
        self.save(state)

    def record(
        self,
        conversation_id: str,
        *,
        kind: str,
        look_id: str | None = None,
        scene_mix: SceneMix | None = None,
        motif_id: str | None = None,
        mood_id: str | None = None,
        detail_id: str | None = None,
    ) -> VisualCoverageSample:
        components = scene_mix.component_ids if scene_mix is not None else {}
        sample = VisualCoverageSample(
            conversation_id=conversation_id,
            created_at=datetime.now(timezone.utc),
            kind=kind if kind in {"image", "gif", "video"} else "image",
            look_id=look_id,
            setting_id=components.get("setting"),
            lighting_id=components.get("lighting"),
            composition_id=components.get("composition"),
            atmosphere_id=components.get("atmosphere"),
            motif_id=motif_id,
            mood_id=mood_id,
            detail_id=detail_id,
        )
        state = self.load()
        state.samples.append(sample)
        state.revision += 1
        self.save(state)
        return sample.model_copy(deep=True)

    def samples(self, conversation_id: str, *, limit: int | None = None) -> list[VisualCoverageSample]:
        values = [
            item.model_copy(deep=True)
            for item in self.load().samples
            if item.conversation_id == conversation_id
        ]
        if limit is not None:
            values = values[-max(0, int(limit)) :]
        return values

    @staticmethod
    def _value(sample: VisualCoverageSample, key: str) -> str | None:
        return {
            "look": sample.look_id,
            "setting": sample.setting_id,
            "lighting": sample.lighting_id,
            "composition": sample.composition_id,
            "atmosphere": sample.atmosphere_id,
            "motif": sample.motif_id,
            "mood": sample.mood_id,
            "detail": sample.detail_id,
            "kind": sample.kind,
        }[key]

    def summary(self, conversation_id: str) -> VisualCoverageSummary:
        config = self.config(conversation_id)
        samples = self.samples(conversation_id, limit=config.recent_window)
        dimensions: list[CoverageDimension] = []
        for key, labels in _OPTION_LABELS.items():
            observed = [self._value(sample, key) for sample in samples]
            counts = Counter(value for value in observed if value)
            if not labels:
                continue
            minimum = min((counts.get(item_id, 0) for item_id in labels), default=0)
            maximum = max((counts.get(item_id, 0) for item_id in labels), default=0)
            underused = [item_id for item_id in labels if counts.get(item_id, 0) == minimum]
            overused = [
                item_id
                for item_id in labels
                if maximum > 0 and counts.get(item_id, 0) == maximum
            ]
            dimensions.append(
                CoverageDimension(
                    key=key,
                    label=_DIMENSION_LABELS[key],
                    counts={item_id: counts.get(item_id, 0) for item_id in labels},
                    labels=dict(labels),
                    underused_ids=underused,
                    overused_ids=overused,
                )
            )
        return VisualCoverageSummary(
            conversation_id=conversation_id,
            sample_count=len(samples),
            window=config.recent_window,
            dimensions=dimensions,
        )

    def guidance(self, conversation_id: str) -> str:
        config = self.config(conversation_id)
        if not config.enabled:
            return ""
        summary = self.summary(conversation_id)
        if summary.sample_count < 4:
            return ""

        useful_keys = {"lighting", "composition", "atmosphere", "motif", "detail"}
        suggestions: list[str] = []
        repetitions: list[str] = []
        for dimension in summary.dimensions:
            if dimension.key not in useful_keys:
                continue
            underused = [dimension.labels[item] for item in dimension.underused_ids[:2]]
            overused = [dimension.labels[item] for item in dimension.overused_ids[:1]]
            if underused:
                suggestions.append(f"{dimension.label}: {', '.join(underused)}")
            if overused:
                repetitions.append(f"{dimension.label}: {overused[0]}")

        if not suggestions:
            return ""
        avoid = f" Recently frequent: {'; '.join(repetitions[:3])}." if repetitions else ""
        return (
            "Local visual coverage soft hint: recent generated visuals are uneven. When the user's current "
            "request and all explicit creative selections/locks allow it, favor underused visual treatment: "
            + "; ".join(suggestions[:5])
            + "."
            + avoid
            + " Never override an explicit selection, creative lock, scene continuity, or stable character identity."
        )

    def reset(self, conversation_id: str) -> None:
        state = self.load()
        state.samples = [item for item in state.samples if item.conversation_id != conversation_id]
        state.revision += 1
        self.save(state)
