from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

import httpx

from app.media.capabilities import WorkflowCapability, inspect_workflow_profile
from app.media.comfyui import ComfyUIClient, GeneratedMedia
from app.media.hardware import ComfyUIHardwareProbe, MediaHardwareBudget
from app.media.planner import MediaIntent
from app.media.profiles import WorkflowCatalog, WorkflowProfile, load_workflow_catalog
from app.media.rendering import MediaRenderCalculator, MediaRenderPlan
from app.media.workflow_inspector import WorkflowInspection, inspect_workflow_file
from app.settings import AppSettings


class MediaSetupError(RuntimeError):
    """Raised when automatic local media setup cannot continue safely."""


@dataclass(frozen=True, slots=True)
class WorkflowAutoSetup:
    workflow: Path
    inspection: WorkflowInspection
    profile: WorkflowProfile | None
    capability: WorkflowCapability | None
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return bool(
            self.inspection.complete
            and self.profile is not None
            and self.capability is not None
            and self.capability.runnable
        )

    @property
    def kinds(self) -> tuple[str, ...]:
        if self.profile is None:
            return ()
        return tuple(self.profile.kinds)


@dataclass(frozen=True, slots=True)
class WorkflowSmokeTestResult:
    generated: GeneratedMedia
    render_plan: MediaRenderPlan
    hardware: MediaHardwareBudget
    profile_id: str

    def summary(self) -> str:
        applied = ", ".join(self.generated.applied_render_parameters) or "Workflow-Defaults"
        return (
            f"Render erfolgreich: {self.generated.kind} · {self.render_plan.width}x{self.render_plan.height} · "
            f"{self.hardware.tier} · Parameter: {applied} · Datei: {self.generated.path}"
        )


def _profile_id(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.casefold()).strip("-")
    slug = slug[:56] or "workflow"
    return f"auto-{slug}"


def _infer_kinds(
    workflow: Path,
    inspection: WorkflowInspection,
) -> tuple[str, ...]:
    if not inspection.complete:
        return ()
    probe = WorkflowProfile(
        id="auto-probe",
        label="automatic capability probe",
        workflow=str(workflow),
        kinds=["image", "gif", "video"],
        positive_node=inspection.positive_node or "",
        negative_node=inspection.negative_node or "",
        seed_node=inspection.seed_node or "",
    )
    capability = inspect_workflow_profile(probe)
    if capability.output_evidence:
        return capability.output_evidence
    # Custom ComfyUI output nodes are impossible to classify perfectly without
    # executing them. Image is the safest fallback for a standard API workflow.
    return ("image",)


def inspect_for_auto_setup(path: str | Path) -> WorkflowAutoSetup:
    workflow = Path(path).expanduser()
    inspection = inspect_workflow_file(workflow)
    warnings = list(inspection.warnings)
    if not inspection.complete:
        return WorkflowAutoSetup(
            workflow=workflow,
            inspection=inspection,
            profile=None,
            capability=None,
            warnings=tuple(warnings),
        )

    kinds = _infer_kinds(workflow, inspection)
    profile = WorkflowProfile(
        id=_profile_id(workflow),
        label=f"Auto: {workflow.stem}",
        workflow=str(workflow.resolve()),
        kinds=list(kinds or ("image",)),
        positive_node=inspection.positive_node or "",
        negative_node=inspection.negative_node or "",
        seed_node=inspection.seed_node or "",
        priority=50,
        enabled=True,
        render_quality="balanced",
    )
    capability = inspect_workflow_profile(profile)
    warnings.extend(capability.warnings)
    if capability.error:
        warnings.append(capability.error)
    return WorkflowAutoSetup(
        workflow=workflow,
        inspection=inspection,
        profile=profile,
        capability=capability,
        warnings=tuple(dict.fromkeys(item for item in warnings if item)),
    )


def generated_catalog_path(settings: AppSettings) -> Path:
    output_parent = settings.output_path.parent
    return output_parent / "workflow_profiles.generated.json"


def save_generated_profile(
    setup: WorkflowAutoSetup,
    path: str | Path,
) -> Path:
    if not setup.ready or setup.profile is None:
        raise MediaSetupError("Workflow is not ready for automatic profile creation")
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        try:
            catalog = load_workflow_catalog(target)
        except (OSError, ValueError) as exc:
            raise MediaSetupError(
                f"Existing generated profile catalog is invalid and was not overwritten: {exc}"
            ) from exc
        profiles = [
            profile
            for profile in catalog.profiles
            if profile.id != setup.profile.id
        ]
        profiles.append(setup.profile)
        result = WorkflowCatalog(version=max(1, catalog.version), profiles=profiles)
    else:
        result = WorkflowCatalog(version=1, profiles=[setup.profile])

    payload = result.model_dump(mode="json")
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def _smoke_intent(kind: str) -> MediaIntent:
    motion = "slow subtle camera drift" if kind != "image" else ""
    return MediaIntent(
        generate=True,
        kind=kind if kind in {"image", "gif", "video"} else "image",
        mood="neutral diagnostic studio",
        theme="simple empty studio chair under soft light",
        visual_style="clean photographic test render",
        wardrobe=[],
        intensity=0.15,
        continuity_key=None,
        reason="local workflow smoke test",
        framing="portrait",
        camera_angle="eye level",
        lighting="soft studio light",
        composition="centered simple composition",
        motion=motion,
    )


def run_workflow_smoke_test(
    settings: AppSettings,
    setup: WorkflowAutoSetup,
    *,
    hardware_budget: MediaHardwareBudget | None = None,
    http_client: httpx.Client | None = None,
) -> WorkflowSmokeTestResult:
    if not setup.ready or setup.profile is None:
        raise MediaSetupError("Workflow is not ready for a render smoke test")

    hardware = hardware_budget or ComfyUIHardwareProbe(settings.media_url).current()
    preferred_kind = "image" if "image" in setup.profile.kinds else setup.profile.kinds[0]
    intent = _smoke_intent(preferred_kind)
    plan = MediaRenderCalculator().calculate(
        intent,
        [],
        quality="draft",
        max_megapixels=0.45,
        hardware_budget=hardware,
    )

    client = ComfyUIClient(
        base_url=settings.media_url,
        output_dir=settings.output_path,
        timeout=180.0,
        poll_interval=0.25,
        client=http_client,
    )
    try:
        generated = client.generate(
            "simple empty studio chair, soft light, clean photographic diagnostic render, high clarity",
            "person, child, text, watermark, logo, blurry, low quality, malformed geometry",
            seed=424242,
            profile=setup.profile,
            render_plan=plan,
        )
    finally:
        client.close()

    return WorkflowSmokeTestResult(
        generated=generated,
        render_plan=plan,
        hardware=hardware,
        profile_id=setup.profile.id,
    )
