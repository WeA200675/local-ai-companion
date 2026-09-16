from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Iterable

from app.media.capabilities import WorkflowCapability
from app.media.hardware import MediaHardwareBudget
from app.media.planner import MediaIntent
from app.media.profiles import WorkflowProfile
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
    return " ".join(
        " ".join(str(part or "").casefold().replace("-", " ").split())
        for part in parts
    ).strip()


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

    def repetition_penalty(
        self,
        profile_id: str,
        framing: str,
        *,
        limit: int = 12,
    ) -> tuple[int, int]:
        """Penalize recent workflow reuse and repeated workflow/framing pairs."""

        clean_framing = _folded_text(framing)
        workflow_penalty = 0
        framing_penalty = 0
        for index, event in enumerate(self.store.list_media_events(limit=max(1, limit))):
            intent = event.get("intent")
            if not isinstance(intent, dict):
                continue
            if str(intent.get("workflow_profile") or "") != profile_id:
                continue
            weight = max(1, 8 - index)
            workflow_penalty += weight
            if clean_framing and _folded_text(intent.get("framing")) == clean_framing:
                framing_penalty += weight + 3
        return min(24, workflow_penalty), min(24, framing_penalty)


@dataclass(frozen=True, slots=True)
class WorkflowHealth:
    profile_id: str
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    quarantined: bool = False
    last_error: str = ""
    last_success_at: str = ""
    last_failure_at: str = ""

    @property
    def samples(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        # Beta(1, 1) smoothing prevents one early outcome from dominating.
        return (self.successes + 1) / (self.samples + 2)

    @property
    def reliability_score(self) -> int:
        score = int(round((self.success_rate - 0.5) * 40))
        score -= min(18, self.consecutive_failures * 6)
        return max(-30, min(20, score))

    def as_dict(self) -> dict[str, object]:
        return {
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "quarantined": self.quarantined,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
        }

    @classmethod
    def from_dict(cls, profile_id: str, value: object) -> "WorkflowHealth":
        payload = value if isinstance(value, dict) else {}

        def count(key: str) -> int:
            raw = payload.get(key, 0)
            return max(0, int(raw)) if isinstance(raw, (int, float)) else 0

        return cls(
            profile_id=profile_id,
            successes=count("successes"),
            failures=count("failures"),
            consecutive_failures=count("consecutive_failures"),
            quarantined=bool(payload.get("quarantined", False)),
            last_error=str(payload.get("last_error") or "")[:500],
            last_success_at=str(payload.get("last_success_at") or "")[:80],
            last_failure_at=str(payload.get("last_failure_at") or "")[:80],
        )


class WorkflowHealthRepository:
    """Persist local render outcomes and quarantine repeatedly failing workflows."""

    _STATE_KEY = "media_workflow_health_v1"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def _load(self) -> dict[str, object]:
        raw = self.store._load_app_state(self._STATE_KEY)  # noqa: SLF001
        if raw is None:
            return {}
        try:
            payload = json.loads(raw)
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self, payload: dict[str, object]) -> None:
        self.store._save_app_state(  # noqa: SLF001
            self._STATE_KEY,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )

    def get(self, profile_id: str) -> WorkflowHealth:
        return WorkflowHealth.from_dict(profile_id, self._load().get(profile_id))

    def all(self) -> dict[str, WorkflowHealth]:
        return {
            profile_id: WorkflowHealth.from_dict(profile_id, value)
            for profile_id, value in self._load().items()
            if isinstance(profile_id, str)
        }

    def record_success(self, profile_id: str) -> WorkflowHealth:
        payload = self._load()
        current = WorkflowHealth.from_dict(profile_id, payload.get(profile_id))
        updated = WorkflowHealth(
            profile_id=profile_id,
            successes=current.successes + 1,
            failures=current.failures,
            consecutive_failures=0,
            quarantined=False,
            last_error="",
            last_success_at=datetime.now(timezone.utc).isoformat(),
            last_failure_at=current.last_failure_at,
        )
        payload[profile_id] = updated.as_dict()
        self._save(payload)
        return updated

    def record_failure(
        self,
        profile_id: str,
        error: str,
        *,
        threshold: int = 3,
        confirmed: bool = True,
    ) -> WorkflowHealth:
        current = self.get(profile_id)
        if not confirmed:
            return current
        payload = self._load()
        consecutive = current.consecutive_failures + 1
        updated = WorkflowHealth(
            profile_id=profile_id,
            successes=current.successes,
            failures=current.failures + 1,
            consecutive_failures=consecutive,
            quarantined=consecutive >= max(1, threshold),
            last_error=" ".join(error.split())[:500],
            last_success_at=current.last_success_at,
            last_failure_at=datetime.now(timezone.utc).isoformat(),
        )
        payload[profile_id] = updated.as_dict()
        self._save(payload)
        return updated

    def record_probe(self, profile_id: str, *, succeeded: bool, error: str = "") -> WorkflowHealth:
        """A successful explicit test automatically releases a quarantined profile."""

        if succeeded:
            return self.record_success(profile_id)
        return self.record_failure(profile_id, error or "workflow probe failed")


