from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.media.profiles import WorkflowCatalog, WorkflowProfile

_RENDER_KEYS = ("width", "height", "steps", "cfg", "denoise", "frames", "fps")
_AUTO_KEYS: dict[str, tuple[str, ...]] = {
    "steps": ("steps",),
    "cfg": ("cfg", "guidance", "guidance_scale"),
    "denoise": ("denoise", "denoise_strength"),
    "frames": ("frames", "frame_count", "num_frames", "length", "video_frames"),
    "fps": ("fps", "frame_rate", "framerate"),
}


def _literal_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _inputs(node: object) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    value = node.get("inputs")
    return value if isinstance(value, dict) else None


def _load_workflow(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists() or not path.is_file():
        return None, f"Workflow fehlt: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"Workflow-JSON ungültig: {exc}"
    if not isinstance(payload, dict) or not payload:
        return None, "Workflow ist kein nicht-leeres JSON-Objekt"
    return payload, ""


def _text_input_ok(workflow: dict[str, Any], node_id: str) -> bool:
    inputs = _inputs(workflow.get(node_id))
    return bool(inputs is not None and any(key in inputs for key in ("text", "prompt")))


def _seed_input_ok(workflow: dict[str, Any], node_id: str) -> bool:
    inputs = _inputs(workflow.get(node_id))
    return bool(inputs is not None and any(key in inputs for key in ("seed", "noise_seed")))


def _explicit_binding_ok(
    workflow: dict[str, Any], profile: WorkflowProfile, parameter: str
) -> bool:
    binding = profile.render_bindings.get(parameter)
    if binding is None:
        return False
    inputs = _inputs(workflow.get(binding.node))
    return bool(
        inputs is not None
        and binding.input_key in inputs
        and _literal_number(inputs[binding.input_key])
    )


def _auto_render_controls(workflow: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for node in workflow.values():
        inputs = _inputs(node)
        if inputs is None:
            continue
        if (
            "width" in inputs
            and "height" in inputs
            and _literal_number(inputs["width"])
            and _literal_number(inputs["height"])
        ):
            result.update(("width", "height"))
        for parameter, aliases in _AUTO_KEYS.items():
            if any(key in inputs and _literal_number(inputs[key]) for key in aliases):
                result.add(parameter)
    return result


def _output_evidence(workflow: dict[str, Any]) -> set[str]:
    """Return conservative output evidence from common and custom node families.

    Motion is accepted only when the graph contains both frame/animation evidence
    and an animated encoder or container output. A filename alone is never enough.
    """

    result: set[str] = set()
    frame_evidence = False
    animated_output = False
    gif_output = False
    still_output = False

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = " ".join(str(node.get("class_type") or "").casefold().split())
        compact_type = class_type.replace("_", "").replace("-", "").replace(" ", "")
        inputs = _inputs(node) or {}
        format_text = " ".join(
            str(inputs.get(key) or "").casefold()
            for key in ("format", "video_format", "container", "codec", "extension")
        )
        keys = {str(key).casefold() for key in inputs}

        if any(token in compact_type for token in ("saveimage", "previewimage")):
            still_output = True

        if (
            any(token in compact_type for token in (
                "animatediff",
                "svdimg2vid",
                "videolatent",
                "videomodel",
                "frameinterpolation",
                "rife",
                "filminterpolation",
                "imagesbatch",
            ))
            or any("frame" in key and key not in {"frame_rate", "framerate"} for key in keys)
        ):
            frame_evidence = True

        if any(token in compact_type for token in (
            "videocombine",
            "savevideo",
            "videoencoder",
            "vhscombine",
            "ffmpeg",
        )):
            animated_output = True
        if any(token in format_text for token in ("mp4", "webm", "h264", "h265", "hevc", "av1")):
            animated_output = True
        if "gif" in compact_type or "gif" in format_text:
            animated_output = True
            gif_output = True
        if "animatedwebp" in compact_type or "animated webp" in format_text:
            animated_output = True
            gif_output = True

    if still_output:
        result.add("image")
    if animated_output and frame_evidence:
        result.add("video")
        if gif_output:
            result.add("gif")
    return result


@dataclass(frozen=True, slots=True)
class WorkflowCapability:
    profile_id: str
    label: str
    workflow: Path
    enabled: bool
    valid: bool
    runnable: bool
    declared_kinds: tuple[str, ...]
    output_evidence: tuple[str, ...]
    reference_supported: bool
    render_controls: tuple[str, ...]
    missing_render_controls: tuple[str, ...]
    warnings: tuple[str, ...]
    error: str = ""

    @property
    def runnable_kinds(self) -> tuple[str, ...]:
        return self.declared_kinds if self.runnable else ()

    def summary(self) -> str:
        state = "bereit" if self.runnable else "nicht bereit"
        kinds = "/".join(self.declared_kinds) or "keine"
        reference = "Referenz ✓" if self.reference_supported else "Referenz –"
        render = ",".join(self.render_controls) or "Workflow-Defaults"
        return f"{self.profile_id}: {state} · {kinds} · {reference} · Render [{render}]"


def inspect_workflow_profile(profile: WorkflowProfile) -> WorkflowCapability:
    warnings: list[str] = []
    workflow, error = _load_workflow(profile.workflow_path)
    if workflow is None:
        return WorkflowCapability(
            profile_id=profile.id,
            label=profile.label or profile.id,
            workflow=profile.workflow_path,
            enabled=profile.enabled,
            valid=False,
            runnable=False,
            declared_kinds=tuple(profile.kinds),
            output_evidence=(),
            reference_supported=False,
            render_controls=(),
            missing_render_controls=_RENDER_KEYS,
            warnings=(),
            error=error,
        )

    positive_ok = _text_input_ok(workflow, profile.positive_node)
    negative_ok = _text_input_ok(workflow, profile.negative_node)
    seed_ok = _seed_input_ok(workflow, profile.seed_node)
    mapping_ok = positive_ok and negative_ok and seed_ok
    if not positive_ok:
        warnings.append(f"Positive Prompt Node {profile.positive_node} nicht nutzbar")
    if not negative_ok:
        warnings.append(f"Negative Prompt Node {profile.negative_node} nicht nutzbar")
    if not seed_ok:
        warnings.append(f"Seed Node {profile.seed_node} nicht nutzbar")

    reference_supported = False
    if profile.reference_configured:
        reference_inputs = _inputs(workflow.get(profile.reference_node))
        reference_supported = bool(
            reference_inputs is not None
            and profile.reference_input_key in reference_inputs
        )
        if not reference_supported:
            warnings.append(
                f"Referenz-Mapping {profile.reference_node}.{profile.reference_input_key} fehlt"
            )

    render_controls = _auto_render_controls(workflow)
    for parameter in profile.render_bindings:
        if _explicit_binding_ok(workflow, profile, parameter):
            render_controls.add(parameter)
        else:
            warnings.append(f"Render-Binding {parameter} ist nicht nutzbar")
    missing = tuple(key for key in _RENDER_KEYS if key not in render_controls)

    evidence = _output_evidence(workflow)
    for kind in profile.kinds:
        if evidence and kind not in evidence:
            warnings.append(
                f"{kind} ist deklariert; im Workflow wurde dafür kein eindeutiger Output-Node erkannt"
            )

    runnable = bool(profile.enabled and mapping_ok)
    return WorkflowCapability(
        profile_id=profile.id,
        label=profile.label or profile.id,
        workflow=profile.workflow_path,
        enabled=profile.enabled,
        valid=True,
        runnable=runnable,
        declared_kinds=tuple(profile.kinds),
        output_evidence=tuple(sorted(evidence)),
        reference_supported=reference_supported,
        render_controls=tuple(key for key in _RENDER_KEYS if key in render_controls),
        missing_render_controls=missing,
        warnings=tuple(warnings),
        error="" if mapping_ok else "Prompt-/Seed-Mapping unvollständig",
    )


def inspect_workflow_catalog(catalog: WorkflowCatalog) -> list[WorkflowCapability]:
    return [inspect_workflow_profile(profile) for profile in catalog.profiles]


def runnable_kinds(capabilities: list[WorkflowCapability]) -> set[str]:
    return {
        kind
        for capability in capabilities
        if capability.runnable
        for kind in capability.runnable_kinds
    }
