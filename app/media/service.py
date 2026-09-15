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
from app.media.coverage import VisualCoverageRepository
from app.media.hardware import ComfyUIHardwareProbe, MediaHardwareBudget
from app.media.planner import MediaIntent, MediaPlanner
from app.media.profiles import WorkflowProfile, choose_workflow_profile, load_workflow_catalog
from app.media.prompting import build_visual_prompt
from app.media.rendering import MediaRenderCalculator, MediaRenderPlan
from app.media.workflow_routing import WorkflowPerformanceRepository, intent_focus_tags
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
        return [
            profile
            for profile in self.workflow_profiles
            if (capability := self.workflow_capabilities.get(profile.id)) is not None
            and capability.runnable
        ]

    def _runnable_profile_kinds(self) -> set[str]:
        return runnable_kinds(list(self.workflow_capabilities.values()))

    @property
    def enabled(self) -> bool:
        has_profile = bool(self._runnable_profiles())
        return self.settings.media_enabled and (self.backend.enabled or has_profile)

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

    def _select_workflow_profile(
        self,
        intent: MediaIntent,
        *,
        continuity_key: str | None,
        reference_path: Path | None,
    ) -> WorkflowProfile | None:
        profiles = self._runnable_profiles()
        if not profiles:
            return None
        reference_supported_ids = {
            capability.profile_id
            for capability in self.workflow_capabilities.values()
            if capability.runnable and capability.reference_supported
        }
        focus_tags = set(intent_focus_tags(intent))
        performance_scores = (
            self.workflow_performance.scores(
                (profile.id for profile in profiles),
                focus_tags,
            )
            if self.workflow_performance is not None
            else {}
        )
        return choose_workflow_profile(
            profiles,
            kind=intent.kind,
            character_focus=bool(continuity_key),
            reference_available=reference_path is not None,
            reference_supported_ids=reference_supported_ids,
            focus_tags=focus_tags,
            performance_scores=performance_scores,
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
    ) -> MediaRenderPlan:
        quality = workflow_profile.render_quality if workflow_profile is not None else "balanced"
        max_megapixels = workflow_profile.max_megapixels if workflow_profile is not None else None
        return self.render_calculator.calculate(
            intent,
            [item for item in preference_tags],
            quality=quality,
            max_megapixels=max_megapixels,
            hardware_budget=self.hardware_budget(),
        )

    def generate_for_exchange(
        self,
        *,
        user_text: str,
        assistant_text: str,
        persona: PersonaState,
        preference_tags: Iterable[str] = (),
    ) -> MediaResult | None:
        preference_list = [item for item in preference_tags]
        intent = self.plan(
            user_text=user_text,
            assistant_text=assistant_text,
            persona=persona,
            preference_tags=preference_list,
        )
        if not intent.generate:
            return None

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
        workflow_profile = self._select_workflow_profile(
            intent,
            continuity_key=continuity_key,
            reference_path=reference_path,
        )
        if workflow_profile is not None and reference_path is not None:
            capability = self.workflow_capabilities.get(workflow_profile.id)
            if capability is None or not capability.reference_supported:
                reference_path = None
        elif workflow_profile is None and reference_path is not None:
            if not self.backend.reference_configured:
                reference_path = None

        # With a configured catalog, a missing profile is a validated routing
        # failure, not an invitation to queue the wrong legacy workflow.
        if self.settings.profile_catalog_path is not None and workflow_profile is None:
            return None

        render_plan = self.calculate_render_plan(
            intent,
            preference_list,
            workflow_profile=workflow_profile,
        )

        try:
            generated = self.backend.generate(
                positive,
                negative,
                seed=seed,
                reference_path=reference_path,
                profile=workflow_profile,
                render_plan=render_plan,
            )
        except ComfyUIError:
            return None

        if character_profile is not None and self.store is not None:
            character_profile.register_generation(str(generated.path))
            self.store.save_character_profile(character_profile)

        history_id = None
        if self.store is not None:
            intent_payload = intent.model_dump(mode="json")
            focus_tags = list(intent_focus_tags(intent))
            intent_payload["workflow_focus_tags"] = focus_tags
            if workflow_profile is not None:
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
        )