@dataclass(frozen=True, slots=True)
class WorkflowRouteCandidate:
    profile: WorkflowProfile
    score: int
    suitability_score: int
    components: dict[str, int]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile.id,
            "score": self.score,
            "suitability_score": self.suitability_score,
            "components": dict(self.components),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class WorkflowRoutingDecision:
    requested_kind: str
    focus_tags: tuple[str, ...]
    candidates: tuple[WorkflowRouteCandidate, ...]
    quarantined_profile_ids: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()

    @property
    def selected(self) -> WorkflowRouteCandidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def fallback_profile_ids(self) -> tuple[str, ...]:
        return tuple(item.profile.id for item in self.candidates[1:])

    def explain(self) -> str:
        selected = self.selected
        if selected is None:
            detail = "; ".join(self.rejected) or "keine technisch geeigneten Profile"
            return f"Keine Route für {self.requested_kind}: {detail}."
        components = ", ".join(
            f"{name} {value:+d}" for name, value in selected.components.items() if value
        )
        fallback = ", ".join(self.fallback_profile_ids) or "keiner"
        reasons = "; ".join(selected.reasons[:3])
        return (
            f"{selected.profile.id} wurde mit {selected.score} Punkten gewählt "
            f"({components or 'neutrale Signale'}); Gründe: {reasons}; "
            f"priorisierte Fallbacks: {fallback}."
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "requested_kind": self.requested_kind,
            "focus_tags": list(self.focus_tags),
            "selected_profile_id": (
                self.selected.profile.id if self.selected is not None else None
            ),
            "fallback_profile_ids": list(self.fallback_profile_ids),
            "quarantined_profile_ids": list(self.quarantined_profile_ids),
            "rejected": list(self.rejected),
            "candidates": [item.as_dict() for item in self.candidates],
            "explanation": self.explain(),
        }


def workflow_suitability_score(
    capability: WorkflowCapability,
    *,
    kind: str,
    reference_needed: bool,
) -> int:
    """Score technical fitness after the hard runnable gate."""

    if not capability.runnable or kind not in capability.runnable_kinds:
        return 0
    score = 45
    evidence = set(capability.output_evidence)
    if kind in evidence:
        score += 20
    elif not evidence:
        score += 8
    else:
        score -= 12
    score += round(25 * len(capability.render_controls) / 7)
    if reference_needed:
        score += 10 if capability.reference_supported else -12
    score -= min(18, len(capability.warnings) * 3)
    return max(0, min(100, score))


