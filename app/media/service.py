from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.ai.creative_accents import default_detail_accents, default_mood_grades
from app.ai.look_presets import default_look_presets
from app.ai.model import ChatMessage, LocalModelError, OllamaClient
from app.ai.persona import PersonaState
from app.ai.scene_mixer import ATMOSPHERES, COMPOSITIONS, LIGHTING, SETTINGS
from app.ai.visual_motifs import default_visual_motifs
from app.media.capabilities import WorkflowCapability, inspect_workflow_catalog, runnable_kinds
from app.media.comfyui import ComfyUIClient, ComfyUIError, GeneratedMedia
from app.media.comfyui_runtime import VisibleMediaBackendError
from app.media.coverage import VisualCoverageRepository
from app.media.hardware import ComfyUIHardwareProbe, MediaHardwareBudget
from app.media.planner import MediaIntent, MediaPlanner
from app.media.profiles import RenderQuality, WorkflowProfile, load_workflow_catalog
from app.media.prompting import build_visual_prompt
from app.media.rendering import MediaRenderCalculator, MediaRenderPlan
from app.media.workflow_routing import (
    WorkflowHealthRepository,
    WorkflowPerformanceRepository,
    WorkflowRouter,
    WorkflowRoutingDecision,
    classify_render_failure,
    intent_focus_tags,
    select_media_kind,
)
from app.memory.store import StateStore
from app.settings import AppSettings

_IMAGE_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_MOTION_REQUEST_TOKENS = (
    "video",
    "gif",
    "animation",
    "animiert",
    "bewegtes bild",
    "bewegung",
    "motion",
    "loop",
    "clip",
)


@dataclass(frozen=True, slots=True)
class MediaResult:
    intent: MediaIntent
    generated: GeneratedMedia
    history_id: int | None = None
    workflow_profile: str | None = None
    render_plan: MediaRenderPlan | None = None
    routing_decision: WorkflowRoutingDecision | None = None
    routing_attempts: tuple[dict[str, object], ...] = ()

    @property
    def path(self) -> Path:
        return self.generated.path


