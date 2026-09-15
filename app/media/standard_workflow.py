from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import httpx


class StandardWorkflowError(RuntimeError):
    """Raised when a standard local ComfyUI workflow cannot be built safely."""


@dataclass(frozen=True, slots=True)
class ComfyUICheckpointInventory:
    checkpoints: tuple[str, ...]
    sampler_names: tuple[str, ...]
    schedulers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return bool(self.checkpoints)


def _choice_values(value: object) -> tuple[str, ...]:
    """Extract ComfyUI combo choices from an object_info input descriptor."""

    if not isinstance(value, (list, tuple)) or not value:
        return ()
    choices = value[0]
    if not isinstance(choices, (list, tuple)):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for raw in choices:
        if not isinstance(raw, str):
            continue
        clean = raw.strip()
        folded = clean.casefold()
        if clean and folded not in seen:
            seen.add(folded)
            result.append(clean)
    return tuple(result)


def _required_inputs(node_info: object) -> dict[str, Any]:
    if not isinstance(node_info, dict):
        return {}
    raw_input = node_info.get("input")
    if not isinstance(raw_input, dict):
        return {}
    required = raw_input.get("required")
    return required if isinstance(required, dict) else {}


def _node_info(payload: object, class_type: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    direct = payload.get(class_type)
    if isinstance(direct, dict):
        return direct
    # Some compatible servers return one node's object directly for the
    # /object_info/<class> endpoint rather than wrapping it by class name.
    if "input" in payload:
        return payload
    return {}


def parse_checkpoint_inventory(payload: object) -> ComfyUICheckpointInventory:
    checkpoint_inputs = _required_inputs(_node_info(payload, "CheckpointLoaderSimple"))
    sampler_inputs = _required_inputs(_node_info(payload, "KSampler"))
    return ComfyUICheckpointInventory(
        checkpoints=_choice_values(checkpoint_inputs.get("ckpt_name")),
        sampler_names=_choice_values(sampler_inputs.get("sampler_name")),
        schedulers=_choice_values(sampler_inputs.get("scheduler")),
    )


def _merge_node_info_payloads(*payloads: object) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if "input" in payload:
            # The caller must use full object_info for an unwrapped response;
            # this branch is handled by discover_checkpoint_inventory below.
            continue
        merged.update(payload)
    return merged


def discover_checkpoint_inventory(
    base_url: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 15.0,
) -> ComfyUICheckpointInventory:
    """Discover already-installed checkpoints through ComfyUI object_info.

    Nothing is downloaded or installed. The returned checkpoint names are only
    whatever the configured local ComfyUI endpoint exposes to its standard
    CheckpointLoaderSimple node.
    """

    url = base_url.strip().rstrip("/")
    if not url:
        raise ValueError("ComfyUI-URL must not be blank")
    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout)
    try:
        # Prefer one full request because it also exposes the sampler/scheduler
        # choices required for a portable standard workflow. If a compatible
        # backend does not support the full endpoint, use class-scoped queries.
        try:
            response = http_client.get(f"{url}/object_info")
            response.raise_for_status()
            payload = response.json()
            inventory = parse_checkpoint_inventory(payload)
            if inventory.checkpoints:
                return inventory
        except (httpx.HTTPError, ValueError):
            pass

        scoped: dict[str, Any] = {}
        for class_type in ("CheckpointLoaderSimple", "KSampler"):
            try:
                response = http_client.get(f"{url}/object_info/{class_type}")
                response.raise_for_status()
                value = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if class_type == "CheckpointLoaderSimple":
                    raise StandardWorkflowError(
                        f"ComfyUI object_info konnte nicht gelesen werden: {exc}"
                    ) from exc
                continue
            if isinstance(value, dict) and "input" in value:
                scoped[class_type] = value
            elif isinstance(value, dict):
                node = value.get(class_type)
                if isinstance(node, dict):
                    scoped[class_type] = node

        inventory = parse_checkpoint_inventory(scoped)
        if not inventory.checkpoints:
            raise StandardWorkflowError(
                "ComfyUI meldet keine Checkpoints für CheckpointLoaderSimple. "
                "Installiere zuerst einen lokal nutzbaren Bild-Checkpoint in ComfyUI."
            )
        return inventory
    finally:
        if owns_client:
            http_client.close()


def _preferred_choice(values: tuple[str, ...], preferred: tuple[str, ...], fallback: str) -> str:
    folded = {value.casefold(): value for value in values}
    for candidate in preferred:
        found = folded.get(candidate.casefold())
        if found:
            return found
    return values[0] if values else fallback


def build_standard_image_workflow(
    checkpoint_name: str,
    *,
    sampler_names: tuple[str, ...] = (),
    schedulers: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a minimal ComfyUI API workflow from standard core nodes only."""

    checkpoint = checkpoint_name.strip()
    if not checkpoint:
        raise ValueError("Checkpoint name must not be blank")
    sampler = _preferred_choice(sampler_names, ("euler", "euler_ancestral", "dpmpp_2m"), "euler")
    scheduler = _preferred_choice(schedulers, ("normal", "karras", "simple"), "normal")

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "positive prompt", "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "negative prompt", "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 1024, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 424242,
                "steps": 24,
                "cfg": 6.5,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "local_ai_companion", "images": ["6", 0]},
        },
    }


def generated_workflow_path(output_dir: str | Path, checkpoint_name: str) -> Path:
    output = Path(output_dir).expanduser()
    root = output.parent / "generated_workflows"
    stem = Path(checkpoint_name.replace("\\", "/")).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-")[:56] or "checkpoint"
    return root / f"standard-image-{slug}.json"


def save_standard_image_workflow(
    output_dir: str | Path,
    checkpoint_name: str,
    *,
    sampler_names: tuple[str, ...] = (),
    schedulers: tuple[str, ...] = (),
) -> Path:
    target = generated_workflow_path(output_dir, checkpoint_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    workflow = build_standard_image_workflow(
        checkpoint_name,
        sampler_names=sampler_names,
        schedulers=schedulers,
    )
    target.write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