class WorkflowRouter:
    """Build an explainable, deterministic workflow and fallback chain."""

    def __init__(
        self,
        profiles: Iterable[WorkflowProfile],
        capabilities: dict[str, WorkflowCapability],
        *,
        performance: WorkflowPerformanceRepository | None = None,
        health: WorkflowHealthRepository | None = None,
    ) -> None:
        self.profiles = tuple(profiles)
        self.capabilities = capabilities
        self.performance = performance
        self.health = health

    @staticmethod
    def _hardware_score(
        profile: WorkflowProfile,
        hardware: MediaHardwareBudget,
        *,
        motion: bool,
    ) -> tuple[int, str]:
        available = (
            hardware.vram_free_gb
            if hardware.vram_free_gb is not None
            else hardware.vram_total_gb
        )
        score = 0
        reason = "hardware budget unknown"
        if profile.min_vram_gb is not None:
            if available is None:
                score -= 5
                reason = f"minimum {profile.min_vram_gb:.1f} GB VRAM not measurable"
            elif available < profile.min_vram_gb:
                score -= 45
                reason = (
                    f"{available:.1f} GB free/total VRAM below "
                    f"{profile.min_vram_gb:.1f} GB minimum"
                )
            else:
                score += 8
                reason = f"VRAM meets {profile.min_vram_gb:.1f} GB minimum"
        if profile.preferred_vram_gb is not None and available is not None:
            if available >= profile.preferred_vram_gb:
                score += 8
                reason = f"VRAM meets {profile.preferred_vram_gb:.1f} GB preference"
            elif profile.min_vram_gb is None or available >= profile.min_vram_gb:
                score -= 6
                reason = f"VRAM below {profile.preferred_vram_gb:.1f} GB preference"
        if motion and not hardware.motion_recommended:
            score -= 18
            reason += "; motion is expensive on this hardware tier"
        return score, reason

    def route(
        self,
        intent: MediaIntent,
        *,
        hardware: MediaHardwareBudget,
        reference_available: bool,
    ) -> WorkflowRoutingDecision:
        focus = set(intent_focus_tags(intent))
        candidates: list[WorkflowRouteCandidate] = []
        quarantined: list[str] = []
        rejected: list[str] = []

        for profile in self.profiles:
            capability = self.capabilities.get(profile.id)
            if not profile.enabled:
                rejected.append(f"{profile.id}: deaktiviert")
                continue
            if capability is None or not capability.runnable:
                rejected.append(f"{profile.id}: technisch nicht lauffähig")
                continue
            if intent.kind not in profile.kinds or intent.kind not in capability.runnable_kinds:
                rejected.append(f"{profile.id}: unterstützt {intent.kind} nicht")
                continue

            health = self.health.get(profile.id) if self.health is not None else WorkflowHealth(profile.id)
            if health.quarantined:
                quarantined.append(profile.id)
                rejected.append(f"{profile.id}: nach wiederholten Fehlern quarantänisiert")
                continue

            technical = workflow_suitability_score(
                capability,
                kind=intent.kind,
                reference_needed=reference_available,
            )
            checkpoint = profile.checkpoint_suitability.score_for(focus)
            checkpoint_points = int(round((checkpoint - 0.5) * 50))
            declared = set(profile.routing_tags)
            overlap = declared.intersection(focus)
            declared_points = len(overlap) * 10
            if declared and focus and not overlap:
                declared_points -= 5

            continuity_points = 0
            if intent.continuity_key:
                continuity_points += 24 if profile.prefer_for_character else 0
                if reference_available:
                    continuity_points += 18 if capability.reference_supported else -14
            elif profile.prefer_for_character:
                continuity_points -= 10

            hardware_points, hardware_reason = self._hardware_score(
                profile,
                hardware,
                motion=intent.kind != "image",
            )
            feedback_points = 0
            workflow_repetition = framing_repetition = 0
            if self.performance is not None:
                feedback_points = max(
                    -30,
                    min(30, self.performance.performance(profile.id, focus).score),
                )
                workflow_repetition, framing_repetition = self.performance.repetition_penalty(
                    profile.id,
                    intent.framing,
                )
            repetition_points = -(workflow_repetition + framing_repetition)

            components = {
                "priority": profile.priority,
                "technical": round(technical * 0.35),
                "checkpoint": checkpoint_points,
                "focus": declared_points,
                "continuity": continuity_points,
                "hardware": hardware_points,
                "feedback": feedback_points,
                "reliability": health.reliability_score,
                "anti_repetition": repetition_points,
            }
            total = sum(components.values())
            reasons = (
                f"technical suitability {technical}/100",
                f"checkpoint suitability {checkpoint:.2f} for {', '.join(sorted(focus)) or 'general'}",
                hardware_reason,
                (
                    f"local outcomes {health.successes} successful / {health.failures} failed"
                    if health.samples
                    else "no local runtime outcomes yet"
                ),
                (
                    f"recent-use penalty workflow {workflow_repetition}, framing {framing_repetition}"
                    if workflow_repetition or framing_repetition
                    else "no recent workflow/framing repetition"
                ),
            )
            candidates.append(
                WorkflowRouteCandidate(
                    profile=profile,
                    score=total,
                    suitability_score=technical,
                    components=components,
                    reasons=reasons,
                )
            )

        candidates.sort(key=lambda item: (-item.score, item.profile.id))
        return WorkflowRoutingDecision(
            requested_kind=intent.kind,
            focus_tags=tuple(sorted(focus)),
            candidates=tuple(candidates),
            quarantined_profile_ids=tuple(sorted(quarantined)),
            rejected=tuple(rejected),
        )


