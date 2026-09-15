from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import httpx

from app.media.comfyui import ComfyUIClient, GeneratedMedia
from app.media.continuity import CharacterProfile
from app.media.hardware import ComfyUIHardwareProbe, MediaHardwareBudget
from app.media.planner import MediaIntent
from app.media.profiles import WorkflowProfile
from app.media.rendering import MediaRenderCalculator, MediaRenderPlan
from app.memory.store import StateStore
from app.settings import AppSettings

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class CharacterContinuityLabError(RuntimeError):
    """Raised when the local continuity suite cannot run safely."""


@dataclass(frozen=True, slots=True)
class CharacterContinuityProbe:
    id: str
    label: str
    focus_tag: str
    seed_offset: int
    direction: str
    intent: MediaIntent


@dataclass(frozen=True, slots=True)
class CharacterContinuityResult:
    probe: CharacterContinuityProbe
    generated: GeneratedMedia
    render_plan: MediaRenderPlan
    media_id: int


ProgressCallback = Callable[[int, int, str], None]
ResultCallback = Callable[[CharacterContinuityResult], None]


def _intent(
    key: str,
    *,
    framing: str,
    theme: str,
    composition: str,
    camera_angle: str = "eye level",
) -> MediaIntent:
    return MediaIntent(
        generate=True,
        kind="image",
        mood="cinematic continuity calibration",
        theme=theme,
        visual_style="photographic adult editorial",
        wardrobe=[],
        intensity=0.35,
        continuity_key=key,
        reason="local character continuity calibration",
        framing=framing,
        camera_angle=camera_angle,
        lighting="controlled soft cinematic light",
        composition=composition,
        motion="",
    )


def default_character_continuity_probes(
    continuity_key: str,
) -> tuple[CharacterContinuityProbe, ...]:
    """Return small non-graphic scenes that stress identity across framing changes."""

    key = continuity_key.strip() or "persona-main"
    return (
        CharacterContinuityProbe(
            id="portrait",
            label="Portrait",
            focus_tag="portrait",
            seed_offset=0,
            direction=(
                "close portrait of the same clearly adult companion character, confident calm expression, "
                "dark tailored jacket, natural facial detail, simple neutral background"
            ),
            intent=_intent(
                key,
                framing="close-up portrait",
                theme="adult companion portrait continuity",
                composition="centered portrait composition",
            ),
        ),
        CharacterContinuityProbe(
            id="full_body",
            label="Ganzkörper",
            focus_tag="full_body",
            seed_offset=1,
            direction=(
                "full-body head-to-toe view of the same clearly adult companion character, balanced standing pose, "
                "dark tailored outfit and boots, clean studio floor, recognizable face and hair"
            ),
            intent=_intent(
                key,
                framing="full-body head-to-toe",
                theme="adult companion full-body continuity",
                composition="balanced full-length composition",
            ),
        ),
        CharacterContinuityProbe(
            id="environment",
            label="Szenenwechsel",
            focus_tag="environment",
            seed_offset=2,
            direction=(
                "the same clearly adult companion character seated in a moody private lounge, rain on the window, "
                "recognizable face, hair and proportions, cinematic environmental portrait"
            ),
            intent=_intent(
                key,
                framing="medium environmental portrait",
                theme="rainy private lounge continuity scene",
                composition="character anchored within a wider environment",
                camera_angle="slightly low eye-level angle",
            ),
        ),
    )


def _validated_reference(profile: CharacterProfile) -> Path:
    raw = str(profile.reference_media_path or "").strip()
    path = Path(raw).expanduser()
    if not raw or path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise CharacterContinuityLabError(
            "Für den Character ist noch kein nutzbares lokales Referenzbild festgelegt."
        )
    if not path.exists() or not path.is_file():
        raise CharacterContinuityLabError(
            f"Das festgelegte Character-Referenzbild fehlt: {path}"
        )
    return path


def _positive_prompt(character: CharacterProfile, probe: CharacterContinuityProbe) -> str:
    identity = " ".join(character.appearance_prompt.split())
    return (
        f"{probe.direction}, stable recurring identity, {identity}, "
        "clearly adult, consistent face, consistent hair, consistent body proportions, photographic detail"
    )


