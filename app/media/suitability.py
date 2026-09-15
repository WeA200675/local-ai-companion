from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from app.media.comfyui import ComfyUIClient, GeneratedMedia
from app.media.hardware import ComfyUIHardwareProbe, MediaHardwareBudget
from app.media.planner import MediaIntent
from app.media.profiles import WorkflowProfile
from app.media.rendering import MediaRenderCalculator, MediaRenderPlan
from app.memory.store import StateStore
from app.settings import AppSettings


@dataclass(frozen=True, slots=True)
class SuitabilityProbe:
    id: str
    label: str
    focus_tag: str
    seed: int
    positive: str
    negative: str
    intent: MediaIntent


@dataclass(frozen=True, slots=True)
class SuitabilityProbeResult:
    probe: SuitabilityProbe
    generated: GeneratedMedia
    render_plan: MediaRenderPlan
    media_id: int


ProgressCallback = Callable[[int, int, str], None]
ResultCallback = Callable[[SuitabilityProbeResult], None]


def _intent(*, framing: str, theme: str, composition: str) -> MediaIntent:
    return MediaIntent(
        generate=True,
        kind="image",
        mood="cinematic editorial",
        theme=theme,
        visual_style="photographic adult editorial",
        wardrobe=[],
        intensity=0.35,
        continuity_key=None,
        reason="local workflow suitability probe",
        framing=framing,
        camera_angle="eye level",
        lighting="controlled soft studio light",
        composition=composition,
        motion="",
    )


def default_suitability_probes() -> tuple[SuitabilityProbe, ...]:
    """Small non-graphic render suite for different composition jobs."""

    shared_negative = (
        "minor, child, explicit sex act, nudity, genitals, injury, gore, coercion, "
        "text, watermark, logo, blurry, low quality, malformed anatomy, extra limbs"
    )
    return (
        SuitabilityProbe(
            id="portrait",
            label="Portrait",
            focus_tag="portrait",
            seed=5101,
            positive=(
                "clearly adult woman, cinematic close portrait, confident expression, "
                "black leather jacket, natural skin detail, controlled studio lighting, photographic"
            ),
            negative=shared_negative,
            intent=_intent(
                framing="close-up portrait",
                theme="adult portrait studio",
                composition="centered portrait composition",
            ),
        ),
        SuitabilityProbe(
            id="full_body",
            label="Ganzkörper",
            focus_tag="full_body",
            seed=5102,
            positive=(
                "clearly adult woman, full-body fashion editorial, head-to-toe framing, boots fully visible, "
                "balanced pose, black leather outfit, clean studio floor, photographic"
            ),
            negative=shared_negative,
            intent=_intent(
                framing="full-body head-to-toe",
                theme="adult fashion studio",
                composition="full-length balanced composition",
            ),
        ),
        SuitabilityProbe(
            id="detail",
            label="Materialdetail",
            focus_tag="detail",
            seed=5103,
            positive=(
                "macro editorial material study, black leather glove, polished metal buckle, stitching and texture, "
                "dramatic soft highlights, high detail, photographic product-style close-up"
            ),
            negative=shared_negative,
            intent=_intent(
                framing="macro material detail",
                theme="leather and metal material study",
                composition="tight detail composition",
            ),
        ),
        SuitabilityProbe(
            id="environment",
            label="Umgebung",
            focus_tag="environment",
            seed=5104,
            positive=(
                "moody private lounge interior, empty chair, rain on tall window, reflective dark floor, "
                "cinematic practical lighting, wide establishing composition, photographic"
            ),
            negative=shared_negative,
            intent=_intent(
                framing="wide establishing shot",
                theme="dark private lounge environment",
                composition="wide environment composition",
            ),
        ),
    )


def _record_result(
    store: StateStore,
    profile: WorkflowProfile,
    probe: SuitabilityProbe,
    generated: GeneratedMedia,
    render_plan: MediaRenderPlan,
) -> int:
    payload = probe.intent.model_dump(mode="json")
    payload.update(
        {
            "workflow_profile": profile.id,
            "workflow_checkpoint": profile.checkpoint_name,
            "workflow_focus_tags": [probe.focus_tag],
            "workflow_declared_routing_tags": list(profile.routing_tags),
            "suitability_probe": probe.id,
            "render_plan": render_plan.model_dump(mode="json"),
            "render_parameters_applied": list(generated.applied_render_parameters),
        }
    )
    return store.record_media_event(
        path=str(generated.path),
        kind=generated.kind,
        prompt_id=generated.prompt_id,
        seed=generated.seed,
        continuity_key=None,
        intent=payload,
    )


def run_suitability_suite(
    settings: AppSettings,
    profile: WorkflowProfile,
    store: StateStore,
    *,
    probes: Iterable[SuitabilityProbe] | None = None,
    hardware_budget: MediaHardwareBudget | None = None,
    on_progress: ProgressCallback | None = None,
    on_result: ResultCallback | None = None,
) -> list[SuitabilityProbeResult]:
    """Render a small local suite and record each result for explicit feedback."""

    suite = tuple(probes or default_suitability_probes())
    if not suite:
        return []
    hardware = hardware_budget or ComfyUIHardwareProbe(settings.media_url).current()
    calculator = MediaRenderCalculator()
    client = ComfyUIClient(
        base_url=settings.media_url,
        output_dir=settings.output_path,
        timeout=240.0,
        poll_interval=0.25,
    )
    results: list[SuitabilityProbeResult] = []
    try:
        for index, probe in enumerate(suite, start=1):
            if on_progress is not None:
                on_progress(index, len(suite), probe.label)
            plan = calculator.calculate(
                probe.intent,
                [],
                quality="draft",
                max_megapixels=0.45,
                hardware_budget=hardware,
            )
            generated = client.generate(
                probe.positive,
                probe.negative,
                seed=probe.seed,
                profile=profile,
                render_plan=plan,
            )
            media_id = _record_result(store, profile, probe, generated, plan)
            result = SuitabilityProbeResult(
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
    return results