class MediaService:
    """Coordinates local visual planning, capability routing and generation."""

    def __init__(
        self,
        model: OllamaClient,
        backend: ComfyUIClient,
        *,
        store: StateStore | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.model = model
        self.backend = backend
        self.store = store
        self.settings = settings or AppSettings()
        self.planner = MediaPlanner()
        self.render_calculator = MediaRenderCalculator()
        self.hardware_probe = ComfyUIHardwareProbe(self.settings.media_url)
        self.coverage = VisualCoverageRepository(store) if store is not None else None
        self.workflow_performance = (
            WorkflowPerformanceRepository(
                store,
                history_limit=self.settings.media_history_limit,
            )
            if store is not None
            else None
        )
        self.workflow_health = (
            WorkflowHealthRepository(store) if store is not None else None
        )
        self.workflow_profiles: list[WorkflowProfile] = []
        self.workflow_capabilities: dict[str, WorkflowCapability] = {}
        if self.settings.profile_catalog_path is not None:
            try:
                catalog = load_workflow_catalog(self.settings.profile_catalog_path)
                self.workflow_profiles = catalog.profiles
                self.workflow_capabilities = {
                    item.profile_id: item for item in inspect_workflow_catalog(catalog)
                }
            except (OSError, ValueError):
                self.workflow_profiles = []
                self.workflow_capabilities = {}

    def _runnable_profiles(self) -> list[WorkflowProfile]:
        if not self.workflow_profiles:
            return []
        profiles: list[WorkflowProfile] = []
        for profile in self.workflow_profiles:
            capability = self.workflow_capabilities.get(profile.id)
            if capability is None or not capability.runnable:
                continue
            if (
                self.workflow_health is not None
                and self.workflow_health.get(profile.id).quarantined
            ):
                continue
            profiles.append(profile)
        return profiles

    def _runnable_profile_kinds(self) -> set[str]:
        profile_ids = {profile.id for profile in self._runnable_profiles()}
        return runnable_kinds(
            [
                capability
                for profile_id, capability in self.workflow_capabilities.items()
                if profile_id in profile_ids
            ]
        )

    @property
    def enabled(self) -> bool:
        has_profile = bool(self._runnable_profiles())
        return self.settings.media_enabled and (self.backend.enabled or has_profile)

    @property
    def available_media_kinds(self) -> tuple[str, ...]:
        kinds = self._runnable_profile_kinds()
        if kinds:
            return tuple(kind for kind in ("image", "gif", "video") if kind in kinds)
        return ("image",) if self.backend.enabled else ()

    def close(self) -> None:
        self.backend.close()

    def _active_conversation_id(self) -> str:
        if self.store is None:
            return "main"
        value = self.store._load_app_state("active_conversation_id")  # noqa: SLF001
        return value.strip() if value and value.strip() else "main"

    def _visual_cues(self, limit: int = 8) -> tuple[list[str], list[str]]:
        if self.store is None:
            return [], []
        profile = self.store.load_visual_preferences()
        liked = [
            cue
            for cue in profile.top_liked(limit * 2)
            if profile.liked.get(cue, 0) > profile.disliked.get(cue, 0)
        ][:limit]
        disliked = [
            cue
            for cue in profile.top_disliked(limit * 2)
            if profile.disliked.get(cue, 0) > profile.liked.get(cue, 0)
        ][:limit]
        return liked, disliked

    @staticmethod
    def _usable_reference(path_value: object) -> Path | None:
        path = Path(str(path_value or "")).expanduser()
        if path.suffix.lower() not in _IMAGE_REFERENCE_SUFFIXES:
            return None
        if not path.exists() or not path.is_file():
            return None
        return path

    @staticmethod
    def _explicit_motion_request(user_text: str) -> bool:
        text = " ".join(user_text.casefold().split())
        return any(token in text for token in _MOTION_REQUEST_TOKENS)

    def hardware_budget(self) -> MediaHardwareBudget:
        return self.hardware_probe.current()

    def _reference_path(self, continuity_key: str | None) -> Path | None:
        """Prefer a pinned anchor, then fall back to the newest liked local image."""

        if (
            not continuity_key
            or not self.settings.media_reference_enabled
            or self.store is None
        ):
            return None

        profile = self.store.load_character_profile(continuity_key)
        pinned = self._usable_reference(profile.reference_media_path)
        if pinned is not None:
            return pinned

        for event in self.store.list_media_events(limit=self.settings.media_history_limit):
            if event.get("continuity_key") != continuity_key:
                continue
            if event.get("feedback") != "positive":
                continue
            fallback = self._usable_reference(event.get("path"))
            if fallback is not None:
                return fallback
        return None

    def _route_workflow_profiles(
        self,
        intent: MediaIntent,
        *,
        continuity_key: str | None,
        reference_path: Path | None,
    ) -> WorkflowRoutingDecision:
        routed_intent = intent.model_copy(update={"continuity_key": continuity_key})
        router = WorkflowRouter(
            self.workflow_profiles,
            self.workflow_capabilities,
            performance=self.workflow_performance,
            health=self.workflow_health,
        )
        return router.route(
            routed_intent,
            hardware=self.hardware_budget(),
            reference_available=reference_path is not None,
        )

    def _select_workflow_profile(
        self,
        intent: MediaIntent,
        *,
        continuity_key: str | None,
        reference_path: Path | None,
    ) -> WorkflowProfile | None:
        """Compatibility wrapper for callers that only need the primary route."""

        decision = self._route_workflow_profiles(
            intent,
            continuity_key=continuity_key,
            reference_path=reference_path,
        )
        return decision.selected.profile if decision.selected is not None else None

    def diagnose_routing(self, intent: MediaIntent) -> WorkflowRoutingDecision:
        """Explain which profile would be selected without starting a render."""

        continuity_key = intent.continuity_key if self.settings.continuity_enabled else None
        return self._route_workflow_profiles(
            intent,
            continuity_key=continuity_key,
            reference_path=self._reference_path(continuity_key),
        )

    def record_workflow_probe(
        self,
        profile_id: str,
        *,
        succeeded: bool,
        error: str = "",
    ) -> None:
        """Update quarantine state after an explicit local workflow test."""

        if self.workflow_health is None:
            return
        if profile_id not in {profile.id for profile in self.workflow_profiles}:
            raise KeyError(f"Unknown workflow profile: {profile_id}")
        self.workflow_health.record_probe(
            profile_id,
            succeeded=succeeded,
            error=error,
        )

    @staticmethod
    def _match_by_tags(items: Iterable[object], tags: set[str]) -> object | None:
        best = None
        best_score = 0
        for item in items:
            style_tags = getattr(item, "style_tags", [])
            score = sum(1 for tag in style_tags if str(tag).strip().casefold() in tags)
            if score > best_score:
                best = item
                best_score = score
        return best if best_score > 0 else None

    def _record_visual_coverage(self, kind: str, preference_tags: list[str]) -> None:
        if self.coverage is None:
            return
        conversation_id = self._active_conversation_id()
        tags = {
            item.strip().casefold()
            for item in preference_tags
            if item.strip() and not item.strip().casefold().startswith("avoid:")
        }

        look = self._match_by_tags(default_look_presets(), tags)
        setting = self._match_by_tags(SETTINGS, tags)
        lighting = self._match_by_tags(LIGHTING, tags)
        composition = self._match_by_tags(COMPOSITIONS, tags)
        atmosphere = self._match_by_tags(ATMOSPHERES, tags)
        motif = self._match_by_tags(default_visual_motifs(), tags)
        mood = self._match_by_tags(default_mood_grades(), tags)
        detail = self._match_by_tags(default_detail_accents(), tags)

        scene_mix = None
        if any(item is not None for item in (setting, lighting, composition, atmosphere)):
            components = {
                "setting": getattr(setting, "id", ""),
                "lighting": getattr(lighting, "id", ""),
                "composition": getattr(composition, "id", ""),
                "atmosphere": getattr(atmosphere, "id", ""),
            }
            from app.ai.scene_mixer import SceneMix

            scene_mix = SceneMix(
                signature=":".join(components.values()),
                title="coverage snapshot",
                context="",
                component_ids={key: value for key, value in components.items() if value},
            )

        self.coverage.record(
            conversation_id,
            kind=kind,
            look_id=getattr(look, "id", None),
            scene_mix=scene_mix,
            motif_id=getattr(motif, "id", None),
            mood_id=getattr(mood, "id", None),
            detail_id=getattr(detail, "id", None),
        )

    def plan(
        self,
        *,
        user_text: str,
        assistant_text: str,
        persona: PersonaState,
        preference_tags: Iterable[str] = (),
    ) -> MediaIntent:
        if not self.enabled:
            return MediaIntent(generate=False, reason="media backend disabled")

        tags = [tag.strip() for tag in preference_tags if tag.strip()]
        liked_cues, disliked_cues = self._visual_cues()
        hardware = self.hardware_budget()
        coverage_guidance = ""
        if self.coverage is not None:
            coverage_guidance = self.coverage.guidance(self._active_conversation_id())

        has_catalog = self.settings.profile_catalog_path is not None
        available_profile_kinds = sorted(self._runnable_profile_kinds())
        if has_catalog:
            available_text = ", ".join(available_profile_kinds) if available_profile_kinds else "none"
        else:
            available_text = "legacy workflow (media kind is not declared)"
        motion_rule = (
            "Motion is locally reasonable for this hardware when it materially improves the moment."
            if hardware.motion_recommended
            else "Prefer a still image on this hardware unless the current user explicitly asks for motion."
        )
        planner_prompt = f"""You are the visual director for a private local adult companion app.
Return exactly one JSON object matching this schema:
{{
  "generate": boolean,
  "kind": "image" | "gif" | "video",
  "mood": string,
  "theme": string,
  "visual_style": string,
  "wardrobe": [string],
  "intensity": number from 0 to 1,
  "continuity_key": string or null,
  "reason": string,
  "framing": string,
  "camera_angle": string,
  "lighting": string,
  "composition": string,
  "motion": string
}}

Decide whether a visual would genuinely improve this specific exchange. Prefer image unless motion materially improves the moment.
Validated local workflow capabilities: {available_text}.
If a profile catalog is configured, choose only a media kind listed as validated above.
Local render hardware: {hardware.summary()}.
{motion_rule}
When generate is true, make concrete visual-direction choices instead of vague style prose: choose framing, camera angle, lighting, composition, wardrobe/material cues, and a restrained motion cue for GIF/video.
Keep every depicted person clearly adult. Visuals may be provocative, fetish-inspired, dominant, teasing, sensual, or dark, but do not plan graphic sexual acts, genital-focused imagery, minors, coercive violence, gore, or injury.
Use historical image feedback and local coverage only as soft visual guidance; the user's current request and explicit creative context take priority.
When the recurring companion character is depicted and continuity is enabled, use continuity_key "{self.settings.continuity_key}". Otherwise use null.
Do not include prose outside the JSON object."""
        context = (
            f"Persona name: {persona.name}\n"
            f"Dominance: {persona.dominance.current:.2f}\n"
            f"Strictness: {persona.strictness.current:.2f}\n"
            f"Teasing: {persona.teasing.current:.2f}\n"
            f"Creativity: {persona.creativity.current:.2f}\n"
            f"Visual continuity enabled: {self.settings.continuity_enabled}\n"
            f"Validated media kinds: {available_text}\n"
            f"Local hardware budget: {hardware.summary()}\n"
            f"Preference tags: {', '.join(tags[:24]) if tags else 'none'}\n"
            f"Historically liked visual cues: {', '.join(liked_cues) if liked_cues else 'none yet'}\n"
            f"Historically disliked visual cues: {', '.join(disliked_cues) if disliked_cues else 'none yet'}\n"
            f"Visual coverage guidance: {coverage_guidance or 'none yet'}\n\n"
            f"User message:\n{user_text}\n\n"
            f"Companion reply:\n{assistant_text}"
        )
        try:
            payload = self.model.chat_json(
                [ChatMessage(role="user", content=context)],
                system_prompt=planner_prompt,
                temperature=0.2,
            )
            intent = self.planner.from_model_payload(payload)
            if not self.settings.continuity_enabled and intent.continuity_key:
                intent = intent.model_copy(update={"continuity_key": None})

            if has_catalog and intent.generate and intent.kind not in available_profile_kinds:
                explicit_motion = self._explicit_motion_request(user_text)
                if "image" in available_profile_kinds and not explicit_motion:
                    reason = intent.reason.strip()
                    suffix = f"image selected because {intent.kind} has no validated local workflow"
                    intent = intent.model_copy(
                        update={
                            "kind": "image",
                            "motion": "",
                            "reason": f"{reason}; {suffix}" if reason else suffix,
                        }
                    )
                else:
                    return intent.model_copy(
                        update={
                            "generate": False,
                            "reason": (
                                f"requested media kind {intent.kind!r} has no validated local workflow"
                            ),
                        }
                    )

            if (
                intent.kind != "image"
                and not hardware.motion_recommended
                and not self._explicit_motion_request(user_text)
            ):
                reason = intent.reason.strip()
                suffix = f"still selected for local {hardware.tier} hardware budget"
                intent = intent.model_copy(
                    update={
                        "kind": "image",
                        "motion": "",
                        "reason": f"{reason}; {suffix}" if reason else suffix,
                    }
                )
            return intent
        except (LocalModelError, ValueError):
            return MediaIntent(generate=False, reason="planner failed")

    def calculate_render_plan(
        self,
        intent: MediaIntent,
        preference_tags: Iterable[str] = (),
        *,
        workflow_profile: WorkflowProfile | None = None,
        quality_override: RenderQuality | None = None,
    ) -> MediaRenderPlan:
        quality = quality_override or (
            workflow_profile.render_quality if workflow_profile is not None else "balanced"
        )
        max_megapixels = workflow_profile.max_megapixels if workflow_profile is not None else None
        plan = self.render_calculator.calculate(
            intent,
            [item for item in preference_tags],
            quality=quality,
            max_megapixels=max_megapixels,
            hardware_budget=self.hardware_budget(),
        )
        if intent.kind == "image" or workflow_profile is None:
            return plan

        frames = plan.frames
        fps = plan.fps
        rationale = list(plan.rationale)
        if (
            workflow_profile.max_motion_frames is not None
            and frames > workflow_profile.max_motion_frames
        ):
            frames = max(8, workflow_profile.max_motion_frames)
            rationale.append(
                f"profile {workflow_profile.id} capped motion at {frames} frames"
            )
        if workflow_profile.max_motion_fps is not None and fps > workflow_profile.max_motion_fps:
            fps = workflow_profile.max_motion_fps
            rationale.append(f"profile {workflow_profile.id} capped motion at {fps} fps")
        if frames == plan.frames and fps == plan.fps:
            return plan
        frame_factor = max(1.0, frames / 8.0)
        return plan.model_copy(
            update={
                "frames": frames,
                "fps": fps,
                "duration_seconds": round(frames / fps, 2),
                "estimated_work_units": round(
                    plan.megapixels * plan.steps * frame_factor,
                    2,
                ),
                "rationale": rationale,
            }
        )

    def generate_for_exchange(
        self,
        *,
        user_text: str,
        assistant_text: str,
        persona: PersonaState,
        preference_tags: Iterable[str] = (),
        forced_intent: MediaIntent | None = None,
    ) -> MediaResult | None:
        preference_list = [item for item in preference_tags]
        intent = forced_intent or self.plan(
            user_text=user_text,
            assistant_text=assistant_text,
            persona=persona,
            preference_tags=preference_list,
        )
        if not intent.generate:
            return None

        hardware = self.hardware_budget()
        kind_decision = select_media_kind(
            intent,
            self.available_media_kinds,
            hardware=hardware,
            explicit_motion=self._explicit_motion_request(user_text),
        )
        if kind_decision.selected is None:
            return None
        if kind_decision.selected != intent.kind:
            intent = intent.model_copy(
                update={
                    "kind": kind_decision.selected,
                    "motion": "" if kind_decision.selected == "image" else intent.motion,
                    "reason": (
                        f"{intent.reason}; {kind_decision.reason}"
                        if intent.reason.strip()
                        else kind_decision.reason
                    ),
                }
            )

        positive, negative = build_visual_prompt(intent, persona, preference_list)
        liked_cues, disliked_cues = self._visual_cues(limit=6)
        if liked_cues:
            positive = f"{positive}, preferred visual cues: {', '.join(liked_cues)}"
        if disliked_cues:
            negative = f"{negative}, user-disliked visual cues: {', '.join(disliked_cues)}"

        continuity_key = intent.continuity_key if self.settings.continuity_enabled else None
        character_profile = None
        seed = None
        if continuity_key and self.store is not None:
            character_profile = self.store.load_character_profile(continuity_key)
            seed = character_profile.seed
            positive = f"{positive}, {character_profile.appearance_prompt}"

        reference_path = self._reference_path(continuity_key)
        routing = self._route_workflow_profiles(
            intent,
            continuity_key=continuity_key,
            reference_path=reference_path,
        )
        if self.settings.profile_catalog_path is not None and routing.selected is None:
            return None

        # A catalog-free installation keeps the historical single-workflow path.
        candidates = routing.candidates or (None,)
        generated: GeneratedMedia | None = None
        workflow_profile: WorkflowProfile | None = None
        render_plan: MediaRenderPlan | None = None
        attempts: list[dict[str, object]] = []
        last_visible_error: VisibleMediaBackendError | None = None
        unsafe_failure = False

        for candidate in candidates:
            profile = candidate.profile if candidate is not None else None
            quality_attempts = profile.quality_attempts() if profile is not None else ("balanced",)
            seen_effective_quality: set[str] = set()
            candidate_error: Exception | None = None
            candidate_policy = None
            profile_reference = reference_path
            if profile_reference is not None and profile is not None:
                capability = self.workflow_capabilities.get(profile.id)
                if capability is None or not capability.reference_supported:
                    profile_reference = None
            elif profile_reference is not None and profile is None:
                if not self.backend.reference_configured:
                    profile_reference = None

            for quality in quality_attempts:
                render_plan = self.calculate_render_plan(
                    intent,
                    preference_list,
                    workflow_profile=profile,
                    quality_override=quality,
                )
                if render_plan.quality in seen_effective_quality:
                    continue
                seen_effective_quality.add(render_plan.quality)
                try:
                    generated = self.backend.generate(
                        positive,
                        negative,
                        seed=seed,
                        reference_path=profile_reference,
                        profile=profile,
                        render_plan=render_plan,
                    )
                except (ComfyUIError, VisibleMediaBackendError) as exc:
                    last_visible_error = (
                        exc if isinstance(exc, VisibleMediaBackendError) else last_visible_error
                    )
                    candidate_error = exc
                    candidate_policy = classify_render_failure(exc)
                    attempts.append(
                        {
                            "profile_id": profile.id if profile is not None else "legacy",
                            "quality": render_plan.quality,
                            "status": "failed",
                            "category": candidate_policy.category,
                            "safe_to_fallback": candidate_policy.safe_to_fallback,
                            "error": str(exc),
                        }
                    )
                    if not candidate_policy.safe_to_fallback:
                        unsafe_failure = True
                        break
                    if not candidate_policy.degrade_quality:
                        break
                    continue
                else:
                    attempts.append(
                        {
                            "profile_id": profile.id if profile is not None else "legacy",
                            "quality": render_plan.quality,
                            "status": "success",
                        }
                    )
                    workflow_profile = profile
                    if profile is not None and self.workflow_health is not None:
                        self.workflow_health.record_success(profile.id)
                    break

            if generated is not None or unsafe_failure:
                break
            if profile is not None and candidate_error is not None and self.workflow_health is not None:
                self.workflow_health.record_failure(
                    profile.id,
                    str(candidate_error),
                    threshold=profile.quarantine_failures,
                    confirmed=bool(candidate_policy and candidate_policy.safe_to_fallback),
                )

        if generated is None or render_plan is None:
            if last_visible_error is not None:
                raise last_visible_error
            return None

        if character_profile is not None and self.store is not None:
            character_profile.register_generation(str(generated.path))
            self.store.save_character_profile(character_profile)

        history_id = None
        if self.store is not None:
            intent_payload = intent.model_dump(mode="json")
            focus_tags = list(intent_focus_tags(intent))
            intent_payload["workflow_focus_tags"] = focus_tags
            intent_payload["media_kind_decision"] = kind_decision.as_dict()
            intent_payload["routing_decision"] = routing.as_dict()
            intent_payload["routing_attempts"] = attempts
            explanation = routing.explain()
            if workflow_profile is not None and routing.selected is not None:
                if workflow_profile.id != routing.selected.profile.id:
                    explanation += f" Primärprofil fehlgeschlagen; Fallback {workflow_profile.id} war erfolgreich."
                intent_payload["workflow_profile"] = workflow_profile.id
                intent_payload["workflow_checkpoint"] = workflow_profile.checkpoint_name
                intent_payload["workflow_declared_routing_tags"] = list(
                    workflow_profile.routing_tags
                )
                if self.workflow_performance is not None:
                    performance = self.workflow_performance.performance(
                        workflow_profile.id,
                        focus_tags,
                    )
                    intent_payload["workflow_feedback_score_before"] = performance.score
                    intent_payload["workflow_feedback_samples_before"] = performance.samples
                capability = self.workflow_capabilities.get(workflow_profile.id)
                if capability is not None:
                    intent_payload["workflow_capabilities"] = {
                        "runnable_kinds": list(capability.runnable_kinds),
                        "reference_supported": capability.reference_supported,
                        "render_controls": list(capability.render_controls),
                        "output_evidence": list(capability.output_evidence),
                    }
            intent_payload["routing_explanation"] = explanation
            intent_payload["render_plan"] = render_plan.model_dump(mode="json")
            intent_payload["render_parameters_applied"] = list(
                generated.applied_render_parameters
            )
            history_id = self.store.record_media_event(
                path=str(generated.path),
                kind=generated.kind,
                prompt_id=generated.prompt_id,
                seed=generated.seed,
                continuity_key=continuity_key,
                intent=intent_payload,
            )
            self._record_visual_coverage(generated.kind, preference_list)

        return MediaResult(
            intent=intent,
            generated=generated,
            history_id=history_id,
            workflow_profile=workflow_profile.id if workflow_profile is not None else None,
            render_plan=render_plan,
            routing_decision=routing,
            routing_attempts=tuple(attempts),
        )