def _negative_prompt() -> str:
    return (
        "minor, child, teenager, explicit sex act, genitals, injury, gore, coercion, "
        "identity drift, different person, duplicate person, extra limbs, malformed anatomy, "
        "text, watermark, logo, blurry, low quality"
    )


def _record_result(
    store: StateStore,
    character: CharacterProfile,
    profile: WorkflowProfile,
    probe: CharacterContinuityProbe,
    generated: GeneratedMedia,
    render_plan: MediaRenderPlan,
) -> int:
    payload = probe.intent.model_dump(mode="json")
    payload.update(
        {
            "workflow_profile": profile.id,
            "workflow_checkpoint": profile.checkpoint_name,
            "workflow_focus_tags": ["character", probe.focus_tag],
            "workflow_declared_routing_tags": list(profile.routing_tags),
            "character_continuity_probe": probe.id,
            "character_reference_media_id": character.reference_media_id,
            "render_plan": render_plan.model_dump(mode="json"),
            "render_parameters_applied": list(generated.applied_render_parameters),
        }
    )
    return store.record_media_event(
        path=str(generated.path),
        kind=generated.kind,
        prompt_id=generated.prompt_id,
        seed=generated.seed,
        continuity_key=character.key,
        intent=payload,
    )


def run_character_continuity_suite(
    settings: AppSettings,
    workflow_profile: WorkflowProfile,
    character: CharacterProfile,
    store: StateStore,
    *,
    probes: Iterable[CharacterContinuityProbe] | None = None,
    hardware_budget: MediaHardwareBudget | None = None,
    http_client: httpx.Client | None = None,
    on_progress: ProgressCallback | None = None,
    on_result: ResultCallback | None = None,
) -> list[CharacterContinuityResult]:
    """Render a local reference-based continuity suite and persist normal media events."""

    if "image" not in workflow_profile.kinds:
        raise CharacterContinuityLabError("Das ausgewählte Workflow-Profil erzeugt keine Bilder.")
    if not workflow_profile.reference_configured:
        raise CharacterContinuityLabError(
            "Das ausgewählte Workflow-Profil besitzt keinen validierten Referenzbild-Eingang."
        )
    reference_path = _validated_reference(character)
    suite = tuple(probes or default_character_continuity_probes(character.key))
    if not suite:
        return []

    hardware = hardware_budget or ComfyUIHardwareProbe(settings.media_url).current()
    calculator = MediaRenderCalculator()
    client = ComfyUIClient(
        base_url=settings.media_url,
        output_dir=settings.output_path,
        timeout=240.0,
        poll_interval=0.25,
        client=http_client,
    )
    results: list[CharacterContinuityResult] = []
    mutable_character = character.model_copy(deep=True)
    try:
        for index, probe in enumerate(suite, start=1):
            if on_progress is not None:
                on_progress(index, len(suite), probe.label)
            plan = calculator.calculate(
                probe.intent,
                [],
                quality=workflow_profile.render_quality,
                max_megapixels=min(workflow_profile.max_megapixels or 0.55, 0.55),
                hardware_budget=hardware,
            )
            # Keep the identity seed family stable but avoid rendering the exact
            # same latent for every composition test.
            probe_seed = ((mutable_character.seed + probe.seed_offset) % (2**63 - 2)) + 1
            generated = client.generate(
                _positive_prompt(mutable_character, probe),
                _negative_prompt(),
                seed=probe_seed,
                reference_path=reference_path,
                profile=workflow_profile,
                render_plan=plan,
            )
            media_id = _record_result(
                store,
                mutable_character,
                workflow_profile,
                probe,
                generated,
                plan,
            )
            mutable_character.register_generation(str(generated.path))
            result = CharacterContinuityResult(
                probe=probe,
                generated=generated,
                render_plan=plan,
                media_id=media_id,
            )
            results.append(result)
            if on_result is not None:
                on_result(result)
    finally:
        client.close()

    store.save_character_profile(mutable_character)
    return results