@dataclass(frozen=True, slots=True)
class MediaKindDecision:
    requested: str
    selected: str | None
    available: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "selected": self.selected,
            "available": list(self.available),
            "reason": self.reason,
        }


def select_media_kind(
    intent: MediaIntent,
    available_kinds: Iterable[str],
    *,
    hardware: MediaHardwareBudget,
    explicit_motion: bool,
) -> MediaKindDecision:
    """Resolve image/GIF/video without inventing unavailable local capabilities."""

    available = tuple(
        kind for kind in ("image", "gif", "video") if kind in set(available_kinds)
    )
    requested = intent.kind
    if not available:
        return MediaKindDecision(requested, None, (), "no validated local media kind")
    if (
        requested in {"gif", "video"}
        and not hardware.motion_recommended
        and not explicit_motion
        and "image" in available
    ):
        return MediaKindDecision(
            requested,
            "image",
            available,
            f"still image preferred for {hardware.tier} hardware budget",
        )
    if requested in available:
        return MediaKindDecision(requested, requested, available, "requested kind is validated")

    if requested == "video":
        order = ("gif", "image") if explicit_motion or hardware.motion_recommended else ("image", "gif")
    elif requested == "gif":
        order = ("video", "image") if explicit_motion or hardware.motion_recommended else ("image", "video")
    else:
        order = ("image", "gif", "video")
    selected = next((kind for kind in order if kind in available), None)
    return MediaKindDecision(
        requested,
        selected,
        available,
        f"{requested} unavailable; selected {selected or 'none'} from validated local profiles",
    )


@dataclass(frozen=True, slots=True)
class RenderFailurePolicy:
    category: str
    safe_to_fallback: bool
    degrade_quality: bool
    reason: str


def classify_render_failure(error: Exception) -> RenderFailurePolicy:
    """Allow fallback only when another queue operation cannot duplicate unknown work."""

    stage = str(getattr(error, "stage", "")).casefold()
    detail = str(error).casefold()
    resource_markers = (
        "out of memory",
        "cuda oom",
        "not enough memory",
        "allocate memory",
        "allocation failed",
        "vram",
    )
    if any(marker in detail for marker in resource_markers):
        return RenderFailurePolicy("resources", True, True, "VRAM/RAM render failure")
    if stage in {"queue", "history", "output download", "timeout"}:
        return RenderFailurePolicy(
            "ambiguous",
            False,
            False,
            f"{stage} may represent an accepted or completed render",
        )
    if stage == "execution" or "execution failed" in detail or "render failed" in detail:
        return RenderFailurePolicy("render", True, True, "confirmed render failure")
    if stage in {"prepare", "reference_upload"}:
        return RenderFailurePolicy("configuration", True, False, "pre-queue failure")
    if "queue" in detail or "timed out" in detail or "timeout" in detail:
        return RenderFailurePolicy("ambiguous", False, False, "queue state is ambiguous")
    return RenderFailurePolicy("workflow", True, False, "failure occurred before a known output")
